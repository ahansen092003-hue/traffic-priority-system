# Mumbai Traffic Signal Optimization System

A distributed real-time traffic signal optimization system for the
Worli–Mahalaxmi–Lower Parel corridor in Mumbai, India.

Built entirely outside of coursework to learn production-grade distributed
systems — Kafka, Apache Pinot, Redis, FastAPI, Docker, Kubernetes, and SUMO.

---

## Architecture

```
SUMO (physics engine)
    └── TraCI bridge
            └── simulator.py  ←─────────────────────────────────────┐
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

Cloud deployment:
    Terraform → provisions GKE cluster (us-central1-a, 2× e2-standard-2 nodes)
    Kubernetes → deploys all services onto the cluster
    Prefect    → orchestrates full lifecycle (provision → deploy → run → teardown)
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

**Why Terraform over manual GKE setup?** Infrastructure is declared as code
in four `.tf` files. `terraform apply` provisions the cluster in ~12 minutes.
`terraform destroy` tears it down completely with no orphaned resources.
State is tracked in `terraform.tfstate` so every apply is idempotent.

**Why separate Terraform and Kubernetes?** Terraform owns infrastructure
lifetime (cluster exists or not). Kubernetes owns service runtime (what runs
on the cluster). Prefect owns workflow orchestration (when and in what order).
Each tool does one thing well.

---

## Running Locally (Docker Compose)

### Prerequisites

- Docker Desktop
- SUMO 1.26.0 at `/Library/Frameworks/EclipseSUMO.framework/`
- Python 3.10+ with `pip install -r requirements.txt`

### Step 1 — Start infrastructure

```bash
docker compose up -d
```

Starts Zookeeper, Kafka, Redis, Pinot (controller + broker + server), and
`pinot-init` which uploads schemas and tables automatically. Wait ~30 seconds
for Pinot to initialize before starting the simulator.

### Step 2 — Start the simulator

```bash
python -m services.traffic_sim.simulator
```

Starts SUMO headless, connects via TraCI, launches FastAPI on :8000, and
starts the executor thread listening on `signal-commands`.

### Step 3 — Start the signal controller (separate terminal)

```bash
python -m services.signal_controller.consumer
```

Must run alongside the simulator. Runs two Kafka consumers:
- Emergency consumer: watches `emergency-vehicles`, handles priority-toggle-off
- Bus consumer: watches `vehicle-positions`, issues green-extend / red-reduce
  commands to `signal-commands`, which the executor picks up

### Step 4 — Start the dashboard

```bash
streamlit run services/dashboard/app.py
```

Live PyDeck map at http://localhost:8501. Use the sidebar to spawn ambulances
and toggle signal priority.

---

## Cloud Deployment (GKE)

### Prerequisites

- Google Cloud account with billing enabled
- `gcloud` CLI authenticated: `gcloud auth login && gcloud auth application-default login`
- `terraform` >= 1.0
- `kubectl` and `gke-gcloud-auth-plugin`

### Step 1 — Provision the GKE cluster with Terraform

```bash
cd terraform
terraform init     # downloads Google provider plugin
terraform plan     # dry run — shows what will be created
terraform apply    # provisions cluster (~12 minutes)
```

Creates: one GKE cluster and one node pool (2× `e2-standard-2` nodes) in
`us-central1-a`. Cost is ~$0.14/hour while running.

### Step 2 — Configure kubectl

```bash
gcloud container clusters get-credentials traffic-priority-cluster \
  --zone us-central1-a --project traffic-priority-ahan
