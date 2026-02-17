from collections import deque
from services.traffic_sim.emergency_veh import Emergency_Veh

class RoadEdge:
    def __init__(self, start_node, end_node, length, speed_limit):
        self.start_node = start_node 
        self.end_node = end_node 
        self.length = length     
        self.speed_limit = speed_limit
        
        self.vehicle_queue = deque()
        self.positions = {}
        
    def add_vehicle(self, vehicle):
        self.vehicle_queue.append(vehicle)
        self.positions[vehicle] = 0.0
        
    def remove_vehicle(self, vehicle):
        if vehicle in self.vehicle_queue:
            self.vehicle_queue.remove(vehicle)
            del self.positions[vehicle]
            
    def update_positions(self, time_step):
        vehicles_list = list(self.vehicle_queue)
        for vehicle in vehicles_list:
            current_position = self.positions[vehicle]
            if isinstance(vehicle, Emergency_Veh):
                speed = self.speed_limit * 1.5
            else:
                speed = self.speed_limit
                
            desired_distance = speed * time_step
            vehicle_index = vehicles_list.index(vehicle)
            if vehicle_index > 0:
                vehicle_ahead = vehicles_list[vehicle_index - 1]
                ahead_position = self.positions[vehicle_ahead]
                
                if hasattr(vehicle_ahead, 'bus_id'):
                    ahead_length = 10.0
                elif hasattr(vehicle_ahead, 'car_id'):
                    ahead_length = 5.0
                elif hasattr(vehicle_ahead, 'emV_id'):
                    ahead_length = 6.0
                    
                if isinstance(vehicle, Emergency_Veh):
                    min_gap = 2
                else:
                    min_gap = 5
                    
                max_position = ahead_position - ahead_length - min_gap
            else:
                max_position = self.length
                
            self.positions[vehicle] = min(current_position + desired_distance, max_position)
            if hasattr(vehicle, 'position'):
                vehicle.position = self.positions[vehicle]
                
    def get_vehicle_counts(self):
        cars = 0
        buses = 0
        emergency = 0
    
        for vehicle in self.vehicle_queue:
            if hasattr(vehicle, 'bus_id'):
                buses += 1
            elif hasattr(vehicle, 'emV_id'):
                emergency += 1
            elif hasattr(vehicle, 'car_id'):
                cars += 1
    
        return {'cars': cars, 'buses': buses, 'emergency': emergency}