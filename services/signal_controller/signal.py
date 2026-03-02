import time

class Signal:
    def __init__(self, signal_id, location):
        self.signal_id = signal_id
        self.location = location
        self.time_remaining = None
        self.car_num = None
        self.bus_num = None
        self.north = False
        self.south = False
        self.east = False
        self.west = False
        self.bus_priority = False
        self.emergency_priority = False
        
    def distance_to_vehicle(self, vehicle_position):
        pass