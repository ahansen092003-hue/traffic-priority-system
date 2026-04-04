# Mumbai Traffic Signal Optimization System

A distributed real-time traffic signal optimization system for the
Worli–Mahalaxmi–Lower Parel corridor in Mumbai, India.

Built entirely outside of coursework to learn production-grade distributed
systems — Kafka, Apache Pinot, Redis, FastAPI, Docker, and SUMO.

---

## Architecture

```
SUMO (physics engine)
    └── TraCI bridge
            └── simulator.py  ←─────────────────────────────────────-┐
                    ├── Kafka producer → vehicle-positions           │
                    ├── Kafka producer → emergency-vehicles          │
                    ├── Redis writer  → current_state (per step)     │
                    ├── FastAPI :8000 → /ambulance/spawn             │
                    │                   /priority/toggle             │
                    │                   /status                      │
                    └── executor thread (Kafka consumer)             │
                            └── signal-commands topic ───────────────┘
                                        ↑
                            consumer.py (separate process)
                                ├── emergency consumer (emergency-vehicles)
                                └── bus consumer (vehicle-positions)

Apache Pinot  ←── Kafka (vehicle-positions, emergency-vehicles)
    └── OLAP queries: avg speed per intersection, congestion history

dashboard/app.py  ←── Redis (current_state, ambulance:*:route keys)
    └── Streamlit + PyDeck live map
```

**Why Kafka?** The signal controller (`consumer.py`) runs as a separate
process from the simulator. Kafka gives us a durable, ordered message bus
between them. Signal commands are keyed by `tl_id` so all commands for the
same intersection land in the same partition — guaranteeing they're consumed
in order (no force-green arriving after a release).

**Why Redis?** TraCI requires all calls on one thread (SUMO's constraint).
Redis lets the dashboard and the API read the current simulation state without
touching the TraCI thread. Ambulance routes are also stored here so the
dashboard can render them without a Kafka consumer.

**Why Pinot?** Pinot is an OLAP engine built for real-time time-series
analytics on high-throughput event streams. It ingests directly from Kafka and
makes sub-second aggregation queries possible (e.g. avg speed per intersection
over the last 5 minutes).

---

## Running the System

### Prerequisites

- Docker Desktop (for Kafka, Zookeeper, Redis, Pinot)
- SUMO 1.26.0 installed at `/Library/Frameworks/EclipseSUMO.framework/`
- Python 3.10+ with dependencies: `pip install -r requirements.txt`

### Step 1 — Start infrastructure

```bash
docker compose up -d
```

This starts: Zookeeper, Kafka, Redis, Pinot (controller + broker + server),
and the `pinot-init` container which uploads schemas and tables automatically.

Wait ~30 seconds for Pinot to initialize before starting the simulator.

### Step 2 — Start the simulator

```bash
python -m services.traffic_sim.simulator
```

This starts SUMO headless, connects via TraCI, launches FastAPI on :8000,
and starts the executor thread listening on the `signal-commands` Kafka topic.

### Step 3 — Start the signal controller (separate terminal)

```bash
python -m services.signal_controller.consumer
```

This is a **separate process** that must run alongside the simulator.
It runs two Kafka consumers:
- Emergency consumer: watches `emergency-vehicles`, handles priority-toggle-off
- Bus consumer: watches `vehicle-positions`, issues green-extend / red-reduce
  commands to the `signal-commands` topic, which the executor picks up.

### Step 4 — Start the dashboard

```bash
streamlit run services/dashboard/app.py
```

Opens a live PyDeck map at http://localhost:8501 showing vehicle positions,
signal states, and ambulance routes. Use the sidebar to spawn an ambulance
and toggle signal priority.

---

## Key Design Decisions

### Emergency vehicle preemption
Signals along the ambulance's full route are forced green **at spawn time**,
not reactively as it approaches. This prevents the ambulance from ever hitting
a red light mid-route. Signals are released individually as the ambulance
passes each junction (distance threshold: 80m past the junction centre).

### Bus priority
The bus consumer detects two scenarios:
- Bus **moving** and within 50m of a signal → `extend_green` (+10s)
- Bus **stopped** at a signal for >15s → `reduce_red` (cut remaining red by 5s)

### TraCI threading constraint
SUMO's TraCI library allows only one active connection, and all TraCI calls
must happen on the thread that called `traci.start()`. This is why the executor
runs as a thread *inside* the simulator process rather than as a separate
service — it receives commands from Kafka via a thread-safe queue, then the
main loop (on the TraCI thread) applies them.

---

## Project Structure

```
traffic-priority-system/
├── docker-compose.yml          # Zookeeper, Kafka, Redis, Pinot, pinot-init
├── requirements.txt
├── sumo/
│   ├── mumbai.net.xml          # Road network for Worli–Lower Parel corridor
│   ├── mumbai.rou.xml          # Vehicle routes and demand
│   └── mumbai.sumocfg          # SUMO config
├── pinot/
│   ├── schema.json             # vehicle_positions schema (ts as time column)
│   ├── table.json              # vehicle_positions REALTIME table
│   ├── emergency_schema.json   # emergency_vehicles schema
│   └── emergency_table.json    # emergency_vehicles REALTIME table
├── services/
│   ├── traffic_sim/
│   │   ├── simulator.py        # Main entry point: SUMO + TraCI + FastAPI + executor
│   │   └── producer.py         # Kafka producer for vehicle-positions / emergency-vehicles
│   ├── signal_controller/
│   │   ├── consumer.py         # Emergency + bus Kafka consumers (run separately)
│   │   ├── producer.py         # Kafka producer for signal-commands (keyed by tl_id)
│   │   └── executor.py         # Kafka consumer → in-process queue → TraCI commands
│   └── dashboard/
│       └── app.py              # Streamlit + PyDeck live map
├── flows/                      # Prefect orchestration flows (in progress)
└── legacy/                     # Pre-SUMO custom simulator (osmnx/NetworkX approach)
```

---

## Stack

| Technology | Role |
|---|---|
| SUMO 1.26.0 | Traffic physics engine |
| TraCI | Python bridge to SUMO |
| Apache Kafka | Message bus between controller and simulator |
| Apache Pinot | Real-time OLAP on vehicle stream data |
| Redis | Cross-process shared state (current sim state, ambulance routes) |
| FastAPI | HTTP API for ambulance spawn and priority toggle |
| Streamlit + PyDeck | Live map dashboard |
| Docker Compose | Local infrastructure orchestration |
| Prefect | Flow orchestration (in progress) |
| Claude API | LLM-based signal timing reasoning (in progress) |
