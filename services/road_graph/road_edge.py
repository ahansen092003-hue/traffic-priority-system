from collections import deque

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
        for vehicle_index, vehicle in enumerate(vehicles_list):
            current_position = self.positions[vehicle]
            speed = self.speed_limit * vehicle.speed_multiplier
                
            desired_distance = speed * time_step
            if vehicle_index > 0:
                vehicle_ahead = vehicles_list[vehicle_index - 1]
                ahead_position = self.positions[vehicle_ahead]
                ahead_length = vehicle_ahead.length
                    
                min_gap = vehicle.min_gap
                    
                max_position = ahead_position - ahead_length - min_gap
            else:
                max_position = self.length
                
            self.positions[vehicle] = min(current_position + desired_distance, max_position)
            vehicle.position = self.positions[vehicle]
                
    def get_vehicle_counts(self):
        cars = 0
        buses = 0
        emergency = 0
    
        for vehicle in self.vehicle_queue:
            if vehicle.vehicle_type == "bus":
                buses += 1
            elif vehicle.vehicle_type == "emergency":
                emergency += 1
            elif vehicle.vehicle_type == "car":
                cars += 1
    
        return {'cars': cars, 'buses': buses, 'emergency': emergency}