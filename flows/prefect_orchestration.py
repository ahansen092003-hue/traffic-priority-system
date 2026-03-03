import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import json
from prefect import flow, task
from scripts.build_map import init_build
from scripts.initialize_graph import build

LOCATION = (72.8056, 18.9778, 72.8389, 19.0167)

@task(name="Build Map", log_prints=True)
def build_map():
    print("Building map visualization...")
    init_build(LOCATION)
    print("Map saved")

@task(name="Initialize Road Graph", log_prints=True)
def initialize_road_graph():
    print("Building road graph from OSM data...")
    return build(LOCATION)

@task(name="Load Bus Routes", log_prints=True)
def load_bus_routes():
    with open('config/bus_routes.json', 'r') as f:
        routes = json.load(f)
    print(f"Loaded {len(routes['routes'])} bus routes")
    return routes
    
@flow(name="initialize graph", log_prints=True)
def setup():
    build_map()
    road_edges = initialize_road_graph()
    routes = load_bus_routes()
    
if __name__ == "__main__":
    setup()