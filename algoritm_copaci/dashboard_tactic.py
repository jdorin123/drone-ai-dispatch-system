import streamlit as st
import requests
import json
import os
import time
import numpy as np
from pydub import AudioSegment
from faster_whisper import WhisperModel
import warnings
import re
import math
import uuid
import pandas as pd
import socket
import logging
from datetime import datetime, timezone, timedelta

import config
import ros_manager

try:
    import mgrs
    mgrs_converter = mgrs.MGRS()
except ImportError:
    mgrs_converter = None
    logging.warning("Modulul MGRS lipseste. Coordonatele NATO nu se vor parsa corect.")

warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

st.set_page_config(page_title="Dispecerat Tactic", layout="wide")

@st.cache_resource
def load_whisper():
    model = WhisperModel(config.WHISPER_MODEL_SIZE, device="cpu", compute_type="int8")
    return model

@st.cache_resource
def setup_ros():
    ros_manager.init_ros_node()
    return True

if 'drone_active' not in st.session_state:
    st.session_state.drone_active = 0
if 'drone_disponibile' not in st.session_state:
    st.session_state.drone_disponibile = 15 

if 'inbox_mesaje' not in st.session_state:
    if os.path.exists(config.FISIER_SALVARE_INBOX):
        with open(config.FISIER_SALVARE_INBOX, "r") as f:
            st.session_state.inbox_mesaje = json.load(f)
    else:
        st.session_state.inbox_mesaje = {}

model_whisper = load_whisper()
setup_ros()

def get_haversine_dist(lat1, lon1, lat2, lon2):
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return config.R_EARTH * c

def extract_mgrs(text):
    clean_text = text.replace(" ", "").replace("-", "").replace(",", "").replace(".", "").upper()
    mgrs_pattern = r'([1-6][0-9][C-X][A-Z]{2}[0-9]{4,10})'
    match = re.search(mgrs_pattern, clean_text)
    
    if match:
        mgrs_str = match.group(1)
        lat, lon = None, None
        if mgrs_converter:
            try:
                lat, lon = mgrs_converter.toLatLon(mgrs_str)
            except Exception:
                pass 
        return mgrs_str, lat, lon
            
    return None, None, None

def get_audio_rms(filepath):
    try:
        audio = AudioSegment.from_file(filepath)
        samples = np.array(audio.get_array_of_samples(), dtype=np.float32)
        if audio.channels > 1:
            samples = samples.reshape((-1, audio.channels)).mean(axis=1)
        rms = np.sqrt(np.mean(samples**2))
        return round(min(100, (rms / 32768.0) * 500), 2)
    except Exception as e:
        logger.error(f"Eroare procesare RMS: {e}")
        return 0.0

def query_tactical_llm(text, stress_lvl):
    prompt = f"""You are an advanced military triaging AI. Analyze this transcript.
Transcript: "{text}"

STEP 1: THINKING (Scratchpad)
Write a brief analysis of the transcript. 
- Identify the radio callsign of the sender. Callsigns are STRICTLY a NATO phonetic word (Alpha, Bravo, Charlie, Delta, etc.) followed by a number or role (e.g., "Charlie 2", "Bravo Actual", "Alpha Base", "Charlie IV").
- CRITICAL: Words like "Winchester", "Mayday", "Speedball", "HQ", "Command", or "Dispatch" are NOT sender callsigns. Ignore them entirely for the callsign field.
- If no valid phonetic callsign is found, output "NECUNOSCUT".
- Did the soldier explicitly state "NO casualties" or "ZERO casualties"? (If yes, it is MICRO-RESUPPLY).
- Count the items requested carefully. OUTPUT ONLY INTEGERS as values in the JSON (e.g. use 3, do NOT use "three" or "3").

STEP 2: JSON EXTRACTION
After your analysis, output strictly this JSON structure:
{{
    "callsign": "extracted callsign here",
    "red_threats": ["keywords", "like", "IED"],
    "inventory": {{
        "blood": 0, "tourniquet": 0, "gauze": 0, "chest_seal": 0,
        "morphine": 0, "ammo": 0, "smoke": 0, "batteries": 0
    }},
    "mission_type": "POI MEDICAL SUPPORT" // or "MICRO-RESUPPLY"
}}"""

    payload = {"model": config.MODEL_LLM, "prompt": prompt, "stream": False, "format": "json", "temperature": 0.1}
    
    try:
        response = requests.post(config.OLLAMA_URL, json=payload, timeout=120)
        raw_response = response.json()
        response_text = raw_response.get('response', '').strip()
        
        match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if match:
            result = json.loads(match.group(0))
        else:
            return None
            
        if not isinstance(result.get('inventory'), dict):
            result['inventory'] = {}
        if not isinstance(result.get('red_threats'), list):
            result['red_threats'] = []
            
        return result
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Eroare conexiune Ollama: {e}")
        return None

