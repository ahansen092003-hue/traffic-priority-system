

class Emergency_Veh:
    def __init__(self, emV_id, position, speed, time_stopped, next_sig):
        self.emV_id = emV_id
        self.position = position
        self.speed = speed
        self.time_stopped = time_stopped
        self.next_sig = next_sig

    def update_position(self, new_position):
        pass
    
    def set_next_signal(self, next_sig):
        pass
    
    def distance_to_signal(self, signal_position):
        pass