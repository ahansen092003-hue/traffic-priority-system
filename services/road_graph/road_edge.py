from collections import deque

STOP_DISTANCE = 3.0  # metres before signal line where vehicles stop

class RoadEdge:
    def __init__(self, start_node, end_node, length, speed_limit, signal=None):
        self.start_node = start_node
        self.end_node = end_node
        self.length = length
        self.speed_limit = speed_limit
        self.signal = signal  # Signal object at end_node, set by initialize_intersections

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
        vehicles_list = list(self.vehicle_queue)

        for vehicle_index, vehicle in enumerate(vehicles_list):
            current_position = self.positions[vehicle]
            speed = self.speed_limit * vehicle.speed_multiplier
            desired_distance = speed * time_step

            if vehicle_index == 0:
                # Leading vehicle — check signal state
                if self.signal and self.signal.state.value == "red":
                    max_position = self.length - STOP_DISTANCE
                else:
                    max_position = self.length
            else:
                # Following vehicle — stop behind the vehicle ahead
                vehicle_ahead = vehicles_list[vehicle_index - 1]
                ahead_position = self.positions[vehicle_ahead]
                max_position = ahead_position - vehicle_ahead.length - vehicle.min_gap

            new_position = min(current_position + desired_distance, max_position)
            new_position = max(new_position, current_position)  # never go backwards
            self.positions[vehicle] = new_position
            vehicle.position = new_position

    def get_vehicle_counts(self):
        counts = {'cars': 0, 'buses': 0, 'emergency': 0}
        for vehicle in self.vehicle_queue:
            if vehicle.vehicle_type in counts:
                counts[vehicle.vehicle_type] += 1
        return counts
