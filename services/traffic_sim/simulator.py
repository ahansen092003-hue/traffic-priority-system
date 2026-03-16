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
# Headless binary — no display/XQuartz needed at all
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


def get_signal_state(raw: str) -> str:
    if 'G' in raw or 'g' in raw:
        return 'green'
    if 'y' in raw or 'Y' in raw:
        return 'yellow'
    return 'red'


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

            signals = []
            for tl_id in traci.trafficlight.getIDList():
                try:
                    x, y      = traci.junction.getPosition(tl_id)
                    lon, lat  = traci.simulation.convertGeo(x, y)
                    raw_state = traci.trafficlight.getRedYellowGreenState(tl_id)
                    signals.append({
                        'tl_id': tl_id,
                        'lat':   round(lat, 6),
                        'lon':   round(lon, 6),
                        'state': get_signal_state(raw_state),
                    })
                except traci.exceptions.TraCIException:
                    continue

            state = {'vehicles': vehicles, 'signals': signals, 'step': step}
            with open(STATE_FILE, 'w') as f:
                json.dump(state, f)

            if step % 10 == 0:
                print(f"Step {step} — {len(vehicles)} vehicles, {len(signals)} signals")

            step += 1
            time.sleep(1.0)

    except KeyboardInterrupt:
        print("\nSimulation interrupted.")
    finally:
        traci.close()
        print("SUMO closed.")


if __name__ == '__main__':
    run()
