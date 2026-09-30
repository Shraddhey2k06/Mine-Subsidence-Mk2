"""
app.py
------
Flask application entrypoint for the Mine Subsidence Monitoring
prototype.

STAGE 4 of the incremental build: REST API wired to the database and
the sensor simulator. AI pipeline, GIS, alerts, offline sync, and auth
are added in later stages (see README "Implementation Rules").
"""

from flask import Flask, jsonify, request, render_template, session, redirect, url_for
from functools import wraps
from datetime import datetime, timezone
import os
from werkzeug.security import check_password_hash

import config
import database.db as db
from simulator.sensor_simulator import SensorSimulator, SCENARIOS
from ai.feature_engineering import compute_features_for_node
from ai.anomaly_detector import AnomalyDetector
from ai.predictor import DisplacementPredictor
from ai.risk_engine import compute_risk
from ai.gis_interpolation import build_risk_grid
from notifications.alert_service import maybe_raise_alert

app = Flask(__name__)
app.config["SECRET_KEY"] = config.SECRET_KEY


# ------------------------------------------------------------------
# Authentication
# ------------------------------------------------------------------
# WHY SESSION-BASED AUTH: this is a prototype operator dashboard, not
# a public multi-tenant API, so a simple server-side session (Flask's
# signed cookie) is enough to gate the dashboard and API by role
# without adding JWT/OAuth infrastructure the SIH problem statement
# doesn't ask for. Passwords are hashed with werkzeug's
# generate_password_hash (PBKDF2) - see database/seed.py - never
# stored in plaintext.
PUBLIC_PATHS = {"/login", "/static", "/api/health"}


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "username" not in session:
            if request.path.startswith("/api/"):
                return jsonify({"error": "Authentication required"}), 401
            return redirect(url_for("login_page"))
        return f(*args, **kwargs)
    return wrapper


@app.before_request
def enforce_auth():
    path = request.path
    if any(path == p or path.startswith(p + "/") or path.startswith(p) for p in PUBLIC_PATHS):
        return None
    if "username" not in session:
        if path.startswith("/api/"):
            return jsonify({"error": "Authentication required"}), 401
        return redirect(url_for("login_page"))
    return None


@app.route("/login", methods=["GET"])
def login_page():
    if "username" in session:
        return redirect(url_for("dashboard"))
    return render_template("login.html", error=None)


@app.route("/login", methods=["POST"])
def login_submit():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    user = db.get_user_by_username(username)
    if user is None or not check_password_hash(user["password_hash"], password):
        return render_template("login.html", error="Invalid username or password."), 401
    session["username"] = user["username"]
    session["role"] = user["role"]
    return redirect(url_for("dashboard"))


@app.route("/logout", methods=["GET"])
def logout():
    session.clear()
    return redirect(url_for("login_page"))

# ---------------------------------------------------------------
# In-memory simulator instance.
# WHY IN-MEMORY: the simulator's scenario state (e.g. "NODE_02 is in
# HIGH_RISK, step 7") is transient demo control state, not sensor data
# that needs to survive a restart. Actual generated readings ARE
# persisted to the database as they're produced.
# ---------------------------------------------------------------
_simulator = None

# ---------------------------------------------------------------
# Connectivity simulation (for the offline-mode demo).
# WHY IN-MEMORY: like the simulator state, this is demo control state
# ("is this node's gateway currently reachable?"), not sensor data.
# When OFFLINE, new readings are still written locally (synced=0) but
# the AI pipeline is NOT run on them yet - this mirrors a real edge
# gateway that keeps logging locally while it can't reach the cloud
# analytics service. Calling /api/sync flushes the backlog and runs
# the AI pipeline retroactively, just like a real reconnect would.
# ---------------------------------------------------------------
_connectivity_online = True


def get_simulator():
    global _simulator
    if _simulator is None:
        node_ids = [n["node_id"] for n in db.get_all_nodes()]
        if not node_ids:
            node_ids = ["NODE_01"]
        _simulator = SensorSimulator(node_ids)
    return _simulator


# ---------------------------------------------------------------
# AI models: loaded once at startup (or lazily on first use) rather
# than retrained per-request. If models haven't been trained yet
# (ai/train_models.py hasn't been run), the pipeline is skipped and
# the API returns "no prediction available" instead of crashing.
# ---------------------------------------------------------------
_anomaly_detector = None
_predictor = None
_models_available = None


def load_models():
    global _anomaly_detector, _predictor, _models_available
    if _models_available is not None:
        return _models_available
    try:
        _anomaly_detector = AnomalyDetector.load()
        _predictor = DisplacementPredictor.load()
        _models_available = True
    except Exception:
        _models_available = False
    return _models_available


