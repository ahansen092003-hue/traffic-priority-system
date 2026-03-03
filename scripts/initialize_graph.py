import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import osmnx as ox
import json
import folium
from services.road_graph.road_edge import RoadEdge
    
##HELPER
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
                        speed_limit = int(edge_data['maxspeed']) / 3.6
                    except (ValueError, TypeError):
                        pass
                road_edge = RoadEdge(segment_start, node, total_length, speed_limit)
                road_edges[edge_id] = road_edge
                
            segment_start = node
            segment_nodes = [node]
    
def build(location):
    with open('config/signal_nodes.json', 'r') as f:
        config = json.load(f)
        signal_list = [signal['id'] for signal in config['signals']]
        
    mum_map = ox.graph_from_bbox(bbox=(location[0], location[1], location[2], location[3]), network_type='drive', simplify=True)
    
    road_edges = {}
    paths = {}
    
    for signal_a in signal_list:
        for signal_b in signal_list:
            if signal_a == signal_b:
                continue
            try:
                path = ox.shortest_path(mum_map, signal_a, signal_b, weight='length')
                
                if path:
                    paths[(signal_a, signal_b)] = path
                    split_and_create_edges(path, mum_map, signal_list, road_edges)
            except Exception as e:
                print(f"Error finding path between {signal_a} and {signal_b}: {e}")
                continue
    
    print(f"Created {len(road_edges)} RoadEdge objects connecting signals")
    
    nodes, edges = ox.graph_to_gdfs(mum_map)
    
    center_lat = (location[1] + location[3]) / 2  
    center_lon = (location[0] + location[2]) / 2
    m = folium.Map(location=[center_lat, center_lon], zoom_start=14)
    
    for idx, row in edges.iterrows():
        folium.PolyLine(
            locations=[(coord[1], coord[0]) for coord in row['geometry'].coords],
            color='lightblue',
            weight=1,
            opacity=0.3
        ).add_to(m)
    
    for edge_id, road_edge in road_edges.items():
        u, v = edge_id
        
        
        path = paths.get((u, v))
        
        if path:
            for i in range(len(path) - 1):
                node_u = path[i]
                node_v = path[i + 1]
                
                if mum_map.has_edge(node_u, node_v):
                    edge_data = mum_map[node_u][node_v][0]
                    if 'geometry' in edge_data:
                        coords = [(coord[1], coord[0]) for coord in edge_data['geometry'].coords]
                    else:
                        coords = [[nodes.loc[node_u]['y'], nodes.loc[node_u]['x']], 
                                [nodes.loc[node_v]['y'], nodes.loc[node_v]['x']]]
                    
                    folium.PolyLine(locations=coords, color='green', weight=4).add_to(m)
    
    for node_id in signal_list:
        if node_id in nodes.index:
            folium.CircleMarker(
                location=[nodes.loc[node_id]['y'], nodes.loc[node_id]['x']],
                radius=8,
                color='red',
                fill=True
            ).add_to(m)
    
    m.save('filtered_edges.html')
    print("Visualization saved to filtered_edges.html")
    
    return road_edges

if __name__ == "__main__":
    build((72.8056, 18.9778, 72.8389, 19.0167))