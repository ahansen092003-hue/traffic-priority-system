from enum import Enum

class SignalState(Enum):
    RED = "red"
    GREEN = "green"
    
class Signal:
    GREEN_DURATION = 30.0
    RED_DURATION = 30.0
    MAX_RED_REDUCTION = 10.0
    def __init__(self, signal_id, location):
        self.signal_id = signal_id
        self.location = location
        self.state = SignalState.RED
        self.time_remaining = self.RED_DURATION
        self.is_extended = False
        self.is_forced = False
    
    def tick(self, time_step):
        if self.is_forced:
            return
            
        self.time_remaining -= time_step
        
        if self.time_remaining <= 0:
            if self.state == SignalState.GREEN:
                self.state = SignalState.RED
                self.time_remaining = self.RED_DURATION
                self.is_extended = False
            else:
                self.state = SignalState.GREEN
                self.time_remaining = self.GREEN_DURATION
                
    def force_green(self):
        self.state = SignalState.GREEN
        self.time_remaining = self.GREEN_DURATION
        self.is_forced = True

    def release_force(self):
        self.is_forced = False
        self.state = SignalState.RED
        self.time_remaining = self.RED_DURATION
        
    def extend_green(self, seconds):
        if self.state == SignalState.GREEN and not self.is_extended:
            self.time_remaining += seconds
            self.is_extended = True

    def reduce_red(self, seconds):
        if self.state == SignalState.RED:
            reduction = min(seconds, self.MAX_RED_REDUCTION)
            self.time_remaining = max(0, self.time_remaining - reduction)