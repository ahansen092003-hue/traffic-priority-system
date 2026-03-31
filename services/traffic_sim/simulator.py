import os
import sys
import time
import json
import queue
import threading

import redis
from fastapi import FastAPI
from pydantic import BaseModel
import uvicorn

import math

SUMO_HOME = os.environ.get(
    'SUMO_HOME',
    '/Library/Frameworks/EclipseSUMO.framework/Versions/1.26.0/EclipseSUMO/share/sumo'
)
sys.path.append(os.path.join(SUMO_HOME, 'tools'))
import traci  # type: ignore

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
SUMO_DIR     = os.path.join(PROJECT_ROOT, 'sumo')
SUMO_CFG     = os.path.join(SUMO_DIR, 'mumbai.sumocfg')
SUMO_BINARY  = '/Library/Frameworks/EclipseSUMO.framework/Versions/1.26.0/EclipseSUMO/bin/sumo'

sys.path.insert(0, PROJECT_ROOT)
from services.traffic_sim.producer import VehicleProducer, VEHICLE_POSITIONS_TOPIC, EMERGENCY_VEHICLES_TOPIC

redis_client = redis.Redis(host='localhost', port=6379, decode_responses=True)
ambulance_queue = queue.Queue()
app = FastAPI()

class SpawnRequest(BaseModel):
    origin_lat:  float
    origin_lon:  float
    dest_lat:    float
    dest_lon:    float
    
@app.post('/ambulance/spawn')
def spawn_ambulance(req: SpawnRequest):
    ambulance_queue.put({
        'origin_lat': req.origin_lat,
        'origin_lon': req.origin_lon,
        'dest_lat':   req.dest_lat,
        'dest_lon':   req.dest_lon,
    })
    return {'status': 'queued', 'message': 'Ambulance spawn request received'}

@app.post('/priority/toggle')
def toggle_priority(enabled: bool):
    redis_client.set('priority_enabled', 'true' if enabled else 'false')
    return {'status': 'ok', 'priority_enabled': enabled}

@app.get('/status')
def get_status():
    raw = redis_client.get('current_state')
    if not raw:
        return {'running': False}
    state = json.loads(raw)
    return {
        'running':       True,
        'step':          state.get('step', 0),
        'vehicle_count': len(state.get('vehicles', [])),
    }

def get_vehicle_type(sumo_type_id: str) -> str:
    t = sumo_type_id.lower()
    if 'bus' in t:
        return 'bus'
    if 'emergency' in t or 'ambulance' in t or 'rescue' in t:
        return 'emergency'
    return 'car'


def state_char_to_color(char: str) -> str:
    # Each character in SUMO's state string maps to one signal head
    # G/g = green, y/Y = yellow, r/R = red
    if char in ('G', 'g'):
        return 'green'
    if char in ('y', 'Y'):
        return 'yellow'
    return 'red'


def get_signal_heads(tl_id: str) -> list:
    """
    Returns one entry per signal head (lane approach) at this intersection.
    Each entry has the real GPS position of that signal head and its state.

    SUMO models each traffic light as a list of controlled links.
    Each link = one lane approach = one signal head.
    getControlledLinks() returns a list of lists — one per signal index.
    Each inner list contains (from_lane, to_lane, via_lane) tuples.
    getRedYellowGreenState() returns a string where each character
    is the state of the corresponding signal index.
    """
    heads = []
    try:
        raw_state = traci.trafficlight.getRedYellowGreenState(tl_id)
        controlled_links = traci.trafficlight.getControlledLinks(tl_id)

        seen_positions = set()

        for i, link_group in enumerate(controlled_links):
            if i >= len(raw_state):
                break
            if not link_group:
                continue

            # Each link_group is a list of (from_lane, to_lane, via_lane)
            # We only need the first one — they share the same signal head
            from_lane = link_group[0][0]

            try:
                # getLaneShape returns a list of (x,y) points along the lane
                # The LAST point is the stop line — where the signal head is
                shape = traci.lane.getShape(from_lane)
                if not shape:
                    continue

                x, y = shape[-1]  # stop line position
                lon, lat = traci.simulation.convertGeo(x, y)

                # Round to 4 decimal places — two signal heads on the same
                # approach share nearly identical positions, deduplicate them
                pos_key = (round(lat, 4), round(lon, 4))
                if pos_key in seen_positions:
                    continue
                seen_positions.add(pos_key)

                heads.append({
                    'tl_id':         tl_id,
                    'signal_index':  i,
                    'lat':           round(lat, 6),
                    'lon':           round(lon, 6),
                    'state':         state_char_to_color(raw_state[i]),
                    'from_lane':     from_lane,
                })

            except traci.exceptions.TraCIException:
                continue

    except traci.exceptions.TraCIException:
        pass

    return heads

