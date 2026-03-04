import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

import time
import random
from services.traffic_sim.vehicle import Car, Bus
from services.traffic_sim.producer import VehicleProducer

TIME_STEP = 1.0

def spawn_buses(routes, road_edges):
    buses = {}
    
    for route in routes['routes']:
        route_id = route['route_id']
        signals = route['signals']
        
        for i in range(len(signals) - 1):
            start = signals[i]
            end = signals[i + 1]
            edge_key = (start, end)
            
            if edge_key in road_edges:
                bus_id = f"bus_{route_id}_{i}"
                bus = Bus(vehicle_id=bus_id, next_signal=end)
                road_edges[edge_key].add_vehicle(bus)
                buses[bus_id] = {
                    'vehicle': bus,
                    'edge_key': edge_key,
                    'route': signals,
                    'route_index': i
                }
    
    return buses

def spawn_cars(road_edges, num_cars=20):
    cars = {}
    edge_keys = list(road_edges.keys())
    
    for i in range(num_cars):
        edge_key = random.choice(edge_keys)
        car_id = f"car_{i}_{int(time.time())}"
        car = Car(vehicle_id=car_id)
        road_edges[edge_key].add_vehicle(car)
        cars[car_id] = {
            'vehicle': car,
            'edge_key': edge_key
        }
    
    return cars

def build_message(vehicle, edge_key):
    return {
        'vehicle_id': vehicle.vehicle_id,
        'vehicle_type': vehicle.vehicle_type,
        'position': round(vehicle.position, 2),
        'edge': f"{edge_key[0]}_{edge_key[1]}",
        'next_signal': getattr(vehicle, 'next_signal', None),
        'time_stopped': round(vehicle.time_stopped, 2),
        'timestamp': time.time()
    }

def handle_bus_transition(vid, data, road_edges, buses):
    route_signals = data['route']
    next_index = data['route_index'] + 1
    
    if next_index < len(route_signals) - 1:
        next_edge_key = (route_signals[next_index], route_signals[next_index + 1])
        if next_edge_key in road_edges:
            vehicle = data['vehicle']
            vehicle.next_signal = route_signals[next_index + 1]
            road_edges[next_edge_key].add_vehicle(vehicle)
            buses[vid]['edge_key'] = next_edge_key
            buses[vid]['route_index'] = next_index
    else:
        del buses[vid]

def handle_car_replacement(vid, cars, road_edges):
    del cars[vid]
    new_edge_key = random.choice(list(road_edges.keys()))
    new_car_id = f"car_{int(time.time())}_{random.randint(0, 999)}"
    new_car = Car(vehicle_id=new_car_id)
    road_edges[new_edge_key].add_vehicle(new_car)
    cars[new_car_id] = {
        'vehicle': new_car,
        'edge_key': new_edge_key
    }

def run(road_edges, routes):
    producer = VehicleProducer()
    buses = spawn_buses(routes, road_edges)
    cars = spawn_cars(road_edges, num_cars=20)
    
    print(f"Simulation started: {len(buses)} buses, {len(cars)} cars")
    
    while True:
        prev_positions = {
            vid: data['vehicle'].position
            for vid, data in {**buses, **cars}.items()
        }
        
        for edge in road_edges.values():
            edge.update_positions(TIME_STEP)
        
        all_vehicles = {**buses, **cars}
        
        for vid, data in list(all_vehicles.items()):
            vehicle = data['vehicle']
            edge_key = data['edge_key']
            edge = road_edges[edge_key]
            
            if round(vehicle.position, 4) == round(prev_positions[vid], 4):
                vehicle.time_stopped += TIME_STEP
            else:
                vehicle.time_stopped = 0.0
            
            producer.publish(build_message(vehicle, edge_key))
            
            if vehicle.position >= edge.length - vehicle.length:
                edge.remove_vehicle(vehicle)
                if vehicle.vehicle_type == 'bus':
                    handle_bus_transition(vid, data, road_edges, buses)
                else:
                    handle_car_replacement(vid, cars, road_edges)
        
        time.sleep(TIME_STEP)