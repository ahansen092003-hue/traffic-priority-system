import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import osmnx as ox
import json
import folium
from services.road_graph.road_edge import RoadEdge

with open('config/signal_nodes.json', 'r') as f:
    config = json.load(f)
    signal_list = [signal['id'] for signal in config['signals']]
    
def build(location):
    mum_map = ox.graph_from_bbox(bbox=(location[0], location[1], location[2], location[3]), network_type='drive', simplify=True)
    

if __name__ == "__main__":
    build((72.8056, 18.9778, 72.8389, 19.0167))