def find_signals_on_route(route_edges: list) -> list:
    route_edge_set = set(route_edges)
    signals_on_route = []
    seen_tl_ids = set()

    for tl_id in traci.trafficlight.getIDList():
        if tl_id in seen_tl_ids:
            continue
        try:
            controlled_links = traci.trafficlight.getControlledLinks(tl_id)
        except traci.exceptions.TraCIException:
            continue

        for link_group in controlled_links:
            if not link_group:
                continue
            from_lane = link_group[0][0]
            edge_id   = from_lane.rsplit('_', 1)[0]

            if edge_id in route_edge_set:
                signals_on_route.append({
                    'tl_id':         tl_id,
                    'approach_edge': edge_id,
                })
                seen_tl_ids.add(tl_id)
                break

    return signals_on_route

def force_signal_for_ambulance(tl_id: str, approach_edge: str):
    try:
        raw_state        = traci.trafficlight.getRedYellowGreenState(tl_id)
        controlled_links = traci.trafficlight.getControlledLinks(tl_id)

        new_state = list('r' * len(raw_state))

        for i, link_group in enumerate(controlled_links):
            if i >= len(raw_state):
                break
            if not link_group:
                continue
            from_lane = link_group[0][0]
            edge_id   = from_lane.rsplit('_', 1)[0]
            if edge_id == approach_edge:
                new_state[i] = 'G'

        traci.trafficlight.setRedYellowGreenState(tl_id, ''.join(new_state))

    except traci.exceptions.TraCIException as e:
        print(f"[AMBULANCE] Could not force signal {tl_id}: {e}")
        
def release_signal(tl_id: str):
    try:
        traci.trafficlight.setProgram(tl_id, '0')
        print(f"[AMBULANCE] Released signal {tl_id}")
    except traci.exceptions.TraCIException as e:
        print(f"[AMBULANCE] Could not release signal {tl_id}: {e}")
        
def process_ambulance_spawn(request: dict, counter: list) -> dict | None:
    amb_id = f"ambulance_{counter[0]}"
    counter[0] += 1

    try:
        ox, oy = traci.simulation.convertGeo(
            request['origin_lon'], request['origin_lat'], fromGeo=True
        )
        dx, dy = traci.simulation.convertGeo(
            request['dest_lon'], request['dest_lat'], fromGeo=True
        )

        origin_edge = traci.simulation.convertRoad(ox, oy, isGeo=False)[0]
        dest_edge   = traci.simulation.convertRoad(dx, dy, isGeo=False)[0]

        route_result = traci.simulation.findRoute(origin_edge, dest_edge)
        if not route_result or not route_result.edges:
            print(f"[AMBULANCE] No route found between clicked points")
            return None

        route_edges    = list(route_result.edges)
        signals_on_route = find_signals_on_route(route_edges)

        route_id = f"route_{amb_id}"
        traci.route.add(route_id, route_edges)
        traci.vehicle.add(amb_id, routeID=route_id, typeID='DEFAULT_VEHTYPE')
        traci.vehicle.setColor(amb_id, (255, 50, 50, 255))
        traci.vehicle.setMaxSpeed(amb_id, 20.0)

        for sig in signals_on_route:
            force_signal_for_ambulance(sig['tl_id'], sig['approach_edge'])

        route_data = {
            'ambulance_id':    amb_id,
            'route_edges':     route_edges,
            'signals':         signals_on_route,
            'cleared_signals': [],
            'origin':          [request['origin_lat'], request['origin_lon']],
            'dest':            [request['dest_lat'],   request['dest_lon']],
        }

        redis_client.set(
            f'ambulance:{amb_id}:route',
            json.dumps(route_data)
        )

        print(f"[AMBULANCE] {amb_id} spawned on {len(route_edges)} edges, "
              f"{len(signals_on_route)} signals forced green")
        return route_data

    except traci.exceptions.TraCIException as e:
        print(f"[AMBULANCE] Spawn failed: {e}")
        return None

