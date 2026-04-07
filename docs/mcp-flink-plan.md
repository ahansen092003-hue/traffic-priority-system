# Plan: MCP + Claude API + Apache Flink as Intelligent Signal Controller

## Context

The project already has `anthropic` and `chromadb` in `requirements.txt` but nothing wired up. The goal is to wire Claude into the signal control loop using MCP tools (Pinot queries, Redis reads, Kafka writes). Apache Flink sits between Kafka and Claude: it processes the raw vehicle-position stream cheaply, detects meaningful traffic events (new ambulance, bus stuck, congestion building), and publishes those to a `claude-triggers` topic. Claude only runs inference when Flink says something interesting happened — plus a periodic heartbeat for general optimization. This avoids calling Claude on every simulation step while still reacting in near-real-time to incidents.

---

## Architecture

```
vehicle-positions (Kafka)  ─┐
emergency-vehicles (Kafka) ─┤─▶ Flink Job ──▶ claude-triggers (Kafka)
                             │                        │
                             │                 ┌──────▼──────────┐
                             │                 │  Claude Agent   │
                             │                 │  (agent.py)     │
                             │                 │  + periodic 60s │
                             │                 └──────┬──────────┘
                             │                        │ (MCP tools)
                             │              ┌─────────┼──────────┐
                             │              ▼         ▼          ▼
                             │           Pinot      Redis     Kafka
                             │                                   │
                             │                        signal-commands (Kafka)
                             │                                   ▼
                             └─────────────────────────── Executor → TraCI
```

---

## New Files to Create

### 1. `services/flink_processor/job.py` — PyFlink streaming job

Consumes `vehicle-positions` and `emergency-vehicles`, applies windowed event detection, publishes to `claude-triggers`.

**Detects and emits:**
- `new_ambulance` — first appearance of an ambulance `vehicle_id` in the stream
- `bus_stuck` — bus `time_stopped` > 15s sustained in a 20s tumbling window
- `congestion_zone` — average speed across vehicles in a lat/lon grid cell drops below threshold in a 30s window

Each event payload: `{"event_type": ..., "vehicle_id": ..., "tl_id": ..., "lat": ..., "lon": ..., "ts": ...}`

### 2. `services/claude_controller/server.py` — MCP server

Exposes 5 tools Claude can call during an inference turn:

| Tool | Data source | Purpose |
|---|---|---|
| `query_vehicle_positions(vehicle_type, seconds)` | Pinot `:8099` | Recent positions by type |
| `query_emergency_vehicles(seconds)` | Pinot `:8099` | Active ambulances |
| `get_current_state()` | Redis `current_state` | Signal phases + all vehicles snapshot |
| `get_ambulance_route(ambulance_id)` | Redis `ambulance:{id}:route` | Route + cleared signals |
| `issue_signal_command(tl_id, command, action, vehicle_id, step)` | Kafka `signal-commands` (keyed by `tl_id`) | Publish a command |

Valid `command` values: `bus_priority`, `emergency_force`, `emergency_release`  
Valid `action` values (for `bus_priority`): `extend_green`, `reduce_red`

### 3. `services/claude_controller/agent.py` — Claude inference loop

Two trigger paths that both invoke the same Claude turn:
1. **Flink trigger**: consumes `claude-triggers` Kafka topic — fires immediately on each event
2. **Periodic heartbeat**: runs every 60s regardless — catches anything Flink missed

Each Claude turn:
- Connects to MCP server via stdio transport
- Sends a user message with the triggering event as context
- Handles `tool_use` blocks in a loop until Claude stops calling tools
- Logs the reasoning and all commands issued

```python
SYSTEM_PROMPT = """
You are a real-time traffic signal controller for 18 intersections in Mumbai's
Worli–Mahalaxmi–Lower Parel corridor. You receive alerts from a Flink stream processor
and can query real-time traffic data and issue signal commands.

Signal command rules:
- Ambulances: highest priority — verify route via get_ambulance_route, issue emergency_force
  for each signal ahead, emergency_release for signals the ambulance has passed (> 80m behind)
- Buses stopped > 15s at a signal: bus_priority with action reduce_red
- Buses approaching within 50m and moving: bus_priority with action extend_green
- Always call get_current_state first to understand current signal phases before issuing commands
"""
```

---

## Infrastructure Changes

### `docker-compose.yml` — add Flink

```yaml
jobmanager:
  image: flink:1.18-scala_2.12-java11
  ports: ["8081:8081"]
  command: jobmanager
  environment:
    FLINK_PROPERTIES: "jobmanager.rpc.address: jobmanager"

taskmanager:
  image: flink:1.18-scala_2.12-java11
  depends_on: [jobmanager]
  command: taskmanager
  environment:
    FLINK_PROPERTIES: "jobmanager.rpc.address: jobmanager\ntaskmanager.numberOfTaskSlots: 4"
```

### `requirements.txt` — add

```
mcp>=1.0.0
apache-flink>=1.18.0
```

### `k8s/` — add (for GKE)
- `flink-jobmanager.yaml`
- `flink-taskmanager.yaml`
- `claude-controller.yaml` (agent + MCP server as sidecar or separate pod)

---

## Files to Modify

- `docker-compose.yml` — add Flink jobmanager + taskmanager services
- `requirements.txt` — add `mcp>=1.0.0`, `apache-flink>=1.18.0`

## Files to Create

- `services/flink_processor/job.py`
- `services/claude_controller/server.py`
- `services/claude_controller/agent.py`

---

## Run Order (updated)

```bash
# 1. Infrastructure (includes Flink now)
docker compose up -d

# 2. Simulator
python -m services.traffic_sim.simulator

# 3. Rule-based signal controller (unchanged)
python -m services.signal_controller.consumer

# 4. Submit Flink job
flink run -py services/flink_processor/job.py

# 5. Claude agent (MCP server launched as subprocess)
python -m services.claude_controller.agent

# 6. Dashboard
streamlit run services/dashboard/app.py
```

---

## Verification

1. Spawn an ambulance: `POST http://localhost:8000/ambulance/spawn`
2. Flink should detect the new ambulance and emit to `claude-triggers` within ~1s
3. Claude agent should receive the trigger, call `get_ambulance_route`, then issue `emergency_force` commands
4. Confirm commands in Kafka: `docker exec kafka kafka-console-consumer.sh --topic signal-commands --bootstrap-server localhost:9092`
5. Confirm signals change on the dashboard at `http://localhost:8501`
6. Monitor Flink job UI at `http://localhost:8081`
