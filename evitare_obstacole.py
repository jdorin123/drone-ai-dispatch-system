#!/usr/bin/env python3
import rospy
from sensor_msgs.msg import LaserScan
from geometry_msgs.msg import Twist

class ModulEvitareObstacole:
    """
    Nod responsabil cu evitarea reactiva a obstacolelor, complementand 
    costmap-urile navigatiei globale (A*) cu reactii rapide de urgenta.
    """
    def __init__(self):
        rospy.init_node('sistem_evitare', anonymous=True)
        self.cmd_pub = rospy.Publisher('/cmd_vel', Twist, queue_size=10)
        self.timeout_marsarier = 0.0
        self.factor_viraj_evitare = 1.0
        self.timp_ultim_log = 0.0
        
        rospy.Subscriber('/scan_reflex_lider', LaserScan, self.callback_scan)
        rospy.loginfo("[INIT] Modulul de evitare a obstacolelor a fost pornit. Limita predictiva: 2.0 m/s.")

    def get_distanta_minima(self, vector_scanari):
        """ Filtrare date LIDAR pentru a ignora scanarile eronate """
        # Extragem doar valorile din intervalul util al senzorului
        scanari_valide = [d for d in vector_scanari if 0.25 < d < 10.0]
        return min(scanari_valide) if len(scanari_valide) > 0 else 10.0

    def callback_scan(self, msg):
        # Separarea razei in 3 sectoare critice pentru decizie de viraj
        # Aceste indecsi au fost ajustati experimental pt. 360 grade
        dist_dreapta = self.get_distanta_minima(msg.ranges[100:160])
        dist_fata    = self.get_distanta_minima(msg.ranges[160:200])
        dist_stanga  = self.get_distanta_minima(msg.ranges[200:260])
        
        timp_curent = rospy.get_time()

        # Rutina de degajare prin rulare spate (timeout prioritar)
        if timp_curent < self.timeout_marsarier:
            msg_cmd = Twist()
            msg_cmd.linear.x = -0.5 
            msg_cmd.angular.z = 1.0 * self.factor_viraj_evitare 
            self.cmd_pub.publish(msg_cmd)
            return 

        # Verificare conditie de urgenta majora
        if dist_fata < 1.2:
            rospy.logerr(f"[CRITIC] Distanta insuficienta fata de obstacol: {dist_fata:.2f}m. Initiere manevra degajare.")
            self.timeout_marsarier = timp_curent + 1.0 
            # Decizia de viraj se bazeaza pe spatiul disponibil stanga/dreapta
            self.factor_viraj_evitare = 1.0 if dist_stanga >= dist_dreapta else -1.0
            return 

        # Control redat planner-ului local (navigatie de cursa)
        if dist_fata > 6.0:
            return 

        # Rutina evitare curba fluida (fara oprire completa)
        msg_cmd = Twist()
        
        # Calcul liniar pentru scaderea vitezei proportionale cu distanta fata de perete
        indice_proximitate = (6.0 - dist_fata) / (6.0 - 1.2)
        indice_proximitate = max(0.0, min(1.0, indice_proximitate)) 
        
        msg_cmd.linear.x = 2.0 - (indice_proximitate * 1.7)
        putere_viraj = 0.5 + (indice_proximitate * 1.5)
        
        # Decizie sens de ocolire bazat pe spatiu liber pe laterale
        if dist_stanga > dist_dreapta:
            msg_cmd.angular.z = putere_viraj 
            info_directie = "Stanga"
        else:
            msg_cmd.angular.z = -putere_viraj
            info_directie = "Dreapta"

        # Limitare frecventa log-uri (Throttle) pentru a nu bloca consola
        if timp_curent - self.timp_ultim_log > 0.5:
            rospy.logwarn(f"[EVITARE] Traiectorie corectata ({info_directie}) | D_Fata: {dist_fata:.1f}m | Vit_Lin: {msg_cmd.linear.x:.1f}m/s")
            self.timp_ultim_log = timp_curent

        self.cmd_pub.publish(msg_cmd)

if __name__ == '__main__':
    try:
        nod = ModulEvitareObstacole()
        rospy.spin()
    except rospy.ROSInterruptException:
        pass