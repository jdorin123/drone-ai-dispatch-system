#!/bin/bash

echo "Curatare procese anterioare ROS/Gazebo..."
killall -9 roscore rosmaster gzserver gzclient rviz python3 2>/dev/null
sleep 2

echo "Pornire simulare."

# 1. ROS Master
gnome-terminal --title="ROS_MASTER" -- bash -c "roscore; exec bash" &

echo "Asteptare initializare roscore."
until rostopic list > /dev/null 2>&1; do sleep 1; done

# Sincronizare timp pentru simulator
rosparam set use_sim_time true
echo "ROS Master online."

# 2. Gazebo Server
echo "Lansare gzserver."
gnome-terminal --title="GAZEBO_SERVER" -- bash -c "gzserver --verbose -s libgazebo_ros_api_plugin.so padure_tactica.world; exec bash" &

echo "Asteptare publicare /clock din Gazebo."
until rostopic echo -n 1 /clock > /dev/null 2>&1; do sleep 2; done
echo "Nodul Gazebo ruleaza."

# 3. Navigatie si Vizualizare
echo "Incarcare RViz si noduri navigatie."
gnome-terminal --title="RVIZ_SI_TF" -- bash -c "roslaunch sisteme_3d.launch & roslaunch move_base.launch & rviz -d panou_tactic.rviz; exec bash" &

# 4. Control Swarm, Evitare Obstacole si Autonomie
echo "Lansare scripturi de control."
gnome-terminal --title="CONTROL_SWARM" -- bash -c "python3 dynamic_swarm.py; exec bash" &
gnome-terminal --title="EVITARE_OBSTACOLE" -- bash -c "python3 evitare_obstacole.py; exec bash" &
gnome-terminal --title="AUTONOMIE_RTH" -- bash -c "python3 autonomie_rth.py; exec bash" &

echo "Mediu ROS pregatit. Se poate rula dashboard_tactic.py in terminal separat."