import os
import sys
import time
import json

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
STATE_FILE   = os.path.join(SUMO_DIR, 'current_state.json')

sys.path.insert(0, PROJECT_ROOT)
from services.traffic_sim.producer import VehicleProducer  # noqa: E402


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


def run():
    producer = VehicleProducer()

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

    try:
        step = 0

        while traci.simulation.getMinExpectedNumber() > 0:
            traci.simulationStep()

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
                producer.publish(message)
                vehicles.append(message)

            # Collect individual signal heads for all traffic lights
            signals = []
            for tl_id in traci.trafficlight.getIDList():
                heads = get_signal_heads(tl_id)
                signals.extend(heads)

            state = {'vehicles': vehicles, 'signals': signals, 'step': step}
            with open(STATE_FILE, 'w') as f:
                json.dump(state, f)

            if step % 10 == 0:
                print(f"Step {step} — {len(vehicles)} vehicles, {len(signals)} signal heads")

            step += 1
            time.sleep(1.0)

    except KeyboardInterrupt:
        print("\nSimulation interrupted.")
    finally:
        traci.close()
        print("SUMO closed.")


if __name__ == '__main__':
    run()