kubectl get nodes   # should show 2 nodes in Ready state
```

### Step 3 — Deploy services to the cluster

```bash
kubectl apply -f k8s/
kubectl get pods -w   # watch pods reach Running state
```

Deploys: Zookeeper, Kafka (with external LoadBalancer), Redis, Pinot
(controller + broker + server), and pinot-init Job. All services use
Kubernetes DNS for discovery (`kafka:29092`, `zookeeper:2181`, etc.).

### Step 4 — Tear down

```bash
kubectl delete -f k8s/     # remove all services
cd terraform
terraform destroy           # delete the GKE cluster and nodes
```

---

## Key Design Decisions

### Emergency vehicle preemption
Signals along the ambulance's full route are forced green at spawn time,
not reactively as it approaches. Each signal is released individually once
the ambulance has first approached within 40m then passed 80m beyond it —
preventing premature release of signals the ambulance hasn't reached yet.

### Bus priority
The bus consumer detects two scenarios:
- Bus **moving** and within 50m of a signal → `extend_green` (+10s)
- Bus **stopped** at a signal for >15s → `reduce_red` (cut remaining red by 5s)

### TraCI threading constraint
SUMO's TraCI library allows only one active connection and all calls must
happen on the thread that called `traci.start()`. The executor runs as a
thread inside the simulator process, receiving commands from Kafka via a
thread-safe `queue.Queue`, which the main TraCI loop drains each step.

### Kafka key ordering guarantee
Signal commands are keyed by `tl_id` in `signal_controller/producer.py`.
Kafka routes all messages with the same key to the same partition, so all
commands for a given intersection are consumed in order — a `force_green`
can never arrive after its corresponding `release`.

### Terraform + Kubernetes separation
Terraform manages infrastructure lifetime (when the cluster exists).
Kubernetes manages service runtime (what runs on the cluster).
This separation means the cluster config can be updated independently of
the application manifests, and either layer can be torn down without
affecting the other.

---

## Project Structure

```
traffic-priority-system/
├── docker-compose.yml              # Local infrastructure (Kafka, Redis, Pinot)
├── requirements.txt
├── sumo/
│   ├── mumbai.net.xml              # Road network — Worli–Lower Parel corridor
│   ├── mumbai.rou.xml              # Vehicle routes and demand
│   └── mumbai.sumocfg              # SUMO configuration
├── pinot/
│   ├── schema.json                 # vehicle_positions schema (ts as time column)
│   ├── table.json                  # vehicle_positions REALTIME table
│   ├── emergency_schema.json       # emergency_vehicles schema
│   └── emergency_table.json        # emergency_vehicles REALTIME table
├── services/
│   ├── traffic_sim/
│   │   ├── simulator.py            # SUMO + TraCI + FastAPI + executor thread
│   │   └── producer.py             # Kafka producer (vehicle-positions, emergency-vehicles)
│   ├── signal_controller/
│   │   ├── consumer.py             # Emergency + bus Kafka consumers (separate process)
│   │   ├── producer.py             # Signal command producer (keyed by tl_id)
│   │   └── executor.py             # Kafka → in-process queue → TraCI commands
│   └── dashboard/
│       └── app.py                  # Streamlit + PyDeck live map
├── terraform/
│   ├── versions.tf                 # Provider versions and Google provider config
│   ├── variables.tf                # Project ID, region, zone, machine type
│   ├── main.tf                     # GKE cluster + node pool resource definitions
│   └── outputs.tf                  # Cluster name, endpoint, kubectl config command
├── k8s/
│   ├── zookeeper.yaml              # Deployment + headless Service
│   ├── kafka.yaml                  # Deployment + internal Service + LoadBalancer Service
│   ├── redis.yaml                  # Deployment + ClusterIP Service
│   ├── pinot-controller.yaml       # Deployment + ClusterIP Service
│   ├── pinot-broker.yaml           # Deployment + ClusterIP Service
│   ├── pinot-server.yaml           # Deployment + ClusterIP Service
│   └── pinot-init.yaml             # ConfigMap (schemas) + Job (uploads to Pinot)
├── flows/                          # Prefect orchestration flows (in progress)
└── legacy/                         # Pre-SUMO custom simulator (osmnx/NetworkX)
```

---

## Stack

| Technology | Role |
|---|---|
| SUMO 1.26.0 | Traffic physics engine |
| TraCI | Python bridge to SUMO |
| Apache Kafka | Ordered event streaming between simulator and signal controller |
| Apache Pinot | Real-time OLAP on vehicle stream data |
| Redis | Cross-process shared state (sim state, ambulance routes) |
| FastAPI | HTTP API for ambulance spawn and priority toggle |
| Streamlit + PyDeck | Live map dashboard |
| Docker Compose | Local infrastructure orchestration |
| Terraform | GKE cluster provisioning (infrastructure as code) |
| Kubernetes (GKE) | Cloud container orchestration |
| Prefect | Workflow orchestration — provision, deploy, run, teardown (in progress) |
| Claude API | LLM-based signal timing reasoning (in progress) |
| ChromaDB | RAG memory for agent past decisions (in progress) |
