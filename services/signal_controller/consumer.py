import os
import sys
import json
import math
import time
import threading
import redis

redis_client = redis.Redis(host='localhost', port=6379, decode_responses=True)

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from confluent_kafka import Consumer, KafkaError

KAFKA_CONFIG = {
    'bootstrap.servers': 'localhost:9092',
    'group.id':          'signal-controller-group',
    'auto.offset.reset': 'latest',
}

VEHICLE_POSITIONS_TOPIC  = 'vehicle-positions'
APPROACH_DISTANCE_M      = 50.0
CLEAR_DISTANCE_M         = 80.0
BUS_WAIT_THRESHOLD_S     = 15.0
BUS_REISSUE_INTERVAL     = 30

def haversine_distance(lat1: float, lon1: float,
                       lat2: float, lon2: float) -> float:
    R       = 6_371_000
    phi1    = math.radians(lat1)
    phi2    = math.radians(lat2)
    d_phi   = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = (math.sin(d_phi / 2) ** 2
         + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def load_signal_index(redis_client) -> dict:
    try:
        raw = redis_client.get('current_state')
        if not raw:
            return {}
        state = json.loads(raw)
    except Exception:
        return {}

    tl_positions = {}
    for head in state.get('signals', []):
        tl_id = head['tl_id']
        if tl_id not in tl_positions:
            tl_positions[tl_id] = []
        tl_positions[tl_id].append((head['lat'], head['lon']))

    index = {}
    for tl_id, positions in tl_positions.items():
        avg_lat = sum(p[0] for p in positions) / len(positions)
        avg_lon = sum(p[1] for p in positions) / len(positions)
        index[tl_id] = (avg_lat, avg_lon)

    return index

def find_nearest_signal(vehicle_lat: float, vehicle_lon: float,
                        signal_index: dict) -> tuple:
    nearest_id   = None
    nearest_dist = float('inf')

    for tl_id, (sig_lat, sig_lon) in signal_index.items():
        dist = haversine_distance(vehicle_lat, vehicle_lon, sig_lat, sig_lon)
        if dist < nearest_dist:
            nearest_dist = dist
            nearest_id   = tl_id

    return nearest_id, nearest_dist

def run_emergency_consumer(command_producer):
    config = {
        'bootstrap.servers': 'localhost:9092',
        'group.id':          'emergency-signal-group',
        'auto.offset.reset': 'latest',
    }
    consumer = Consumer(config)
    consumer.subscribe(['emergency-vehicles'])

    signal_index       = {}
    last_index_rebuild = 0.0

    print("Emergency consumer started. Listening on emergency-vehicles...")

    try:
        while True:
            msg = consumer.poll(timeout=1.0)

            now = time.time()
            if now - last_index_rebuild > 10.0:
                signal_index       = load_signal_index(redis_client)
                last_index_rebuild = now

            if msg is None:
                continue
            if msg.error():
                if msg.error().code() == KafkaError._PARTITION_EOF:
                    continue
                print(f"Emergency consumer error: {msg.error()}")
                continue

            vehicle    = json.loads(msg.value().decode('utf-8'))
            vehicle_id = vehicle['vehicle_id']
            step       = vehicle['step']

            # Check if priority is enabled
            priority_enabled = redis_client.get('priority_enabled') == 'true'

            # Check if this vehicle has an active route in Redis
            route_raw = redis_client.get(f'ambulance:{vehicle_id}:route')

            if not priority_enabled and route_raw:
                # Priority has been toggled OFF while an ambulance is active.
                # Publish emergency_release for every uncleared signal on its route
                # so the simulator's forced signals get restored to normal.
                route_data = json.loads(route_raw)
                cleared    = set(route_data.get('cleared_signals', []))

                for sig in route_data.get('signals', []):
                    if sig['tl_id'] not in cleared:
                        print(
                            f"[PRIORITY OFF] Releasing {sig['tl_id']} "
                            f"for {vehicle_id}"
                        )
                        command_producer.publish({
                            'command':        'emergency_release',
                            'tl_id':          sig['tl_id'],
                            'vehicle_id':     vehicle_id,
                            'issued_at_step': step,
                        })

            elif priority_enabled and route_raw:
                route_data = json.loads(route_raw)
                remaining  = len(route_data.get('signals', [])) - \
                             len(route_data.get('cleared_signals', []))
                print(
                    f"[EMERGENCY] {vehicle_id} active — "
                    f"{remaining} signals remaining on route (step {step})"
                )

    except KeyboardInterrupt:
        pass
    finally:
        consumer.close()
        print("Emergency consumer closed.")


def run_bus_consumer(command_producer):
    config = {
        'bootstrap.servers': 'localhost:9092',
        'group.id':          'bus-signal-group',
        'auto.offset.reset': 'latest',
    }
    consumer = Consumer(config)
    consumer.subscribe([VEHICLE_POSITIONS_TOPIC])

    bus_priority_sent  = {}
    signal_index       = {}
    last_index_rebuild = 0.0

    print("Bus consumer started. Listening on vehicle-positions...")

    try:
        while True:
            msg = consumer.poll(timeout=1.0)

            now = time.time()
            if now - last_index_rebuild > 10.0:
                signal_index       = load_signal_index(redis_client)
                last_index_rebuild = now

            if msg is None:
                continue
            if msg.error():
                if msg.error().code() == KafkaError._PARTITION_EOF:
                    continue
                print(f"Bus consumer error: {msg.error()}")
                continue

            vehicle      = json.loads(msg.value().decode('utf-8'))
            vehicle_type = vehicle['vehicle_type']

            if vehicle_type != 'bus':
                continue

            vehicle_id   = vehicle['vehicle_id']
            v_lat        = vehicle['lat']
            v_lon        = vehicle['lon']
            time_stopped = vehicle['time_stopped']
            step         = vehicle['step']

            if not signal_index:
                continue

            nearest_tl, distance = find_nearest_signal(v_lat, v_lon, signal_index)
            if nearest_tl is None:
                continue

            if distance > APPROACH_DISTANCE_M:
                continue

            priority_key  = (vehicle_id, nearest_tl)
            last_sent     = bus_priority_sent.get(priority_key, -999)
            recently_sent = (step - last_sent) < BUS_REISSUE_INTERVAL

            if recently_sent:
                continue

            if time_stopped >= BUS_WAIT_THRESHOLD_S:
                print(f"[BUS] {vehicle_id} stopped {time_stopped}s at {nearest_tl} — requesting reduce_red")
                command_producer.publish({
                    'command':        'bus_priority',
                    'action':         'reduce_red',
                    'tl_id':          nearest_tl,
                    'vehicle_id':     vehicle_id,
                    'time_stopped':   time_stopped,
                    'issued_at_step': step,
                })
                bus_priority_sent[priority_key] = step

            elif time_stopped == 0.0:
                print(f"[BUS] {vehicle_id} approaching {nearest_tl} ({distance:.1f}m) — requesting extend_green")
                command_producer.publish({
                    'command':        'bus_priority',
                    'action':         'extend_green',
                    'tl_id':          nearest_tl,
                    'vehicle_id':     vehicle_id,
                    'distance_m':     round(distance, 1),
                    'issued_at_step': step,
                })
                bus_priority_sent[priority_key] = step

    except KeyboardInterrupt:
        pass
    finally:
        consumer.close()
        print("Bus consumer closed.")


def run():
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
    from services.signal_controller.producer import SignalCommandProducer

    command_producer = SignalCommandProducer()

    emergency_thread = threading.Thread(
        target=run_emergency_consumer,
        args=(command_producer,),
        daemon=True,
    )

    bus_thread = threading.Thread(
        target=run_bus_consumer,
        args=(command_producer,),
        daemon=True,
    )

    emergency_thread.start()
    bus_thread.start()

    print("Signal controller running. Press Ctrl+C to stop.")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down signal controller.")


if __name__ == '__main__':
    run()