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

    # --- Normal phase transitions (called by Intersection) ---

    def set_green(self):
        """It's this signal's normal turn. tick() will count it down."""
        self.state = SignalState.GREEN
        self.time_remaining = self.GREEN_DURATION
        self.is_forced = False

    def set_red(self):
        """This signal is inactive. tick() will still run but it's already RED."""
        self.state = SignalState.RED
        self.time_remaining = self.RED_DURATION
        self.is_forced = False

    # --- Emergency overrides (called by Intersection for emergency vehicles) ---

    def force_green(self):
        """Emergency lock: stays GREEN until explicitly released. tick() is skipped."""
        self.state = SignalState.GREEN
        self.time_remaining = self.GREEN_DURATION
        self.is_forced = True

    def release_force(self):
        """Release emergency lock. Signal goes back to RED and tick() resumes."""
        self.is_forced = False
        self.state = SignalState.RED
        self.time_remaining = self.RED_DURATION

    # --- Bus priority adjustments ---

    def extend_green(self, seconds):
        """Bus is approaching with <=5s remaining. Extend once."""
        if self.state == SignalState.GREEN and not self.is_extended:
            self.time_remaining += seconds
            self.is_extended = True

    def reduce_red(self, seconds):
        """Bus is waiting on red. Shorten the wait, capped at MAX_RED_REDUCTION."""
        if self.state == SignalState.RED:
            reduction = min(seconds, self.MAX_RED_REDUCTION)
            self.time_remaining = max(0, self.time_remaining - reduction)
