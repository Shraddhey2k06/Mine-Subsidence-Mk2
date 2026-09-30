"""
config.py
---------
Central configuration for the Mine Subsidence Monitoring prototype.

WHY THIS FILE EXISTS:
The problem statement (and good engineering practice) asks us to avoid
scattering "magic numbers" throughout the code. Every threshold used by
the risk engine, alert system, and AI pipeline lives here so a judge (or
a teammate) can see and tune the entire decision logic in one place.

IMPORTANT: These are PROTOTYPE thresholds chosen for demo purposes.
They are NOT validated against real mine geotechnical data. See the
README "Limitations" section.
"""

import os

# -----------------------------------------------------------------------
# Basic app settings
# -----------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

SECRET_KEY = os.environ.get("MINEWATCH_SECRET_KEY", "dev-secret-change-me")

DATABASE_PATH = os.path.join(BASE_DIR, "data", "minewatch.db")

MODELS_DIR = os.path.join(BASE_DIR, "models")
ANOMALY_MODEL_PATH = os.path.join(MODELS_DIR, "anomaly_model.joblib")
PREDICTOR_MODEL_PATH = os.path.join(MODELS_DIR, "predictor_model.joblib")
SCALER_PATH = os.path.join(MODELS_DIR, "feature_scaler.joblib")

# -----------------------------------------------------------------------
# Sensor / simulation settings
# -----------------------------------------------------------------------
# How often (seconds) the simulator emits a new reading per node.
SIMULATOR_INTERVAL_SECONDS = 3

# Rolling window (number of past readings) used for rolling-average
# features and for rate-of-change calculations.
ROLLING_WINDOW_SIZE = 5

# -----------------------------------------------------------------------
# Anomaly detection (Isolation Forest) settings
# -----------------------------------------------------------------------
# contamination = expected proportion of anomalous points in "normal"
# training data. Kept low because most training data represents
# routine, non-hazardous ground conditions.
ISOLATION_FOREST_CONTAMINATION = 0.05
ISOLATION_FOREST_N_ESTIMATORS = 100
ISOLATION_FOREST_RANDOM_STATE = 42

# Anomaly score threshold (after min-max rescaling to 0-1, where 1 =
# most anomalous). Above this, a reading is flagged "anomalous".
ANOMALY_SCORE_THRESHOLD = 0.6

# -----------------------------------------------------------------------
# Prediction (regression) settings
# -----------------------------------------------------------------------
# How far ahead (in minutes of simulated time) the regression model
# forecasts displacement. Kept short relative to the simulator's tick
# rate so enough training examples exist for each scenario window
# (see ai/train_models.py TICKS_PER_HORIZON).
PREDICTION_HORIZON_MINUTES = 5

# -----------------------------------------------------------------------
# Risk engine settings
# -----------------------------------------------------------------------
# Weights applied to each normalized (0-1) input signal when computing
# the composite risk score (0-100). Weights should sum to 1.0.
RISK_WEIGHTS = {
    "anomaly_score": 0.30,
    "predicted_displacement": 0.25,
    "displacement_rate": 0.20,
    "tilt_rate": 0.15,
    "vibration": 0.05,
    "crack_status": 0.05,
}

# Risk score (0-100) cut points for the four risk levels.
RISK_LEVEL_THRESHOLDS = {
    "LOW": 0,        # 0   <= score < 30
    "MODERATE": 30,  # 30  <= score < 55
    "HIGH": 55,      # 55  <= score < 80
    "CRITICAL": 80,  # 80  <= score <= 100
}

# Normalization reference ranges used to scale raw sensor/feature values
# into 0-1 before applying RISK_WEIGHTS. These are prototype reference
# ranges based on typical simulated scenario magnitudes, not surveyed
# geotechnical limits.
NORMALIZATION_RANGES = {
    "displacement_rate": (0.0, 2.0),      # mm per reading interval
    "tilt_rate": (0.0, 0.5),              # degrees per reading interval
    "vibration": (0.0, 1.0),              # g (relative units)
    "predicted_displacement": (0.0, 50.0) # mm
}

# -----------------------------------------------------------------------
# Alerting settings
# -----------------------------------------------------------------------
# Minimum risk_score that triggers an automatic alert.
ALERT_RISK_SCORE_THRESHOLD = 55

# Cooldown period (seconds) — an identical alert for the same node will
# not be re-raised within this window, to avoid alert spam.
ALERT_COOLDOWN_SECONDS = 60

# -----------------------------------------------------------------------
# Offline / sync settings
# -----------------------------------------------------------------------
# How often (seconds) the frontend/backend checks connectivity and
# attempts to flush the queued/unsynchronized readings.
SYNC_CHECK_INTERVAL_SECONDS = 10
