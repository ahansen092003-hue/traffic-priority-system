import os
import psycopg2
from psycopg2 import pool

_pool = None

def get_pool():
    global _pool
    if _pool is None:
        _pool = pool.SimpleConnectionPool(
            minconn=1,
            maxconn=5,
            dsn=os.environ["DATABASE_URL"]
        )
    return _pool


def get_route_for_stop(intersection_id: str) -> dict | None:
    """
    Given a SUMO tl_id (e.g. "152326244#0"), return the route,
    stop, and schedule associated with that intersection.
    Returns None if no stop is mapped to this intersection.
    """
    conn = get_pool().getconn()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    r.route_id,
                    r.name,
                    s.stop_id,
                    s.sequence_order,
                    sc.departure_time,
                    sc.frequency_minutes
                FROM stops s
                JOIN routes r ON r.route_id = s.route_id
                JOIN schedules sc ON sc.route_id = s.route_id
                WHERE s.intersection_id = %s
                ORDER BY sc.departure_time
                """,
                (intersection_id,)
            )
            row = cursor.fetchone()

        if row is None:
            return None

        return {
            "route_id":          row[0],
            "route_name":        row[1],
            "stop_id":           row[2],
            "sequence_order":    row[3],
            "departure_time":    row[4],
            "frequency_minutes": row[5],
        }
    finally:
        get_pool().putconn(conn)


def get_active_run(vehicle_id: str) -> dict | None:
    """
    Fetch the current bus_run row for a vehicle.
    Returns None if this vehicle isn't being tracked yet.
    consumer.py calls this before deciding whether to extend green.
    """
    conn = get_pool().getconn()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT run_id, route_id, vehicle_id,
                       started_at, current_stop, delay_seconds
                FROM bus_runs
                WHERE vehicle_id = %s
                """,
                (vehicle_id,)
            )
            row = cursor.fetchone()

        if row is None:
            return None

        return {
            "run_id":        row[0],
            "route_id":      row[1],
            "vehicle_id":    row[2],
            "started_at":    row[3],
            "current_stop":  row[4],
            "delay_seconds": row[5],
        }
    finally:
        get_pool().putconn(conn)


def upsert_run(vehicle_id: str, route_id: int, current_stop: int, delay_seconds: int):
    """
    Create or update a bus_run row.
    Called when a bus clears a stop — we advance current_stop
    and write the recalculated delay.
    Requires UNIQUE (vehicle_id) on bus_runs — see 001_initial.sql.
    """
    conn = get_pool().getconn()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO bus_runs (vehicle_id, route_id, current_stop, delay_seconds)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (vehicle_id)
                DO UPDATE SET
                    current_stop  = EXCLUDED.current_stop,
                    delay_seconds = EXCLUDED.delay_seconds
                """,
                (vehicle_id, route_id, current_stop, delay_seconds)
            )
        conn.commit()
    finally:
        get_pool().putconn(conn)


def delete_run(vehicle_id: str):
    """
    Called when a bus exits the corridor.
    Removes the run so it doesn't show as active.
    """
    conn = get_pool().getconn()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "DELETE FROM bus_runs WHERE vehicle_id = %s",
                (vehicle_id,)
            )
        conn.commit()
    finally:
        get_pool().putconn(conn)