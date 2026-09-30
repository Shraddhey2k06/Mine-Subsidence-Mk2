"""
database/db.py
---------------
Thin SQLite access layer.

WHY NOT AN ORM: for a prototype of this size, plain SQL with sqlite3's
built-in Row factory is easier for a student to read, debug and explain
to judges than an ORM's abstraction layer. SQLAlchemy can be dropped in
later (see README "Future Scalability") since all DB access is
centralized in this one module.
"""

import sqlite3
import os
import json
from datetime import datetime, timezone

import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema.sql")


def get_connection():
    """Return a new SQLite connection with row access by column name."""
    os.makedirs(os.path.dirname(config.DATABASE_PATH), exist_ok=True)
    conn = sqlite3.connect(config.DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """Create all tables from schema.sql if they don't already exist."""
    conn = get_connection()
    with open(SCHEMA_PATH, "r") as f:
        conn.executescript(f.read())
    conn.commit()
    conn.close()


def now_iso():
    return datetime.now(timezone.utc).isoformat()


# ------------------------------------------------------------------
# Nodes
# ------------------------------------------------------------------
def upsert_node(node_id, latitude, longitude, installation_area=None, status="ACTIVE"):
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO nodes (node_id, latitude, longitude, installation_area, status, last_seen)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(node_id) DO UPDATE SET
            latitude=excluded.latitude,
            longitude=excluded.longitude,
            installation_area=excluded.installation_area,
            status=excluded.status,
            last_seen=excluded.last_seen
        """,
        (node_id, latitude, longitude, installation_area, status, now_iso()),
    )
    conn.commit()
    conn.close()


def touch_node(node_id, status="ACTIVE"):
    conn = get_connection()
    conn.execute(
        "UPDATE nodes SET last_seen = ?, status = ? WHERE node_id = ?",
        (now_iso(), status, node_id),
    )
    conn.commit()
    conn.close()


def get_all_nodes():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM nodes ORDER BY node_id").fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ------------------------------------------------------------------
# Sensor readings
# ------------------------------------------------------------------
def insert_reading(reading: dict, is_simulated=True, synced=True):
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO sensor_readings
            (node_id, timestamp, tilt_x, tilt_y, displacement, vibration,
             crack_status, temperature, battery_level, signal_strength,
             is_simulated, synced)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            reading["node_id"],
            reading["timestamp"],
            reading["tilt_x"],
            reading["tilt_y"],
            reading["displacement"],
            reading["vibration"],
            reading.get("crack_status", 0),
            reading.get("temperature"),
            reading.get("battery_level"),
            reading.get("signal_strength"),
            1 if is_simulated else 0,
            1 if synced else 0,
        ),
    )
    conn.commit()
    conn.close()


def get_latest_readings():
    """One most-recent reading per node."""
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT sr.* FROM sensor_readings sr
        INNER JOIN (
            SELECT node_id, MAX(timestamp) AS max_ts
            FROM sensor_readings GROUP BY node_id
        ) latest
        ON sr.node_id = latest.node_id AND sr.timestamp = latest.max_ts
        """
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_readings_for_node(node_id, limit=50):
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM sensor_readings WHERE node_id = ? ORDER BY timestamp DESC LIMIT ?",
        (node_id, limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in reversed(rows)]


def get_history_for_node(node_id, start_iso=None, end_iso=None):
    conn = get_connection()
    query = "SELECT * FROM sensor_readings WHERE node_id = ?"
    params = [node_id]
    if start_iso:
        query += " AND timestamp >= ?"
        params.append(start_iso)
    if end_iso:
        query += " AND timestamp <= ?"
        params.append(end_iso)
    query += " ORDER BY timestamp ASC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_unsynced_readings():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM sensor_readings WHERE synced = 0").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def mark_readings_synced(reading_ids):
    if not reading_ids:
        return
    conn = get_connection()
    qmarks = ",".join("?" * len(reading_ids))
    conn.execute(f"UPDATE sensor_readings SET synced = 1 WHERE id IN ({qmarks})", reading_ids)
    conn.commit()
    conn.close()


# ------------------------------------------------------------------
# Predictions
# ------------------------------------------------------------------
def insert_prediction(pred: dict):
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO predictions
            (node_id, timestamp, predicted_displacement, anomaly_score,
             is_anomalous, risk_score, risk_level, contributing_factors)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            pred["node_id"],
            pred["timestamp"],
            pred.get("predicted_displacement"),
            pred.get("anomaly_score"),
            1 if pred.get("is_anomalous") else 0,
            pred.get("risk_score"),
            pred.get("risk_level"),
            json.dumps(pred.get("contributing_factors", [])),
        ),
    )
    conn.commit()
    conn.close()


def get_latest_prediction(node_id):
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM predictions WHERE node_id = ? ORDER BY timestamp DESC LIMIT 1",
        (node_id,),
    ).fetchone()
    conn.close()
    if row is None:
        return None
    d = dict(row)
    d["contributing_factors"] = json.loads(d["contributing_factors"] or "[]")
    return d


def get_prediction_history(node_id, limit=100):
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM predictions WHERE node_id = ? ORDER BY timestamp DESC LIMIT ?",
        (node_id, limit),
    ).fetchall()
    conn.close()
    result = []
    for r in reversed(rows):
        d = dict(r)
        d["contributing_factors"] = json.loads(d["contributing_factors"] or "[]")
        result.append(d)
    return result


# ------------------------------------------------------------------
# Alerts
# ------------------------------------------------------------------
def insert_alert(alert: dict):
    conn = get_connection()
    cur = conn.execute(
        """
        INSERT INTO alerts (node_id, timestamp, severity, message, triggering_conditions, acknowledged)
        VALUES (?, ?, ?, ?, ?, 0)
        """,
        (
            alert["node_id"],
            alert["timestamp"],
            alert["severity"],
            alert["message"],
            json.dumps(alert.get("triggering_conditions", [])),
        ),
    )
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return new_id


def get_recent_alert_for_node(node_id, severity, within_seconds):
    """Used for alert cooldown/de-duplication."""
    conn = get_connection()
    row = conn.execute(
        """
        SELECT * FROM alerts
        WHERE node_id = ? AND severity = ?
        ORDER BY timestamp DESC LIMIT 1
        """,
        (node_id, severity),
    ).fetchone()
    conn.close()
    if row is None:
        return None
    last_time = datetime.fromisoformat(row["timestamp"])
    now = datetime.now(timezone.utc)
    if last_time.tzinfo is None:
        last_time = last_time.replace(tzinfo=timezone.utc)
    if (now - last_time).total_seconds() < within_seconds:
        return dict(row)
    return None


def get_all_alerts(limit=200):
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM alerts ORDER BY timestamp DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        d["triggering_conditions"] = json.loads(d["triggering_conditions"] or "[]")
        result.append(d)
    return result


def acknowledge_alert(alert_id, acknowledged_by="operator"):
    conn = get_connection()
    conn.execute(
        "UPDATE alerts SET acknowledged = 1, acknowledged_by = ?, acknowledged_at = ? WHERE id = ?",
        (acknowledged_by, now_iso(), alert_id),
    )
    conn.commit()
    conn.close()


# ------------------------------------------------------------------
# Users
# ------------------------------------------------------------------
def get_user_by_username(username):
    conn = get_connection()
    row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    conn.close()
    return dict(row) if row else None


def create_user(username, password_hash, role="OPERATOR"):
    conn = get_connection()
    conn.execute(
        "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
        (username, password_hash, role),
    )
    conn.commit()
    conn.close()
