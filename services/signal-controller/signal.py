

class Signal:
    def __init__(self, signal_id, location, state, time_remaining, car_num, bus_num):
        self.signal_id = signal_id
        self.location = location
        self.state = state
        self.time_remaining = time_remaining
        self.car_num = car_num
        self.bus_num = bus_num