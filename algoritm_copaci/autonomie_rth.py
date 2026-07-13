#!/usr/bin/env python3
import rospy
import math
from geometry_msgs.msg import PoseStamped
from actionlib_msgs.msg import GoalStatusArray

class RTHAutomat:
    def __init__(self):
        rospy.init_node('sistem_rth_automat', anonymous=True)
        
        # Publisher pentru a trimite drona înapoi
        self.pub_goal = rospy.Publisher('/move_base_simple/goal', PoseStamped, queue_size=1)
        
        # Ascultăm unde pleacă drona și care este statusul ei
        rospy.Subscriber('/move_base_simple/goal', PoseStamped, self.goal_callback)
        rospy.Subscriber('/move_base/status', GoalStatusArray, self.status_callback)
        
        self.zbor_spre_victima = False
        self.id_misiune_curenta = ""
        
        rospy.loginfo("🛸 Sistem RTH Automat Activat! Aștept lansarea misiunii din Dispecer...")

    def goal_callback(self, msg):
        # Verificăm dacă drona a fost trimisă spre o victimă sau înapoi la bază (-45, 0)
        distanta_fata_de_baza = math.dist([msg.pose.position.x, msg.pose.position.y], [-45.0, 0.0])
        
        if distanta_fata_de_baza > 5.0:
            self.zbor_spre_victima = True
            rospy.loginfo(f"📍 Destinație nouă detectată (Distanță: {distanta_fata_de_baza:.1f}m). Trec în modul MONITORIZARE.")
        else:
            self.zbor_spre_victima = False
            rospy.loginfo("🏠 Destinația curentă este Baza. Aștept aterizarea...")

    def status_callback(self, msg):
        if not msg.status_list:
            return
            
        ultimul_status = msg.status_list[-1]
        
        # Verificăm dacă drona a ajuns cu succes la destinație (Status 3 = SUCCEEDED în ROS)
        if ultimul_status.status == 3 and self.zbor_spre_victima:
            # Ne asigurăm că declanșăm RTH-ul o singură dată per misiune
            if ultimul_status.goal_id.id != self.id_misiune_curenta:
                self.id_misiune_curenta = ultimul_status.goal_id.id
                self.zbor_spre_victima = False 
                
                rospy.loginfo("✅ Pachet ajuns la victimă! Drona livrează pachetul (Așteptare 10 secunde)...")
                rospy.sleep(10.0) # Timpul mort pentru descărcare
                
                self.trimite_la_baza()

    def trimite_la_baza(self):
        rospy.logwarn("🔄 Timp expirat! Inițiez protocolul automat RTH (Return-To-Home)!")
        
        goal_msg = PoseStamped()
        goal_msg.header.stamp = rospy.Time.now()
        goal_msg.header.frame_id = "map" 
        
        # Coordonatele Bazei (Heliportul tău de lansare)
        goal_msg.pose.position.x = -45.0
        goal_msg.pose.position.y = 0.0
        goal_msg.pose.position.z = 0.0
        goal_msg.pose.orientation.w = 1.0 
        
        self.pub_goal.publish(goal_msg)

if __name__ == '__main__':
    try:
        RTHAutomat()
        rospy.spin()
    except rospy.ROSInterruptException:
        pass