def run_ai_pipeline_for_node(node_id):
    """
    Full AI pipeline for one node's latest data:
      raw readings -> feature engineering -> anomaly detection
      -> displacement prediction -> risk engine -> (maybe) alert

    Called right after a new reading is stored, so the dashboard's
    next poll sees an up-to-date prediction/risk/alert state.
    """
    if not load_models():
        return None

    recent_readings = db.get_readings_for_node(node_id, limit=config.ROLLING_WINDOW_SIZE + 1)
    if len(recent_readings) < 2:
        return None  # not enough history yet for rate calculations

    features = compute_features_for_node(recent_readings)
    if features is None:
        return None

    anomaly_score = _anomaly_detector.score(features)
    is_anomalous = _anomaly_detector.is_anomalous(anomaly_score)
    predicted_displacement = _predictor.predict(features)

    risk_score, risk_level, factors = compute_risk(
        anomaly_score=anomaly_score,
        predicted_displacement=predicted_displacement,
        displacement_rate=features["displacement_rate"],
        tilt_rate=features["tilt_rate"],
        vibration=features["vibration"],
        crack_status=features["crack_status"],
    )

    prediction = {
        "node_id": node_id,
        "timestamp": features["timestamp"],
        "predicted_displacement": predicted_displacement,
        "anomaly_score": anomaly_score,
        "is_anomalous": is_anomalous,
        "risk_score": risk_score,
        "risk_level": risk_level,
        "contributing_factors": factors,
    }
    db.insert_prediction(prediction)

    maybe_raise_alert(
        node_id=node_id,
        timestamp=features["timestamp"],
        risk_score=risk_score,
        risk_level=risk_level,
        contributing_factors=factors,
        is_anomalous=is_anomalous,
        crack_status=features["crack_status"],
        displacement_rate=features["displacement_rate"],
    )

    return prediction


# ------------------------------------------------------------------
# Dashboard view
# ------------------------------------------------------------------
@app.route("/", methods=["GET"])
def dashboard():
    return render_template("dashboard.html", username=session.get("username"), role=session.get("role"))


# ------------------------------------------------------------------
# Nodes
# ------------------------------------------------------------------
@app.route("/api/nodes", methods=["GET"])
def api_get_nodes():
    return jsonify(db.get_all_nodes())


# ------------------------------------------------------------------
# Sensor readings
# ------------------------------------------------------------------
@app.route("/api/readings/latest", methods=["GET"])
def api_latest_readings():
    return jsonify(db.get_latest_readings())


@app.route("/api/readings/<node_id>", methods=["GET"])
def api_readings_for_node(node_id):
    limit = request.args.get("limit", default=50, type=int)
    return jsonify(db.get_readings_for_node(node_id, limit=limit))


@app.route("/api/history/<node_id>", methods=["GET"])
def api_history_for_node(node_id):
    start = request.args.get("start")
    end = request.args.get("end")
    return jsonify(db.get_history_for_node(node_id, start_iso=start, end_iso=end))


@app.route("/api/sensor-data", methods=["POST"])
def api_post_sensor_data():
    """
    Ingest a single sensor reading.

    This endpoint is intentionally shared between the simulator and
    (later) real ESP32 hardware - both POST the same JSON shape here,
    so the rest of the system (DB, AI, dashboard) doesn't need to know
    or care whether a reading is real or simulated other than the
    is_simulated flag.
    """
    payload = request.get_json(force=True, silent=True)
    if not payload:
        return jsonify({"error": "Invalid or missing JSON body"}), 400

    required_fields = ["node_id", "tilt_x", "tilt_y", "displacement", "vibration"]
    missing = [f for f in required_fields if f not in payload]
    if missing:
        return jsonify({"error": f"Missing required fields: {missing}"}), 400

    payload.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
    payload.setdefault("crack_status", 0)

    is_simulated = payload.pop("is_simulated", True)
    db.insert_reading(payload, is_simulated=is_simulated, synced=True)
    db.touch_node(payload["node_id"], status="ACTIVE")
    run_ai_pipeline_for_node(payload["node_id"])

    return jsonify({"status": "ok", "node_id": payload["node_id"]}), 201


# ------------------------------------------------------------------
# Simulator control (demo-only helper endpoints)
# ------------------------------------------------------------------
@app.route("/api/simulate/tick", methods=["POST"])
def api_simulate_tick():
    """Generate one new reading per node and store it."""
    global _connectivity_online
    sim = get_simulator()
    readings = sim.generate_all()
    for r in readings:
        db.insert_reading(r, is_simulated=True, synced=_connectivity_online)
        db.touch_node(r["node_id"], status="ACTIVE" if _connectivity_online else "OFFLINE")
        if _connectivity_online:
            run_ai_pipeline_for_node(r["node_id"])
    return jsonify(readings)


