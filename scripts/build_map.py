import osmnx as ox
import folium
import json

with open('config/signal_nodes.json', 'r') as f:
    config = json.load(f)
    signal_list = [signal['id'] for signal in config['signals']]

def build_map(location):
    mum_map = ox.graph_from_bbox(bbox=(location[0], location[1], location[2], location[3]), network_type='drive', simplify=True)
    nodes, edges = ox.graph_to_gdfs(mum_map)
    center_lat = (location[1] + location[3]) / 2  
    center_lon = (location[0] + location[2]) / 2
    m = folium.Map(location=[center_lat, center_lon], zoom_start=14)
    m2 = folium.Map(location=[center_lat, center_lon], zoom_start=14)
    
    for idx, row in edges.iterrows():
        folium.PolyLine(locations=[(coord[1], coord[0]) for coord in row['geometry'].coords], color='blue', weight=2).add_to(m)
        folium.PolyLine(locations=[(coord[1], coord[0]) for coord in row['geometry'].coords], color='blue', weight=2).add_to(m2)

    for idx, row in nodes.iterrows():
        folium.CircleMarker(location=[row['y'], row['x']], radius=3, color='red', popup=str(idx)).add_to(m)
        if idx in signal_list:
            folium.CircleMarker(location=[row['y'], row['x']], radius=3, color='green', popup=str(idx)).add_to(m2)
        
    m.save('map.html')
    m2.save('map_with_signals.html')

if __name__ == "__main__":
    build_map((72.8056, 18.9778, 72.8389, 19.0167))