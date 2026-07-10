"""
Modul pentru comunicarea cu sistemul ROS si simulatorul Gazebo.
Gestioneaza spawn-ul modelelor si publicarea coordonatelor de navigatie.
"""

import rospy
import os
import time
import math
import logging
from geometry_msgs.msg import PoseStamped
import config

logger = logging.getLogger(__name__)

def init_ros_node():
    """ Initializeaza nodul ROS doar daca nu exista deja. """
    try:
        rospy.init_node('dispecer_gui', anonymous=True, disable_signals=True)
        logger.info("Nod ROS 'dispecer_gui' initializat cu succes.")
    except rospy.exceptions.ROSException:
        # Probabil nodul e deja pornit, ignoram
        pass

def converteste_gps_in_gazebo(lat_tinta, lon_tinta):
    """
    Transforma lat/lon din WinTAK in X/Y cartezian pentru harta din Gazebo.
    Calculeaza si distanta in linie dreapta pt verificarea geofence-ului.
    """
    lat_baza_rad = math.radians(config.BASE_LAT)
    lon_baza_rad = math.radians(config.BASE_LON)
    lat_tinta_rad = math.radians(lat_tinta)
    lon_tinta_rad = math.radians(lon_tinta)

    delta_lat = lat_tinta_rad - lat_baza_rad
    y_gazebo = delta_lat * config.R_EARTH

    delta_lon = lon_tinta_rad - lon_baza_rad
    x_gazebo = delta_lon * config.R_EARTH * math.cos(lat_baza_rad)

    distanta_totala = math.sqrt(x_gazebo**2 + y_gazebo**2)

    return round(x_gazebo, 2), round(y_gazebo, 2), round(distanta_totala, 2)

def executa_misiune_roi(drone_necesare, drone_active_curent, coordonate_x=0.0, coordonate_y=0.0):
    """
    Comanda sistemul de lansare: intai Liderul, apoi preia coordonatele 
    si lanseaza followerii daca greutatea (payload-ul) o cere.
    """
    if drone_necesare <= 0:
        logger.info("Nu sunt necesare drone suplimentare pentru acest payload.")
        return drone_active_curent

    logger.info(f"Se lanseaza Drona Lider spre grid-ul (X:{coordonate_x}, Y:{coordonate_y}).")
    
    # Lansare Lider CURAT, fara cai absolute care blocheaza Gazebo
    os.system("rosrun gazebo_ros spawn_model -sdf -file drona_lider.sdf -model drona_lider -x -45 -y 0 -z 1.5")
    time.sleep(2) 
    
    # Publicare destinatie pt algoritmul A*
    pub_goal = rospy.Publisher('/move_base_simple/goal', PoseStamped, queue_size=1)
    time.sleep(1) 
    
    goal_msg = PoseStamped()
    goal_msg.header.stamp = rospy.Time.now()
    goal_msg.header.frame_id = "map" 
    
    goal_msg.pose.position.x = float(coordonate_x)
    goal_msg.pose.position.y = float(coordonate_y)
    goal_msg.pose.position.z = 0.0
    goal_msg.pose.orientation.w = 1.0 
    
    logger.info("Destinatie trimisa. Liderul proceseaza traseul...")
    pub_goal.publish(goal_msg)
    
    if drone_necesare == 1:
        logger.info("Misiune de maxim 1kg. Liderul executa singur.")
        return drone_active_curent

    # Lansare Followeri daca greutatea e mare
    numar_followeri = drone_necesare - 1 
    drone_update = drone_active_curent

    for i in range(numar_followeri):
        drone_update += 1
        nume_drona = f"drona_follower_{drone_update}"
        
        # Calcul offset lansare
        x_spawn = -48 - (i * 1.5)
        y_spawn = 1.0 + (i * 0.5)

        logger.info(f"Spawnam {nume_drona} pt preluare surplus payload...")
        os.system(f"rosrun gazebo_ros spawn_model -sdf -file drona_follower.sdf -model {nume_drona} -robot_namespace {nume_drona} -x {x_spawn} -y {y_spawn} -z 1.5")
        time.sleep(2) 

    logger.info(f"Misiune inceputa cu 1 Lider si {numar_followeri} Followeri.")
    return drone_update