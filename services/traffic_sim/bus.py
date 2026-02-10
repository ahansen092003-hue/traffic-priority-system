

class Bus:
    def __init__(self, bus_id, position, speed, time_stopped, next_sig):
        self.bus_id = bus_id
        self.position = position
        self.speed = speed
        self.time_stopped = time_stopped
        self.next_sig = next_sig
        
    def set_next_signal(self, next_sig):
        pass

    def distance_to_signal(self, signal_position):
        pass