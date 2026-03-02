class Vehicle:
    speed_multiplier = 1.0
    length = 0.0
    min_gap = 5.0
    vehicle_type = "generic"
    def __init__(self, vehicle_id, time_stopped=0.0):
        self.vehicle_id = vehicle_id
        self.time_stopped = time_stopped
        self.position = 0.0
        
class Car(Vehicle):
    speed_multiplier = 1.0
    min_gap = 3.0
    vehicle_type = "car"
    length = 5.0
    def __init__(self, vehicle_id, time_stopped=0.0):
        super().__init__(vehicle_id, time_stopped)
        
class Bus(Vehicle):
    speed_multiplier = 1.0
    min_gap = 3.0
    vehicle_type = "bus"
    length = 12.0
    
    def __init__(self, vehicle_id, time_stopped=0.0, next_signal=None):
        super().__init__(vehicle_id, time_stopped)
        self.next_signal = next_signal
        
class EmergencyVehicle(Vehicle):
    speed_multiplier = 1.5
    min_gap = 1.0
    vehicle_type = "emergency"
    length = 6.0
    def __init__(self, vehicle_id, time_stopped=0.0, next_signal=None):
        super().__init__(vehicle_id, time_stopped)
        self.next_signal = next_signal
        
        