def parse_payload_data(llm_inventory):
    mapare = {
        "blood": "sange_integral",
        "tourniquet": "garou_cat",
        "gauze": "pansament_hemostatic",
        "chest_seal": "chest_seal",
        "morphine": "morfina_autoinjector",
        "ammo": "incarcator_556",
        "smoke": "grenada_fum_m18",
        "batteries": "baterie_radio_prc"
    }
    
    # Dicționar de rezervă în cazul în care LLM-ul răspunde cu "three" în loc de 3
    text_to_num = {
        "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, 
        "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10
    }
    
    intern_inv = {k: 0 for k in mapare.values()}
    
    if isinstance(llm_inventory, dict):
        for key_eng, key_ro in mapare.items():
            val = llm_inventory.get(key_eng, 0)
            
            val_calculat = 0
            # Verificăm ce fel de format ne-a dat Ollama și îl forțăm la Integer
            if isinstance(val, int):
                val_calculat = val
            elif isinstance(val, float):
                val_calculat = int(val)
            elif isinstance(val, str):
                val_str = val.lower().strip()
                if val_str.isdigit():
                    val_calculat = int(val_str)
                elif val_str in text_to_num:
                    val_calculat = text_to_num[val_str]
                    
            if val_calculat > 0:
                intern_inv[key_ro] = val_calculat
    
    return intern_inv

