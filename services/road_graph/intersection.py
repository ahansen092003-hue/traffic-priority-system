from services.signal_controller.signal import Signal

class Intersection:
    def __init__(self, intersection_id, location):
        self.intersection_id = intersection_id
        self.location = location
        self.signals = []

    def add_signal(self, signal):
        self.signals.append(signal)
