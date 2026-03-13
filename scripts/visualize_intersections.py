import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import json
import folium
import osmnx as ox

# 15 visually distinct colours — one per intersection
COLOURS = [
    '#e6194b', '#3cb44b', '#4363d8', '#f58231', '#911eb4',
    '#42d4f4', '#f032e6', '#bfef45', '#fabed4', '#469990',
    '#dcbeff', '#9A6324', '#fffac8', '#800000', '#aaffc3',
]

def build_intersection_map():
    with open('config/intersections.json', 'r') as f:
        intersections = json.load(f)['intersections']

    with open('config/signal_nodes.json', 'r') as f:
        signal_list = [s['id'] for s in json.load(f)['signals']]

    # signal_id → intersection index for quick lookup
    signal_to_intersection = {}
    for i, intersection in enumerate(intersections):
        for signal_id in intersection['signals']:
            signal_to_intersection[signal_id] = i

    print("Downloading OSMnx graph to get node coordinates...")
    bbox = (72.8056, 18.9778, 72.8389, 19.0167)
    graph = ox.graph_from_bbox(
        bbox=(bbox[0], bbox[1], bbox[2], bbox[3]),
        network_type='drive',
        simplify=True
    )
    nodes, edges = ox.graph_to_gdfs(graph)

    center_lat = (bbox[1] + bbox[3]) / 2
    center_lon = (bbox[0] + bbox[2]) / 2
    m = folium.Map(location=[center_lat, center_lon], zoom_start=15)

    # Faint road network background
    for _, row in edges.iterrows():
        folium.PolyLine(
            locations=[(coord[1], coord[0]) for coord in row['geometry'].coords],
            color='lightgray',
            weight=1,
            opacity=0.4
        ).add_to(m)

    # Signal nodes coloured by intersection group
    for signal_id in signal_list:
        if signal_id not in nodes.index:
            print(f"Warning: signal {signal_id} not found in graph nodes")
            continue

        lat = nodes.loc[signal_id]['y']
        lon = nodes.loc[signal_id]['x']
        intersection_index = signal_to_intersection.get(signal_id)

        if intersection_index is None:
            colour = '#808080'
            label = f"Unassigned: {signal_id}"
        else:
            colour = COLOURS[intersection_index % len(COLOURS)]
            intersection = intersections[intersection_index]
            name = intersection['name'] if intersection['name'] else f"Intersection {intersection_index + 1}"
            label = f"{name}<br>Signal ID: {signal_id}<br>Signals in group: {len(intersection['signals'])}"

        folium.CircleMarker(
            location=[lat, lon],
            radius=10,
            color=colour,
            fill=True,
            fill_color=colour,
            fill_opacity=0.9,
            tooltip=folium.Tooltip(label)
        ).add_to(m)

    # Legend
    legend_html = '<div style="position:fixed;bottom:40px;left:40px;z-index:1000;background:white;padding:12px;border-radius:8px;border:1px solid #ccc;font-size:13px;">'
    legend_html += '<b>Intersections</b><br>'
    for i, intersection in enumerate(intersections):
        colour = COLOURS[i % len(COLOURS)]
        name = intersection['name'] if intersection['name'] else f"Intersection {i + 1}"
        n = len(intersection['signals'])
        legend_html += f'<span style="color:{colour};font-size:18px;">&#9679;</span> {name} ({n} signal{"s" if n > 1 else ""})<br>'
    legend_html += '</div>'
    m.get_root().html.add_child(folium.Element(legend_html))

    m.save('intersection_groups.html')
    print("Map saved to intersection_groups.html — open in your browser to verify groupings")

if __name__ == "__main__":
    build_intersection_map()
