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
        for vehicle in list(self.vehicle_queue):
            
            pass