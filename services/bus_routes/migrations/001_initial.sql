CREATE TABLE routes (
    route_id    SERIAL PRIMARY KEY,
    name        TEXT NOT NULL,
    description TEXT
);

CREATE TABLE stops (
    stop_id          SERIAL PRIMARY KEY,
    route_id         INT REFERENCES routes(route_id),
    intersection_id  TEXT NOT NULL,
    sequence_order   INT NOT NULL,
    UNIQUE (route_id, sequence_order)
);

CREATE TABLE schedules (
    schedule_id       SERIAL PRIMARY KEY,
    route_id          INT REFERENCES routes(route_id),
    departure_time    TIME NOT NULL,
    frequency_minutes INT NOT NULL
);

CREATE TABLE bus_runs (
    run_id         SERIAL PRIMARY KEY,
    route_id       INT REFERENCES routes(route_id),
    vehicle_id     TEXT NOT NULL UNIQUE,   -- UNIQUE added: required for upsert ON CONFLICT
    started_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    current_stop   INT REFERENCES stops(stop_id),
    delay_seconds  INT NOT NULL DEFAULT 0
);

CREATE INDEX idx_stops_intersection ON stops(intersection_id);
CREATE INDEX idx_bus_runs_vehicle   ON bus_runs(vehicle_id);