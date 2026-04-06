# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This System Does

Real-time traffic signal optimization for 18 intersections in the Worli–Mahalaxmi–Lower Parel corridor in Mumbai. The system dynamically adjusts signals to prioritize emergency vehicles (ambulances) and public transit (buses) using a distributed architecture: SUMO physics simulation → Kafka event streaming → signal controller logic → TraCI signal commands.

## Running the System Locally

**Prerequisites:**
- Docker Desktop running
- SUMO 1.26.0 installed at `/Library/Frameworks/EclipseSUMO.framework/`
- Python 3.10+: `pip install -r requirements.txt`

**Start order (each in its own terminal):**
```bash
# 1. Infrastructure
docker compose up -d

# 2. Simulator (TraCI + FastAPI on :8000)
python -m services.traffic_sim.simulator

# 3. Signal controller
python -m services.signal_controller.consumer

# 4. Dashboard (http://localhost:8501)
streamlit run services/dashboard/app.py
```

## Cloud Deployment (GKE)

```bash
# Provision GKE cluster (~12 minutes)
cd terraform && terraform init && terraform apply

# Configure kubectl
gcloud container clusters get-credentials traffic-priority-cluster \
  --zone us-central1-a --project traffic-priority-ahan

# Deploy all services
kubectl apply -f k8s/
kubectl get pods -w

# Teardown
kubectl delete -f k8s/
terraform destroy
```

## Architecture

### Data Flow

```
SUMO Simulator (simulator.py)
  ├── TraCI (single-threaded — all SUMO calls must happen here)
  ├── FastAPI :8000 (ambulance spawn, priority toggle)
  └── Executor thread (drains signal-commands queue → TraCI calls)
        ↑
        └── Kafka: signal-commands topic (keyed by tl_id)
                ↑
          Signal Controller (consumer.py)
            ├── Emergency consumer ← Kafka: emergency-vehicles topic
            └── Bus consumer ← Kafka: vehicle-positions topic

Simulator → Redis: current_state (every step)
Redis → Dashboard: polling every 2s
Simulator → Pinot: vehicle_positions + emergency_vehicles (real-time OLAP)
```

### Critical Threading Constraint

TraCI (SUMO's Python API) is **not thread-safe** — all TraCI calls must occur on the main simulator thread. This is why:
- The executor (`services/signal_controller/executor.py`) puts commands into a `queue.Queue`
- The main simulator loop drains that queue each step and applies commands via TraCI
- The FastAPI server and Kafka consumer run in separate threads but never call TraCI directly

### Kafka Topic Design

| Topic | Key | Purpose |
|---|---|---|
| `vehicle-positions` | `vehicle_id` | All vehicle positions every sim step |
| `emergency-vehicles` | `vehicle_id` | Ambulance events only |
| `signal-commands` | `tl_id` | Signal control commands (keyed for ordering) |

Keying `signal-commands` by `tl_id` ensures all commands for a given intersection are consumed in order — prevents "force_green arriving after release."

### Services

- **`services/traffic_sim/simulator.py`** — Main simulator loop with TraCI, FastAPI server, and executor consumer thread
- **`services/traffic_sim/producer.py`** — Kafka producer for vehicle/emergency events
- **`services/signal_controller/consumer.py`** — Two consumers (emergency + bus) that compute priority decisions using Haversine distance
- **`services/signal_controller/producer.py`** — Publishes signal commands keyed by intersection
- **`services/signal_controller/executor.py`** — Thread-safe queue that bridges Kafka consumer → TraCI main thread
- **`services/dashboard/app.py`** — Streamlit + PyDeck live map, polls Redis

### Infrastructure

- **`docker-compose.yml`** — Local: Zookeeper, Kafka (9092), Redis (6379), Pinot (controller 9000, broker 8099)
- **`k8s/`** — GKE manifests for all services; `pinot-init.yaml` auto-uploads Pinot schemas via Job
- **`terraform/`** — GKE cluster on `us-central1-a`, 2× `e2-standard-2` nodes, project `traffic-priority-ahan`
- **`sumo/`** — SUMO network (`mumbai.net.xml`), routes (`mumbai.rou.xml`), config (`mumbai.sumocfg`)
- **`pinot/`** — Schema + REALTIME table definitions for `vehicle_positions` and `emergency_vehicles`

### Planned but Not Implemented

- **`flows/`** — Prefect workflow orchestration (directory exists, empty)
- **Claude API + ChromaDB** — LLM-based signal timing reasoning with RAG memory (`anthropic` and `chromadb` are in `requirements.txt` but not yet wired up)

## No Tests or Linting

There are currently no test files, test runners, or linting configurations in this project.