CLEAR_DISTANCE_M = 80.0


def sig_index_for_tl(tl_id: str):
    try:
        traci.junction.getPosition(tl_id)
        return 0
    except traci.exceptions.TraCIException:
        return None


def apply_signal_command(cmd: dict):
    command = cmd.get('command')
    tl_id   = cmd.get('tl_id')

    if not tl_id:
        return

    try:
        if command == 'bus_priority':
            action = cmd.get('action')
            if action == 'reduce_red':
                traci.trafficlight.setPhase(
                    tl_id,
                    traci.trafficlight.getPhase(tl_id)
                )
            elif action == 'extend_green':
                current_duration = traci.trafficlight.getPhaseDuration(tl_id)
                traci.trafficlight.setPhaseDuration(tl_id, current_duration + 10.0)

        elif command == 'emergency_force':
            approach_edge = cmd.get('approach_edge')
            if approach_edge:
                force_signal_for_ambulance(tl_id, approach_edge)

        elif command == 'emergency_release':
            release_signal(tl_id)

        elif command == 'extend_green':
            seconds = cmd.get('seconds', 10)
            current_duration = traci.trafficlight.getPhaseDuration(tl_id)
            traci.trafficlight.setPhaseDuration(tl_id, current_duration + seconds)

    except traci.exceptions.TraCIException as e:
        print(f"[EXECUTOR] Could not apply command {command} to {tl_id}: {e}")

