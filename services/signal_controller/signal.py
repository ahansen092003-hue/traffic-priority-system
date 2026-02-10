import time

class Signal:
    def __init__(self, signal_id, location):
        self.signal_id = signal_id
        self.location = location
        self.time_remaining = None
        self.car_num = None
        self.bus_num = None
        self.north = bool
        self.south = bool
        self.east = bool
        self.west = bool
        self.bus_priority = bool
        self.emergency_priority = bool
        
    def distance_to_vehicle(self, vehicle_position):
        pass