def broadcast_wintak_cot(uid, lat, lon, marker_type="a-h-G", callsign="Dispecerat", details="N/A", delete_marker=False):
    now_dt = datetime.now(timezone.utc)
    now = now_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    
    if delete_marker:
        stale = (now_dt - timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    else:
        stale = (now_dt + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
    
    clean_name = callsign.replace(".wav", "").replace(".mp3", "")[:30]
    
    xml_cot = f"""<?xml version="1.0" encoding="utf-8" standalone="yes"?>
<event version="2.0" uid="{uid}" type="{marker_type}" time="{now}" start="{now}" stale="{stale}" how="h-g-i-g-o">
    <point lat="{lat}" lon="{lon}" hae="0.0" ce="10.0" le="10.0"/>
    <detail>
        <contact callsign="{clean_name}"/>
        <remarks>{details}</remarks>
    </detail>
</event>"""
    
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        
        sock.sendto(xml_cot.encode('utf-8'), (config.WINTAK_LOCAL_IP, config.WINTAK_LOCAL_PORT))
        sock.sendto(xml_cot.encode('utf-8'), (config.WINTAK_BROADCAST_IP, config.WINTAK_BROADCAST_PORT))
        
        ip_windows = config.WINTAK_LOCAL_IP
        if os.path.exists('/etc/resolv.conf'):
            with open('/etc/resolv.conf', 'r') as f:
                for line in f:
                    if line.startswith('nameserver'):
                        ip_windows = line.split()[1]
                        break
        sock.sendto(xml_cot.encode('utf-8'), (ip_windows, config.WINTAK_LOCAL_PORT))
    except Exception as e:
        logger.error(f"Eroare trimitere pachet WinTAK: {e}")
        
    return xml_cot

def format_transcript_ui(text, red_words, required_resources, mgrs_str=None):
    buf = {}
    counter = [0]
    temp_text = text

    def add_to_buffer(match, color):
        orig_word = match.group(0)
        key = f"@@BUF{counter[0]}@@"
        buf[key] = f":{color}[{orig_word}]"
        counter[0] += 1
        return key

    if mgrs_str:
        pattern_mgrs = r'[\s\,\.\-]*'.join(list(mgrs_str))
        temp_text = re.sub(f"(?i)({pattern_mgrs})", lambda m: add_to_buffer(m, "green"), temp_text)

    eng_map = {
        "sange_integral": ["blood", "plasma"],
        "garou_cat": ["tourniquet", "trauma kit", "medical kit", "trauma kits", "tourniquets"],
        "pansament_hemostatic": ["gauze", "hemostatic", "hemostatic gauze"],
        "chest_seal": ["chest seal", "chest seals"],
        "morfina_autoinjector": ["morphine", "painkiller", "morphine auto-injector", "painkillers"],
        "incarcator_556": ["ammo", "magazine", "box", "boxes"],
        "grenada_fum_m18": ["smoke", "smoke grenade", "smoke grenades"],
        "baterie_radio_prc": ["battery", "batteries"]
    }

    qty_prefix = r"(?:(?:a|one|two|three|four|five|six|seven|eight|nine|ten|\d+)\s+(?:(?:bag|bags|box|boxes|pack|packs|kit|kits)\s+of\s+)?)?"

    for eng_words in eng_map.values():
        for word in eng_words:
            pattern_res = rf"\b({qty_prefix}(?:{re.escape(word)}s?|{re.escape(word)}es))\b"
            temp_text = re.sub(f"(?i)({pattern_res})", lambda m: add_to_buffer(m, "blue"), temp_text)

    red_words = red_words if isinstance(red_words, list) else ([red_words] if red_words else [])
    for w in red_words:
        if w and len(str(w)) > 2:
            pattern_threat = rf"\b({re.escape(str(w))})\b"
            temp_text = re.sub(f"(?i)({pattern_threat})", lambda m: add_to_buffer(m, "red"), temp_text)

    for key, formatted_val in buf.items():
        temp_text = temp_text.replace(key, formatted_val)

    return temp_text

def get_required_drones(inventory):
    total_weight = 0.0
    for item, qty in inventory.items():
        if item in config.PAYLOAD_WEIGHTS_KG and qty > 0:
            total_weight += config.PAYLOAD_WEIGHTS_KG[item] * qty
            
    if total_weight == 0:
        return 1
        
    return math.ceil(total_weight / config.CAPACITATE_MAXIMA_DRONA_KG)

with st.sidebar:
    st.header("Gestiune Flotă")
    st.metric(label="Drone Disponibile", value=st.session_state.drone_disponibile)
    st.metric(label="Drone pe Traseu", value=st.session_state.drone_active)
    if st.button("Reîncarcă Flota (+10)"):
        st.session_state.drone_disponibile += 10
        st.rerun()

    st.markdown("---")
    st.header("Bază de Date")
    if st.button("Resetare Totală Date", type="primary"):
        st.session_state.inbox_mesaje = {}
        if os.path.exists(config.FISIER_SALVARE_INBOX):
            try:
                os.remove(config.FISIER_SALVARE_INBOX)
            except Exception as e:
                st.error(f"Eroare sistem fișiere: {e}")
        st.session_state.drone_disponibile = 15
        st.session_state.drone_active = 0
        st.rerun()

st.title("CENTRUL DE COMANDĂ: ROAM SWARM")
st.markdown("Monitorizare autonomă a frecvențelor radio.")

col_scan, _ = st.columns([1, 2])
with col_scan:
    if st.button("SCANEAZĂ FRECVENȚELE RADIO", type="primary", use_container_width=True):
        if os.path.exists(config.FOLDER_AUDIO):
            fisiere_noi = [f for f in os.listdir(config.FOLDER_AUDIO) if f.lower().endswith(('.wav', '.mp3')) and f not in st.session_state.inbox_mesaje]
            if fisiere_noi:
                progress_bar = st.progress(0)
                status_text = st.empty() 
                
                for idx, fisier in enumerate(fisiere_noi):
                    cale = os.path.join(config.FOLDER_AUDIO, fisier)
                    t0 = time.time() 
                    
                    status_text.info(f"Decodare semnal RX: {fisier}...")
                    
                    try:
                        stres = get_audio_rms(cale)
                        tactical_vocab = "Military tactical radio. NATO MGRS Grid 35 T U L 12345678, 35TUL. TCCC, tourniquet, whole blood, chest seal, hemostatic gauze, plasma, ammo, smoke grenade, casualties, IED, GNSS-denied, speedball."
                        
                        segmente, info = model_whisper.transcribe(
                            cale, language="en", beam_size=2,
                            condition_on_previous_text=False, vad_filter=True,
                            vad_parameters=dict(min_silence_duration_ms=500),
                            temperature=[0.0, 0.2, 0.4, 0.6, 0.8],
                            compression_ratio_threshold=1.5, no_speech_threshold=0.6,
                            initial_prompt=tactical_vocab
                        )
                        
                        segmente_list = list(segmente)
                        text_parts = []
                        for segment in segmente_list:
                            seg_text = segment.text.strip()
                            if seg_text and seg_text not in text_parts:
                                text_parts.append(seg_text)
                        
                        text_brut = " ".join(text_parts)
                        text_curat_1 = re.sub(r'\b(\w+)(?:[.,!?\s]+(?i)\1\b)+', r'\1', text_brut, flags=re.IGNORECASE)
                        text = re.sub(r'\b(.{4,60}?)(?:[.,!?\s]+\1\b)+', r'\1', text_curat_1, flags=re.IGNORECASE).strip()
                        
                    except Exception as e:
                        logger.error(f"Eroare modul Whisper: {e}")
                        continue
                    
                    status_text.warning(f"Analiză LLM și Extragere MGRS pentru: {fisier}...")
                    
                    mgrs_str, lat, lon = extract_mgrs(text)
                    distanta_zbor = 0.0
                    if lat and lon:
                        distanta_zbor = get_haversine_dist(config.BASE_LAT, config.BASE_LON, lat, lon)
                    
                    decizie = query_tactical_llm(text, stres)
                    
                    if decizie:
                        inventar_llm = decizie.get("inventory", {})
                        inventar_procesat = parse_payload_data(inventar_llm)
                        m_type_raw = decizie.get("mission_type", "MICRO-RESUPPLY")
                        tip_misiune = "SUPORT MEDICAL POI" if "POI" in m_type_raw else "REAPROVIZIONARE"
                        pericol_rosu = decizie.get("red_threats", [])
                    else:
                        inventar_procesat = {k: 0 for k in config.PAYLOAD_WEIGHTS_KG.keys()}
                        tip_misiune = "REAPROVIZIONARE"
                        pericol_rosu = []
                    
                    text_lower = text.lower() if text else ""
                    cuvinte_critice = ["attack", "casualties", "wounded", "ied", "mayday", "heavy fire", "ambush", "contact", "men down", "bleeding"]
                    
                    # NOUA LOGICĂ: Verificăm dacă termenul critic este precedat de "no", "zero" sau "0"
                    pericole_detectate = []
                    for c in cuvinte_critice:
                        if c in text_lower:
                            # re.search ignoră cuvântul critic dacă în fața lui se află "no", "zero" sau "0"
                            if not re.search(rf"\b(?:no|zero|0)\s+{re.escape(c)}\b", text_lower):
                                pericole_detectate.append(c)
                                
                    if pericole_detectate:
                        este_critic = True
                        for p in pericole_detectate:
                            if p not in pericol_rosu:
                                pericol_rosu.append(p)
                    else:
                        este_critic = False
                    
                    urgenta = "CRITIC" if este_critic else "MEDIU" if stres > 70 else "SCAZUT"
                    if este_critic:
                        tip_misiune = "SUPORT MEDICAL POI (SUPRASCRIS)"

                    xml_generat = "Indisponibil"
                    uid_curent = str(uuid.uuid4())[:8]
                    callsign_ai = decizie.get("callsign", fisier.replace(".wav", "").replace(".mp3", "")) if decizie else fisier
                    
                    if lat and lon:
                        if urgenta == "CRITIC":
                            tip_cot = "a-h-G" 
                        elif urgenta == "MEDIU":
                            tip_cot = "a-u-G" 
                        else:
                            tip_cot = "a-n-G" 
                            
                        obiecte_text_wintak = ", ".join([f"{cant}x {item.replace('_', ' ')}" for item, cant in inventar_procesat.items() if cant > 0])
                        detalii_wintak = f"Ora Interceptării: {datetime.now().strftime('%H:%M')} | Sarcină Utilă: {obiecte_text_wintak if obiecte_text_wintak else 'Nespecificat'}"
                        
                        xml_generat = broadcast_wintak_cot(uid_curent, lat, lon, tip_cot, callsign_ai, detalii_wintak)
                    
                    st.session_state.inbox_mesaje[fisier] = {
                        "uid": uid_curent,
                        "callsign": callsign_ai,
                        "text": text,
                        "stres": stres,
                        "urgenta": urgenta,
                        "tip_misiune": tip_misiune,
                        "inventar_curat": inventar_procesat,
                        "drone_calculate": get_required_drones(inventar_procesat),
                        "cale": cale,
                        "mgrs": mgrs_str,
                        "lat": lat,
                        "lon": lon,
                        "distanta_m": distanta_zbor,
                        "xml_generat": xml_generat,
                        "rezolvat": False,
                        "pericol_rosu": pericol_rosu
                    }

                    with open(config.FISIER_SALVARE_INBOX, "w") as f:
                        json.dump(st.session_state.inbox_mesaje, f, indent=4)
                    
                    logger.info(f"Procesat {fisier} în {round(time.time() - t0, 1)}s.")
                    progress_bar.progress((idx + 1) / len(fisiere_noi))
                
                status_text.success("Scanare finalizată.")
                time.sleep(1.5)
                st.rerun()
            else:
                st.info("Nu există fișiere noi în folderul de monitorizare.")

st.markdown("---")

def render_mission_card(fisier, data):
    urgenta, tip_misiune = data["urgenta"], data["tip_misiune"]
    inventar = data["inventar_curat"]
    
    tip_alerta = st.error if urgenta == "CRITIC" else (st.warning if urgenta == "MEDIU" else st.success)

    with st.container():
        nume_afisat = data.get("callsign", fisier)
        tip_alerta(f"**{nume_afisat}** - {tip_misiune}")
        col_detalii, col_actiune = st.columns([2.5, 1.5])
        
        with col_detalii:
            st.markdown(f"**Transcriere:** {format_transcript_ui(data['text'], data['pericol_rosu'], inventar, data.get('mgrs'))}")
            obiecte_text = ", ".join([f"{cant}x {item.replace('_', ' ')}" for item, cant in inventar.items() if cant > 0])
            st.write(f"**Sarcină Utilă Estimată:** :blue[{obiecte_text if obiecte_text else 'Nespecificat'}]")
            st.write(f"**Stres Analizat (RMS):** {data['stres']}/100")
            st.audio(data['cale']) 
            
            if data['lat'] and data['lon']:
                with st.expander("Telemetrie WinTAK și Mapare"):
                    st.write(f"**MGRS:** `{data['mgrs']}` | **Distanță:** `{data['distanta_m']:.1f} m`")
                    st.map(pd.DataFrame([{"lat": data['lat'], "lon": data['lon']}]), zoom=12, use_container_width=True)
                    st.code(data['xml_generat'], language='xml')
            
        with col_actiune:
            if data["rezolvat"]:
                st.info("Misiune finalizată. Roi dispersat.")
            else:
                st.write("**Aprobare Sarcină Utilă:**")
                
                inventar_modificat = {}
                with st.expander("Suprascriere sistem", expanded=False):
                    for item, cantitate in inventar.items():
                        nume_frumos = item.replace("_", " ").title()
                        inventar_modificat[item] = st.number_input(
                            nume_frumos, 
                            min_value=0, max_value=100, 
                            value=int(cantitate), 
                            key=f"edit_{fisier}_{item}"
                        )
                
                drone_necesare = get_required_drones(inventar_modificat)
                
                drone_aprobate = st.number_input(
                    "Alocare manuală drone:", 
                    min_value=1, max_value=20, 
                    value=min(20, max(1, drone_necesare)), 
                    key=f"spin_{fisier}"
                )
                
                if st.button(f"LANSEAZĂ {drone_aprobate} DRONE", key=f"btn_{fisier}", type="primary" if urgenta == "CRITIC" else "secondary", use_container_width=True):
                    if drone_aprobate > st.session_state.drone_disponibile:
                        st.error("Resurse insuficiente în flotă!")
                    else:
                        lat_dest = data.get('lat') if data.get('lat') else config.BASE_LAT
                        lon_dest = data.get('lon') if data.get('lon') else config.BASE_LON
                        
                        x_gaz, y_gaz, dist_m = ros_manager.converteste_gps_in_gazebo(lat_dest, lon_dest)
                        
                        if dist_m > config.MAX_FLIGHT_DISTANCE_M:
                            st.error(f"ANULARE: Ținta la {dist_m}m. Depășește distanța de siguranță de {config.MAX_FLIGHT_DISTANCE_M}m!")
                        else:
                            st.success(f"Aprobat pentru lansare. Rutare către Gazebo X:{x_gaz}, Y:{y_gaz}")
                            
                            with st.spinner("Se transmite către nodul ROS..."):
                                st.session_state.drone_active = ros_manager.executa_misiune_roi(
                                    drone_necesare=drone_aprobate,
                                    drone_active_curent=st.session_state.drone_active,
                                    coordonate_x=x_gaz,
                                    coordonate_y=y_gaz
                                )
                                
                            if data.get('lat') and data.get('lon'):
                                broadcast_wintak_cot(data['uid'], data['lat'], data['lon'], delete_marker=True)
                                
                            st.session_state.drone_disponibile -= drone_aprobate
                            st.session_state.inbox_mesaje[fisier]["inventar_curat"] = inventar_modificat
                            st.session_state.inbox_mesaje[fisier]["rezolvat"] = True
                            
                            with open(config.FISIER_SALVARE_INBOX, "w") as f:
                                json.dump(st.session_state.inbox_mesaje, f, indent=4)
                                
                            st.rerun()
    st.markdown("<hr style='margin: 10px 0px; opacity: 0.2;'>", unsafe_allow_html=True)


st.subheader("JURNAL OPERAȚIUNI")
tab_active, tab_arhiva = st.tabs(["Acțiuni în Așteptare", "Istoric Misiuni"])

lista_mesaje = list(st.session_state.inbox_mesaje.items())
lista_mesaje.sort(key=lambda x: 0 if x[1]["urgenta"] == "CRITIC" else 1)

misiuni_active = [(f, d) for f, d in lista_mesaje if not d.get("rezolvat", False)]
misiuni_arhivate = [(f, d) for f, d in lista_mesaje if d.get("rezolvat", False)]

with tab_active:
    if not misiuni_active:
        st.info("Nicio transmisie detectată.")
    else:
        for fisier, date in misiuni_active:
            render_mission_card(fisier, date)

with tab_arhiva:
    if not misiuni_arhivate:
        st.info("Istoric gol.")
    else:
        for fisier, date in misiuni_arhivate:
            render_mission_card(fisier, date)