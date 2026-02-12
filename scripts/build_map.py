import osmnx as ox
import folium  

def build_map(location):
    
    mum_map = ox.graph_from_bbox(bbox=(location[0], location[1], location[2], location[3]), network_type='drive', simplify=True)
    FM_mum_map = ox.plot_graph_folium(mum_map, popup_attribute='name', weight=2, color='blue')
    FM_mum_map.save('map.html')
    
if __name__ == "__main__":
    worli_coords = (19.0167, 18.9778, 72.8389, 72.8056)
    build_map(worli_coords)