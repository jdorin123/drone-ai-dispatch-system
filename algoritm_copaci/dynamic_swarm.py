#!/usr/bin/env python3
import rospy
import math
import tf 
from geometry_msgs.msg import Twist
from gazebo_msgs.msg import ModelStates
from collections import deque

class SistemNavigatieRoi:
    def __init__(self):
        rospy.init_node('swarm_manager', anonymous=True)
        self.subs = rospy.Subscriber('/gazebo/model_states', ModelStates, self.callback)
        self.pubs = {}
        # Am mărit memoria la 500 de puncte ca să nu piardă traseul la curbele lungi
        self.istoric_puncte = deque(maxlen=500) 
        self.baterie_virtuala = 100.0
        self.tf_broadcaster = tf.TransformBroadcaster()
        rospy.loginfo("[INIT] Sistemul Swarm: Pure Pursuit Autentic pe Breadcrumbs Activat.")

    def callback(self, msg):    
        try:
            if self.baterie_virtuala <= 0: return
            
            idx_lider = msg.name.index('drona_lider')
            pos_lider = msg.pose[idx_lider].position
            q_lider = msg.pose[idx_lider].orientation

            self.tf_broadcaster.sendTransform(
                (pos_lider.x, pos_lider.y, pos_lider.z),
                (q_lider.x, q_lider.y, q_lider.z, q_lider.w),
                rospy.Time.now(), "base_link", "odom"
            )

            # Lăsăm firimiturile mai des (la fiecare 0.3m) pentru o precizie fină la ocolirea copacilor
            if not self.istoric_puncte or math.dist([pos_lider.x, pos_lider.y], self.istoric_puncte[-1]) > 0.3:
                self.istoric_puncte.append((pos_lider.x, pos_lider.y))

            follower_names = [n for n in msg.name if "drona_follower" in n]
            follower_names.sort()

            for i, nume_drona in enumerate(follower_names):
                if nume_drona not in self.pubs:
                    self.pubs[nume_drona] = rospy.Publisher(f"/{nume_drona}/cmd_vel_follower", Twist, queue_size=10)

                idx_curent = msg.name.index(nume_drona)
                pos_curent = msg.pose[idx_curent].position
                q_curent = msg.pose[idx_curent].orientation
                
                nume_baza = f"base_link_{nume_drona}"
                self.tf_broadcaster.sendTransform((pos_curent.x, pos_curent.y, pos_curent.z), (q_curent.x, q_curent.y, q_curent.z, q_curent.w), rospy.Time.now(), nume_baza, "odom")
                self.tf_broadcaster.sendTransform((0.2, 0, 0.1), (0, 0, 0, 1), rospy.Time.now(), f"camera_link_{nume_drona}", nume_baza)
                self.tf_broadcaster.sendTransform((0, 0, 0.12), (0, 0, 0, 1), rospy.Time.now(), f"velodyne_link_{nume_drona}", nume_baza)

                euler = tf.transformations.euler_from_quaternion([q_curent.x, q_curent.y, q_curent.z, q_curent.w])
                yaw = euler[2]
                
                comanda_vel = Twist() 
                dist_fata_de_lider = math.dist([pos_lider.x, pos_lider.y], [pos_curent.x, pos_curent.y])

                if dist_fata_de_lider >= 3.5 and len(self.istoric_puncte) > 5:
                    
                    # PASUL 1: Găsim firimitura cea mai apropiată de drona Follower
                    min_dist = float('inf')
                    idx_cel_mai_apropiat = 0
                    for idx_pct, punct in enumerate(self.istoric_puncte):
                        d = math.dist([punct[0], punct[1]], [pos_curent.x, pos_curent.y])
                        if d < min_dist:
                            min_dist = d
                            idx_cel_mai_apropiat = idx_pct

                    # PASUL 2: Privim ÎNAINTE pe traseu (de la follower spre lider) căutând punctul de Lookahead
                    tinta_curenta = None
                    for idx_pct in range(idx_cel_mai_apropiat, len(self.istoric_puncte)):
                        punct = self.istoric_puncte[idx_pct]
                        d = math.dist([punct[0], punct[1]], [pos_curent.x, pos_curent.y])
                        
                        if d >= 1.5: # Raza de Lookahead (1.5 metri în fața ei pe firimituri)
                            tinta_curenta = punct
                            break
                    
                    # Siguranță: Dacă liderul e aproape și am rămas fără puncte intermediare, îl țintim pe el
                    if not tinta_curenta:
                        tinta_curenta = self.istoric_puncte[-1]

                    unghi_target = math.atan2(tinta_curenta[1] - pos_curent.y, tinta_curenta[0] - pos_curent.x)
                    eroare_unghiulara = math.atan2(math.sin(unghi_target - yaw), math.cos(unghi_target - yaw))
                    dist_target = math.dist([tinta_curenta[0], tinta_curenta[1]], [pos_curent.x, pos_curent.y])

                    if dist_target > 0.2:
                        comanda_vel.linear.x = min(2.5, dist_target * 1.2)
                        comanda_vel.angular.z = max(min(eroare_unghiulara * 2.0, 2.0), -2.0) 
                        self.baterie_virtuala -= ((abs(comanda_vel.linear.x) * 0.01) + (abs(comanda_vel.angular.z) * 0.005))
                
                self.pubs[nume_drona].publish(comanda_vel)

        except ValueError:
            pass

if __name__ == '__main__':
    try:
        nod = SistemNavigatieRoi()
        rospy.spin()
    except rospy.ROSInterruptException:
        pass