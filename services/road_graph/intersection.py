from services.road_graph.signal import Signal, SignalState


class Intersection:
    def __init__(self, intersection_id, location):
        self.intersection_id = intersection_id
        self.location = location
        self.signals = []
        self.active_index = 0
        self.emergency_active = False

    def add_signal(self, signal: Signal):
        self.signals.append(signal)

    def start(self):
        """Call once after all signals are added to kick off the first GREEN."""
        if self.signals:
            self._activate(0)

    def _activate(self, index):
        """
        Normal phase transition: set one signal GREEN, all others RED.
        Uses set_green/set_red so tick() still controls the countdown.
        Never called during an emergency.
        """
        for i, signal in enumerate(self.signals):
            if i == index:
                signal.set_green()
            else:
                signal.set_red()
        self.active_index = index

    def tick(self, time_step):
        """
        Called every simulation tick by the signal controller.
        Skipped during an emergency — forced signal stays GREEN
        until release_emergency() is called.
        """
        if not self.signals or self.emergency_active:
            return

        active_signal = self.signals[self.active_index]
        active_signal.tick(time_step)

        if active_signal.state == SignalState.RED:
            next_index = (self.active_index + 1) % len(self.signals)
            self._activate(next_index)

    def force_green(self, signal_id):
        """
        Emergency override: lock one signal GREEN, all others RED.
        tick() is paused for this intersection until release_emergency().
        """
        found = False
        for i, signal in enumerate(self.signals):
            if signal.signal_id == signal_id:
                signal.force_green()
                self.active_index = i
                found = True
            else:
                signal.set_red()

        if not found:
            raise ValueError(
                f"Signal {signal_id} not found in intersection {self.intersection_id}"
            )

        self.emergency_active = True

    def release_emergency(self):
        """
        Emergency cleared. Release forced signal, resume normal cycling
        from the next signal in sequence.
        """
        current = self.signals[self.active_index]
        current.release_force()
        self.emergency_active = False
        next_index = (self.active_index + 1) % len(self.signals)
        self._activate(next_index)

    def get_state(self):
        """Snapshot of all signal states. Signal controller publishes this to Kafka."""
        return {
            signal.signal_id: {
                "state": signal.state.value,
                "time_remaining": round(signal.time_remaining, 2),
                "is_forced": signal.is_forced,
            }
            for signal in self.signals
        }