@app.route("/api/simulate/scenario", methods=["POST"])
def api_simulate_set_scenario():
    """Body: {"node_id": "NODE_02", "scenario": "HIGH_RISK"}"""
    payload = request.get_json(force=True, silent=True) or {}
    node_id = payload.get("node_id")
    scenario = payload.get("scenario")
    if not node_id or not scenario:
        return jsonify({"error": "node_id and scenario are required"}), 400
    if scenario not in SCENARIOS:
        return jsonify({"error": f"Unknown scenario. Valid options: {SCENARIOS}"}), 400
    sim = get_simulator()
    sim.set_scenario(node_id, scenario)
    return jsonify({"status": "ok", "node_id": node_id, "scenario": scenario})


@app.route("/api/simulate/scenarios", methods=["GET"])
def api_list_scenarios():
    return jsonify(SCENARIOS)


# ------------------------------------------------------------------
# Predictions & alerts (placeholders wired to DB now, AI pipeline in
# a later stage will actually populate the predictions table)
# ------------------------------------------------------------------
@app.route("/api/prediction/<node_id>", methods=["GET"])
def api_prediction_for_node(node_id):
    pred = db.get_latest_prediction(node_id)
    if pred is None:
        return jsonify({"message": "No prediction available yet for this node"}), 404
    return jsonify(pred)


@app.route("/api/alerts", methods=["GET"])
def api_get_alerts():
    limit = request.args.get("limit", default=200, type=int)
    return jsonify(db.get_all_alerts(limit=limit))


# ------------------------------------------------------------------
# GIS risk surface (Inverse Distance Weighting interpolation)
# ------------------------------------------------------------------
@app.route("/api/risk-grid", methods=["GET"])
def api_risk_grid():
    """
    Returns an interpolated risk grid across the mine panel area, built
    from each node's latest known risk_score. This is a PROTOTYPE
    VISUALIZATION (see ai/gis_interpolation.py) - not a validated
    geological subsidence boundary.
    """
    nodes = db.get_all_nodes()
    known_points = []
    for n in nodes:
        pred = db.get_latest_prediction(n["node_id"])
        risk_score = pred["risk_score"] if pred and pred.get("risk_score") is not None else 0.0
        known_points.append({
            "latitude": n["latitude"],
            "longitude": n["longitude"],
            "risk_score": risk_score,
        })
    grid = build_risk_grid(known_points)
    return jsonify(grid)


@app.route("/api/acknowledge-alert", methods=["POST"])
def api_acknowledge_alert():
    payload = request.get_json(force=True, silent=True) or {}
    alert_id = payload.get("alert_id")
    if not alert_id:
        return jsonify({"error": "alert_id is required"}), 400
    db.acknowledge_alert(alert_id, acknowledged_by=payload.get("acknowledged_by", "operator"))
    return jsonify({"status": "ok"})


# ------------------------------------------------------------------
# Connectivity (offline-mode demo control)
# ------------------------------------------------------------------
@app.route("/api/connectivity", methods=["GET"])
def api_get_connectivity():
    unsynced_count = len(db.get_unsynced_readings())
    return jsonify({"online": _connectivity_online, "queued_readings": unsynced_count})


@app.route("/api/connectivity", methods=["POST"])
def api_set_connectivity():
    """Body: {"online": true|false} - demo control to simulate a lost connection."""
    global _connectivity_online
    payload = request.get_json(force=True, silent=True) or {}
    online = payload.get("online")
    if online is None:
        return jsonify({"error": "online (boolean) is required"}), 400
    _connectivity_online = bool(online)
    for n in db.get_all_nodes():
        db.touch_node(n["node_id"], status="ACTIVE" if _connectivity_online else "OFFLINE")
    return jsonify({"online": _connectivity_online})


# ------------------------------------------------------------------
# Sync (offline mode) - flush queued readings and catch up the AI
# pipeline on each one now that connectivity is restored.
# ------------------------------------------------------------------
@app.route("/api/sync", methods=["POST"])
def api_sync():
    unsynced = db.get_unsynced_readings()
    ids = [r["id"] for r in unsynced]
    db.mark_readings_synced(ids)

    # Re-run the AI pipeline for every node that had queued data, using
    # its now-up-to-date reading history, so risk/alerts reflect what
    # happened while offline instead of silently skipping it.
    affected_nodes = sorted({r["node_id"] for r in unsynced})
    for node_id in affected_nodes:
        run_ai_pipeline_for_node(node_id)

    return jsonify({"status": "ok", "synced_count": len(ids), "nodes_updated": affected_nodes})


# ------------------------------------------------------------------
# Health check
# ------------------------------------------------------------------
@app.route("/api/health", methods=["GET"])
def api_health():
    return jsonify({"status": "ok", "time": datetime.now(timezone.utc).isoformat()})


if __name__ == "__main__":
    if not os.path.exists(config.DATABASE_PATH):
        db.init_db()
    # use_reloader=False: the reloader spawns a child process, which
    # complicates process management for this prototype (and during
    # development it kept restarting the demo simulator's in-memory
    # state on every file save). Flip debug/use_reloader on if you're
    # actively editing app.py and want auto-reload.
    app.run(debug=True, port=5000, use_reloader=False)
