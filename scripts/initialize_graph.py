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
    
def split_and_create_edges(path, graph, signal_list, road_edges):
    segment_start = path[0]
    segment_nodes = [path[0]]
    
    for node in path[1:]: 
        segment_nodes.append(node)
    
        if node in signal_list:
            edge_id = (segment_start, node)
            
            if edge_id not in road_edges:
                total_length = 0
                edge_data = None
                for i in range(len(segment_nodes) - 1):
                    u = segment_nodes[i]
                    v = segment_nodes[i + 1]
                    edge_data = graph[u][v][0] 
                    total_length += edge_data['length']
                
                speed_limit = 11.0  
                if edge_data and 'maxspeed' in edge_data:
                    try:
                        speed_limit = int(edge_data['maxspeed']) / 3.6  # Convert km/h to m/s
                    except (ValueError, TypeError):
                        pass
                road_edge = RoadEdge(segment_start, node, total_length, speed_limit)
                road_edges[edge_id] = road_edge
                
            segment_start = node
            segment_nodes = [node]
    
def build(location):
    mum_map = ox.graph_from_bbox(bbox=(location[0], location[1], location[2], location[3]), network_type='drive', simplify=True)
    

if __name__ == "__main__":
    build((72.8056, 18.9778, 72.8389, 19.0167))