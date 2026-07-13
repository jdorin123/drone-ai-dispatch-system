#!/usr/bin/env python3
import rospy
from sensor_msgs.msg import LaserScan
from geometry_msgs.msg import Twist

class ModulEvitareObstacole:
    def __init__(self):
        rospy.init_node('sistem_evitare', anonymous=True)
        self.cmd_pub = rospy.Publisher('/cmd_vel', Twist, queue_size=10)
        self.timeout_marsarier = 0.0
        self.factor_viraj_evitare = 1.0
        self.timp_ultim_log = 0.0
        
        rospy.Subscriber('/scan_reflex_lider', LaserScan, self.callback_scan)
        rospy.loginfo("[INIT] Modulul evitare: Con frontal ingustat, predictie setata la 4.5m.")

    def get_distanta_minima(self, vector_scanari):
        # Păstrăm pata oarbă de 0.45m ca să nu își vadă propriul șasiu
        scanari_valide = [d for d in vector_scanari if 0.45 < d < 12.0]
        return min(scanari_valide) if len(scanari_valide) > 0 else 12.0

    def callback_scan(self, msg):
        # 1. Îngustăm conul frontal înapoi la 40 de grade (strict ce e în fața ei)
        dist_dreapta = self.get_distanta_minima(msg.ranges[100:160])
        dist_fata    = self.get_distanta_minima(msg.ranges[160:200])
        dist_stanga  = self.get_distanta_minima(msg.ranges[200:260])
        
        timp_curent = rospy.get_time()

        if timp_curent < self.timeout_marsarier:
            msg_cmd = Twist()
            msg_cmd.linear.x = -0.5 
            msg_cmd.angular.z = 1.0 * self.factor_viraj_evitare 
            self.cmd_pub.publish(msg_cmd)
            return 

        if dist_fata < 1.2:
            rospy.logerr(f"[CRITIC] Impact iminent ({dist_fata:.2f}m). Degajare!")
            self.timeout_marsarier = timp_curent + 1.0 
            self.factor_viraj_evitare = 1.0 if dist_stanga >= dist_dreapta else -1.0
            return 

        # 2. Reducem distanța de panică la 4.5m. Așa lăsăm A*-ul să conducă printre copaci!
        if dist_fata > 4.5:
            return 

        # 3. Frânăm și glisăm DOAR când copacul e cu adevărat pe traiectorie
        msg_cmd = Twist()
        
        indice_proximitate = (4.5 - dist_fata) / (4.5 - 1.2)
        indice_proximitate = max(0.0, min(1.0, indice_proximitate)) 
        
        msg_cmd.linear.x = 2.0 - (indice_proximitate * 1.7)
        putere_viraj = 0.5 + (indice_proximitate * 1.5)
        
        if dist_stanga > dist_dreapta:
            msg_cmd.angular.z = putere_viraj 
            info_directie = "Stanga"
        else:
            msg_cmd.angular.z = -putere_viraj
            info_directie = "Dreapta"

        if timp_curent - self.timp_ultim_log > 0.5:
            rospy.logwarn(f"[EVITARE] Glisare {info_directie} | D_Fata: {dist_fata:.1f}m | Vit: {msg_cmd.linear.x:.1f}m/s")
            self.timp_ultim_log = timp_curent

        self.cmd_pub.publish(msg_cmd)

if __name__ == '__main__':
    try:
        nod = ModulEvitareObstacole()
        rospy.spin()
    except rospy.ROSInterruptException:
        pass