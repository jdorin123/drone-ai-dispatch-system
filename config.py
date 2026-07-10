"""
Universitatea Tehnică din Cluj-Napoca (UTCN)
Facultatea de Inginerie Electrică
Modul Configurare - Dispecerat Tactic Roi de Drone
"""

import math

# --- Setari Geospatiale (Zona testare) ---
# Momentan setat pe zona de testare default, a se modifica pt testele live
BASE_LAT = 46.7712
BASE_LON = 23.6236
R_EARTH = 6371000.0  # Raza ecuatoriala (m)

# Limita geofence pt siguranta testelor (setata la 3.5km pt acoperire radio in mediu impadurit)
MAX_FLIGHT_DISTANCE_M = 3500.0  

# --- Retea si Comunicatii (WinTAK / WSL) ---
WINTAK_BROADCAST_IP = "239.2.3.1"
WINTAK_BROADCAST_PORT = 6969
WINTAK_LOCAL_IP = "127.0.0.1"
WINTAK_LOCAL_PORT = 4242

# --- Setari AI si Backend ---
# TODO: De mutat pe un server dedicat daca Llama3.2 mananca prea mult RAM
OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_LLM = "llama3.2"
WHISPER_MODEL_SIZE = "small" # Testat: 'small' e cel mai bun compromis viteza/acuratete pe CPU

# --- Cai directoare si Fisiere ---
FOLDER_AUDIO = "audio_uri_dispecer"
FISIER_SALVARE_INBOX = "inbox_memorie.json"

# --- Parametri Tehnici Drone ---
CAPACITATE_MAXIMA_DRONA_KG = 1.0  # limitare constructiva per drona follower

# Greutati standardizate pt calculul automat de payload
PAYLOAD_WEIGHTS_KG = {
    "sange_integral": 0.50,
    "garou_cat": 0.08,
    "pansament_hemostatic": 0.05,
    "chest_seal": 0.04,
    "morfina_autoinjector": 0.05,
    "incarcator_556": 0.49,
    "grenada_fum_m18": 0.54,
    "baterie_radio_prc": 0.40
}