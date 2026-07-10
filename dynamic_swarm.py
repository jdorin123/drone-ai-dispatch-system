#!/usr/bin/env python3
import rospy
import math
import tf 
from geometry_msgs.msg import Twist
from gazebo_msgs.msg import ModelStates
from collections import deque

class SistemNavigatieRoi:
    """
    Gestioneaza urmarirea traiectoriei liderului de catre dronele follower 
    folosind logica de tip Pure Pursuit (Sfoara elastica).
    """
    def __init__(self):
        rospy.init_node('swarm_manager', anonymous=True)
        self.subs = rospy.Subscriber('/gazebo/model_states', ModelStates, self.callback)
        self.pubs = {}
        # Coada limitata la 300 puncte pentru traiectoria istorica a liderului
        self.istoric_puncte = deque(maxlen=300) 
        self.baterie_virtuala = 100.0
        self.tf_broadcaster = tf.TransformBroadcaster()
        rospy.loginfo("[INIT] Sistemul de management al roiului si TF broadcaster a fost pornit.")

    def callback(self, msg):    
        try:
            if self.baterie_virtuala <= 0:
                 return
            
            # Localizare drona lider in vectorul de state Gazebo
            idx_lider = msg.name.index('drona_lider')
            pos_lider = msg.pose[idx_lider].position
            q_lider = msg.pose[idx_lider].orientation

            # Publicare transformari TF pentru monitorizare in RViz
            self.tf_broadcaster.sendTransform(
                (pos_lider.x, pos_lider.y, pos_lider.z),
                (q_lider.x, q_lider.y, q_lider.z, q_lider.w),
                rospy.Time.now(),
                "base_link",
                "odom"
            )

            # Actualizare traiectorie istoric lider cu filtrare spatiala (>0.5m)
            if not self.istoric_puncte or math.dist([pos_lider.x, pos_lider.y], self.istoric_puncte[-1]) > 0.5:
                self.istoric_puncte.append((pos_lider.x, pos_lider.y))

            # Procesare control individual pentru fiecare drona urmaritoare
            follower_names = [n for n in msg.name if "drona_follower" in n]
            follower_names.sort()

            for i, nume_drona in enumerate(follower_names):
                if nume_drona not in self.pubs:
                    self.pubs[nume_drona] = rospy.Publisher(f"/{nume_drona}/cmd_vel_follower", Twist, queue_size=10)

                idx_curent = msg.name.index(nume_drona)
                pos_curent = msg.pose[idx_curent].position
                q_curent = msg.pose[idx_curent].orientation
                
                # Setup ierarhie TF pentru follower
                self.tf_broadcaster.sendTransform((pos_curent.x, pos_curent.y, pos_curent.z), (q_curent.x, q_curent.y, q_curent.z, q_curent.w), rospy.Time.now(), "base_link_follower", "odom")
                self.tf_broadcaster.sendTransform((0.2, 0, 0.1), (0, 0, 0, 1), rospy.Time.now(), "camera_link_follower", "base_link_follower")
                self.tf_broadcaster.sendTransform((0, 0, 0.12), (0, 0, 0, 1), rospy.Time.now(), "velodyne_link_follower", "base_link_follower")

                # Transformare quaterion in euler pentru control unghiular
                euler = tf.transformations.euler_from_quaternion([q_curent.x, q_curent.y, q_curent.z, q_curent.w])
                yaw = euler[2]
                
                # Cautare tinta pentru lookahead de 3.5m
                tinta_curenta = None
                # Iteram invers prin traiectorie pentru a gasi cel mai apropiat punct valid de la drona curenta
                for punct in reversed(self.istoric_puncte): 
                    dist_catre_punct = math.dist([punct[0], punct[1]], [pos_curent.x, pos_curent.y])
                    if dist_catre_punct > 3.5: 
                        tinta_curenta = punct
                        break

                if tinta_curenta:
                    unghi_target = math.atan2(tinta_curenta[1] - pos_curent.y, tinta_curenta[0] - pos_curent.x)
                    eroare_unghiulara = math.atan2(math.sin(unghi_target - yaw), math.cos(unghi_target - yaw))
                    dist_target = math.dist([tinta_curenta[0], tinta_curenta[1]], [pos_curent.x, pos_curent.y])

                    comanda_vel = Twist()
                    if dist_target > 0.5:
                        # Profil viteza: limitat la 2.5m/s (peste viteza maxima a liderului)
                        comanda_vel.linear.x = min(2.5, dist_target * 0.8)
                        # Profil viraj cu limitari
                        comanda_vel.angular.z = max(min(eroare_unghiulara * 1.5, 2.0), -2.0) 
                        # Simulare descarcare (Model simplu de consum de energie)
                        self.baterie_virtuala -= ((abs(comanda_vel.linear.x) * 0.01) + (abs(comanda_vel.angular.z) * 0.005))
                    
                    self.pubs[nume_drona].publish(comanda_vel)

        except ValueError:
             # Dronele nu sunt inca vizibile in simulatorul Gazebo
            pass

if __name__ == '__main__':
    try:
        nod = SistemNavigatieRoi()
        rospy.spin()
    except rospy.ROSInterruptException:
        pass