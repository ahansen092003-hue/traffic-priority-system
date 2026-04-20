# Plan: PostgreSQL Bus Routes Database

## Context

Buses currently have no route, stop, or schedule concept in the system — they're anonymous vehicles whose positions are detected in real-time from Kafka and matched to the nearest signal using Haversine distance. This plan adds a PostgreSQL database to hold static bus route definitions, stop locations, schedules, and live run state. The signal controller can then make richer priority decisions (e.g., deprioritize a bus that's ahead of schedule, extend green longer for a bus that's severely delayed).

---

## Schema

```sql
CREATE TABLE routes (
    route_id    SERIAL PRIMARY KEY,
    name        TEXT NOT NULL,          -- e.g. "34 - Worli–Lower Parel"
    description TEXT
);

CREATE TABLE stops (
    stop_id          SERIAL PRIMARY KEY,
    route_id         INT REFERENCES routes(route_id),
    intersection_id  TEXT NOT NULL,     -- matches SUMO tl_id, e.g. "152326244#0"
    sequence_order   INT NOT NULL,
    UNIQUE (route_id, sequence_order)
);

CREATE TABLE schedules (
    schedule_id       SERIAL PRIMARY KEY,
    route_id          INT REFERENCES routes(route_id),
    departure_time    TIME NOT NULL,    -- first stop departure
    frequency_minutes INT NOT NULL      -- headway
);

CREATE TABLE bus_runs (
    run_id         SERIAL PRIMARY KEY,
    route_id       INT REFERENCES routes(route_id),
    vehicle_id     TEXT NOT NULL,       -- matches vehicle_id in Kafka stream
    started_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    current_stop   INT REFERENCES stops(stop_id),
    delay_seconds  INT NOT NULL DEFAULT 0
);

CREATE INDEX idx_stops_intersection ON stops(intersection_id);
CREATE INDEX idx_bus_runs_vehicle   ON bus_runs(vehicle_id);
```

**Key join**: `stops.intersection_id` ↔ SUMO `tl_id` values (the signal index keys in Redis, format `"152326244#0"`). This is how a bus near a signal maps to a route and schedule.

---

## New Files to Create

### `services/bus_routes/db.py` — connection + queries

```python
import psycopg2, os

def get_conn():
    return psycopg2.connect(os.environ["DATABASE_URL"])

def get_route_for_stop(intersection_id: str) -> dict | None:
    """Look up route and schedule for a given SUMO tl_id."""

def get_active_run(vehicle_id: str) -> dict | None:
    """Fetch current bus_run for a vehicle_id."""

def upsert_run(vehicle_id: str, route_id: int, current_stop: int, delay_seconds: int):
    """Create or update a bus_run row."""
```

### `services/bus_routes/migrations/001_initial.sql` — the schema above

### `services/bus_routes/seed.py` — populate routes + stops from SUMO signal coordinates

Reads the Redis signal index (same `load_signal_index()` used in `consumer.py`) and inserts representative routes and stops so the database isn't empty on first run.

---

## Files to Modify

### `services/signal_controller/consumer.py`

Enrich the bus consumer loop to:
1. On each bus event, call `get_active_run(vehicle_id)` from `db.py`
2. If a run exists, use `delay_seconds` to weight the priority decision:
   - Delay > 120s → increase priority (shorter reduce_red threshold: 10s instead of 15s)
   - Bus ahead of schedule → skip extend_green even if within 50m
3. When a bus clears a stop (distance > `CLEAR_DISTANCE_M`), call `upsert_run()` to advance `current_stop` and recalculate `delay_seconds` against the schedule

### `docker-compose.yml` — add PostgreSQL

```yaml
postgres:
  image: postgres:16
  environment:
    POSTGRES_DB: bus_routes
    POSTGRES_USER: traffic
    POSTGRES_PASSWORD: traffic
  ports: ["5432:5432"]
  volumes:
    - ./services/bus_routes/migrations/001_initial.sql:/docker-entrypoint-initdb.d/001_initial.sql
```

### `requirements.txt` — add

```
psycopg2-binary>=2.9
```

---

## Run Order

```bash
docker compose up -d                    # starts postgres; migration runs automatically on first boot
python services/bus_routes/seed.py      # populate routes + stops
python -m services.signal_controller.consumer  # now reads postgres for delay weighting
```

---

## Verification

1. Connect to postgres: `docker exec -it postgres psql -U traffic bus_routes`
2. Confirm schema: `\dt` should show all 4 tables
3. Run seed: `python services/bus_routes/seed.py`, then `SELECT count(*) FROM stops;`
4. Start simulator + consumer, spawn buses
5. Query live runs: `SELECT vehicle_id, delay_seconds, current_stop FROM bus_runs;` — rows should appear and `delay_seconds` should update as buses move through stops
