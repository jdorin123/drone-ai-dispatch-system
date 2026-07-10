#!/usr/bin/env python3
import random
import math

NUM_TREES = 1200      
MAP_SIZE = 300        # Trebuie sa corespunda cu param width/height din global_costmap
TREE_RADIUS = 0.25        
TREE_HEIGHT = 8.0     

BASE_X = -45
BASE_Y = 0
SAFE_RADIUS_BASE = 5.0

world_content = """<?xml version="1.0" ?>
<sdf version="1.5">
  <world name="padure_tactica">
    <include><uri>model://sun</uri></include>
    <include><uri>model://ground_plane</uri></include>
"""

for i in range(NUM_TREES):
    while True:
        x = random.uniform(-MAP_SIZE/2, MAP_SIZE/2)
        y = random.uniform(-MAP_SIZE/2, MAP_SIZE/2)
        
        # Evitare spawn in zona heliportului (baza de lansare a roiului)
        if math.dist((x, y), (BASE_X, BASE_Y)) > SAFE_RADIUS_BASE:
            break 

    tree_xml = f"""
    <model name='tree_{i}'>
      <static>true</static> <pose>{x:.2f} {y:.2f} {TREE_HEIGHT/2} 0 0 0</pose> 
      <link name='link'>
        <collision name='collision'><geometry><cylinder><radius>{TREE_RADIUS}</radius><length>{TREE_HEIGHT}</length></cylinder></geometry></collision>
        <visual name='visual'><geometry><cylinder><radius>{TREE_RADIUS}</radius><length>{TREE_HEIGHT}</length></cylinder></geometry>
        <material><script><uri>file://media/materials/scripts/gazebo.material</uri><name>Gazebo/Wood</name></script></material></visual>
      </link>
    </model>
    """
    world_content += tree_xml

world_content += "</world></sdf>"

try:
    with open("padure_tactica.world", "w", encoding="utf-8") as f:
        f.write(world_content)
    print(f"Harta generata cu succes. Total elemente generate: {NUM_TREES}")
except Exception as e:
    print(f"Eroare la scrierea fisierului world: {e}")