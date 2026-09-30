-- schema.sql
-- ----------
-- SQLite schema for the Mine Subsidence Monitoring prototype.
--
-- WHY SQLite: this is a student prototype meant to run on a single
-- laptop with zero setup. SQLAlchemy/PostgreSQL can replace this later
-- (see README "Future Scalability") without changing the API surface.

PRAGMA foreign_keys = ON;

-- ------------------------------------------------------------------
-- nodes: registry of physical/simulated sensor nodes
-- ------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS nodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    node_id TEXT UNIQUE NOT NULL,
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    installation_area TEXT,
    status TEXT NOT NULL DEFAULT 'ACTIVE',   -- ACTIVE | OFFLINE | MAINTENANCE
    last_seen TEXT                            -- ISO timestamp
);

-- ------------------------------------------------------------------
-- sensor_readings: raw (or simulated) readings from each node
-- ------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sensor_readings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    node_id TEXT NOT NULL,
    timestamp TEXT NOT NULL,                  -- ISO timestamp
    tilt_x REAL NOT NULL,
    tilt_y REAL NOT NULL,
    displacement REAL NOT NULL,               -- mm, cumulative surface displacement
    vibration REAL NOT NULL,                  -- g, relative vibration magnitude
    crack_status INTEGER NOT NULL DEFAULT 0,  -- 0 = no crack, 1 = crack detected
    temperature REAL,
    battery_level REAL,
    signal_strength REAL,
    is_simulated INTEGER NOT NULL DEFAULT 1,  -- 1 = simulated/demo, 0 = real sensor
    synced INTEGER NOT NULL DEFAULT 1,        -- 0 = queued offline, not yet synced
    FOREIGN KEY (node_id) REFERENCES nodes(node_id)
);

CREATE INDEX IF NOT EXISTS idx_readings_node_time
    ON sensor_readings(node_id, timestamp);

-- ------------------------------------------------------------------
-- predictions: AI pipeline outputs per node per evaluation cycle
-- ------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    node_id TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    predicted_displacement REAL,
    anomaly_score REAL,
    is_anomalous INTEGER NOT NULL DEFAULT 0,
    risk_score REAL,
    risk_level TEXT,                          -- LOW | MODERATE | HIGH | CRITICAL
    contributing_factors TEXT,                 -- JSON-encoded explanation
    FOREIGN KEY (node_id) REFERENCES nodes(node_id)
);

CREATE INDEX IF NOT EXISTS idx_predictions_node_time
    ON predictions(node_id, timestamp);

-- ------------------------------------------------------------------
-- alerts: generated warnings
-- ------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    node_id TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    severity TEXT NOT NULL,                   -- LOW | MODERATE | HIGH | CRITICAL
    message TEXT NOT NULL,
    triggering_conditions TEXT,                -- JSON-encoded list of reasons
    acknowledged INTEGER NOT NULL DEFAULT 0,
    acknowledged_by TEXT,
    acknowledged_at TEXT,
    FOREIGN KEY (node_id) REFERENCES nodes(node_id)
);

CREATE INDEX IF NOT EXISTS idx_alerts_node_time
    ON alerts(node_id, timestamp);

-- ------------------------------------------------------------------
-- users: basic authentication with roles
-- ------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'OPERATOR'      -- OPERATOR | PLANNER | REGULATOR
);