def run():
    producer        = VehicleProducer()
    signal_cmd_queue = queue.Queue()
    ambulance_counter = [0]
    active_ambulances = {}

    sumo_cmd = [
        SUMO_BINARY,
        '-c', SUMO_CFG,
        '--start',
        '--quit-on-end',
        '--no-step-log',
    ]

    print("Starting SUMO (headless)...")
    traci.start(sumo_cmd)
    print("TraCI connected. Simulation running.")

    # Start FastAPI in a daemon thread
    # uvicorn.run() is blocking — it serves HTTP requests forever.
    # Running it in a daemon thread lets the tick loop run simultaneously.
    # log_level='error' suppresses uvicorn's per-request console output.
    api_thread = threading.Thread(
        target=lambda: uvicorn.run(
            app, host='0.0.0.0', port=8000, log_level='error'
        ),
        daemon=True,
    )
    api_thread.start()
    print("FastAPI server started on http://localhost:8000")

    # Start executor thread — bridges signal-commands Kafka topic to signal_cmd_queue
    from services.signal_controller.executor import run_executor
    executor_thread = threading.Thread(
        target=run_executor,
        args=(signal_cmd_queue,),
        daemon=True,
    )
    executor_thread.start()
    print("Executor thread started.")

    # Initialize priority flag in Redis if not already set
    # This means priority is ON by default when the simulator starts.
    # The dashboard toggle writes to this key to change it.
    if not redis_client.exists('priority_enabled'):
        redis_client.set('priority_enabled', 'true')

    try:
        step = 0

        while traci.simulation.getMinExpectedNumber() > 0:
            traci.simulationStep()

            # --- Process ambulance spawn requests from FastAPI ---
            # get_nowait() returns immediately with queue.Empty if nothing is there.
            # We drain the whole queue in case multiple spawns were queued
            # between ticks (unlikely but possible).
            while not ambulance_queue.empty():
                try:
                    request    = ambulance_queue.get_nowait()
                    route_data = process_ambulance_spawn(request, ambulance_counter)
                    if route_data:
                        active_ambulances[route_data['ambulance_id']] = route_data
                except queue.Empty:
                    break

            # --- Process signal commands from executor thread ---
            # The executor thread puts Kafka signal-commands into signal_cmd_queue.
            # We drain up to 20 commands per tick to avoid stalling the simulation.
            commands_processed = 0
            while not signal_cmd_queue.empty() and commands_processed < 20:
                try:
                    cmd = signal_cmd_queue.get_nowait()
                    apply_signal_command(cmd)
                    commands_processed += 1
                except queue.Empty:
                    break

            # --- Update active ambulance signal states ---
            active_vehicle_ids = set(traci.vehicle.getIDList())
            for amb_id in list(active_ambulances.keys()):

                if amb_id not in active_vehicle_ids:
                    # Ambulance finished its route — release any remaining signals
                    route_data = active_ambulances.pop(amb_id)
                    for sig in route_data['signals']:
                        if sig['tl_id'] not in route_data['cleared_signals']:
                            release_signal(sig['tl_id'])
                    redis_client.delete(f'ambulance:{amb_id}:route')
                    print(f"[AMBULANCE] {amb_id} completed route, all signals released")
                    continue

                # Check each signal on the route —
                # if the ambulance has passed it, release it
                amb_x, amb_y = traci.vehicle.getPosition(amb_id)
                route_data   = active_ambulances[amb_id]

                for sig in route_data['signals']:
                    if sig['tl_id'] in route_data['cleared_signals']:
                        continue

                    # Get signal position
                    sig_index = sig_index_for_tl(sig['tl_id'])
                    if sig_index is None:
                        continue

                    sig_x, sig_y = traci.junction.getPosition(sig['tl_id'])
                    distance     = math.sqrt((amb_x - sig_x)**2 + (amb_y - sig_y)**2)

                    if distance > CLEAR_DISTANCE_M:
                        release_signal(sig['tl_id'])
                        route_data['cleared_signals'].append(sig['tl_id'])

                        # Publish emergency_release to Kafka signal-commands
                        # so the signal controller consumer updates its state
                        producer.publish({
                            'command':        'emergency_release',
                            'tl_id':          sig['tl_id'],
                            'vehicle_id':     amb_id,
                            'issued_at_step': step,
                        }, 'signal-commands')

                        # Update Redis route data
                        redis_client.set(
                            f'ambulance:{amb_id}:route',
                            json.dumps(route_data)
                        )

            # --- Read vehicle and signal states ---
            vehicles = []
            for vid in traci.vehicle.getIDList():
                x, y         = traci.vehicle.getPosition(vid)
                lon, lat     = traci.simulation.convertGeo(x, y)
                speed        = traci.vehicle.getSpeed(vid)
                waiting_time = traci.vehicle.getWaitingTime(vid)
                vtype        = get_vehicle_type(traci.vehicle.getTypeID(vid))

                message = {
                    'vehicle_id':   vid,
                    'vehicle_type': vtype,
                    'lat':          round(lat, 6),
                    'lon':          round(lon, 6),
                    'speed':        round(speed, 2),
                    'time_stopped': round(waiting_time, 2),
                    'step':         step,
                }
                producer.publish(message, VEHICLE_POSITIONS_TOPIC)

                if vtype == 'emergency':
                    producer.publish(message, EMERGENCY_VEHICLES_TOPIC)

                vehicles.append(message)

            signals = []
            for tl_id in traci.trafficlight.getIDList():
                heads = get_signal_heads(tl_id)
                signals.extend(heads)

            # Write state to Redis — replaces the old current_state.json file write.
            # All services (dashboard, status endpoint) read from this key.
            state = {'vehicles': vehicles, 'signals': signals, 'step': step}
            redis_client.set('current_state', json.dumps(state))

            if step % 10 == 0:
                print(f"Step {step} — {len(vehicles)} vehicles, "
                      f"{len(signals)} signal heads, "
                      f"{len(active_ambulances)} active ambulances")

            step += 1
            time.sleep(1.0)

    except KeyboardInterrupt:
        print("\nSimulation interrupted.")
    finally:
        traci.close()
        print("SUMO closed.")

if __name__ == '__main__':
    run()