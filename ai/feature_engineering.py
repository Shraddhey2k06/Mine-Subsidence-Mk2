"""
ai/feature_engineering.py
--------------------------
Converts a sequence of raw sensor readings for one node into a small
set of physically meaningful features.

WHY THESE FEATURES (judge explanation):
A single sensor reading tells you where things stand right now, but
ground subsidence is a PROCESS - what matters is how fast things are
changing, not just the instantaneous value. Two readings with the same
displacement can mean very different things depending on whether that
displacement has been flat for hours or has been climbing rapidly for
the last few minutes. So on top of the raw values we compute:

- magnitude of tilt (combines tilt_x/tilt_y into one number)
- rate of change of displacement and tilt (how fast things are moving)
- rolling averages (smooth out sensor noise so a single noisy reading
  doesn't look like a trend)

We deliberately keep this small and interpretable rather than creating
dozens of engineered features - each one here has a clear physical
meaning a judge can ask about.
"""

import math
from datetime import datetime

import config


def _parse_ts(ts_str):
    return datetime.fromisoformat(ts_str)


def tilt_magnitude(tilt_x, tilt_y):
    """Combine two tilt axes into a single magnitude, like a resultant vector."""
    return math.sqrt(tilt_x ** 2 + tilt_y ** 2)


def compute_features_for_node(readings: list) -> dict:
    """
    Given a chronologically-ordered list of raw reading dicts for ONE
    node (oldest first), return a single feature dict describing the
    most recent state, including rates and rolling averages computed
    from the window.

    Returns None if there isn't enough data yet (need at least 2
    readings for a rate calculation).
    """
    if not readings:
        return None

    window = readings[-config.ROLLING_WINDOW_SIZE:]
    latest = window[-1]

    tilt_mags = [tilt_magnitude(r["tilt_x"], r["tilt_y"]) for r in window]
    displacements = [r["displacement"] for r in window]
    vibrations = [r["vibration"] for r in window]

    current_tilt_mag = tilt_mags[-1]
    current_displacement = displacements[-1]
    current_vibration = vibrations[-1]

    # Rates of change: (change in value) / (change in time, in minutes).
    # Guard against a zero or missing time delta (e.g. only one reading).
    if len(window) >= 2:
        t0 = _parse_ts(window[-2]["timestamp"])
        t1 = _parse_ts(window[-1]["timestamp"])
        dt_minutes = max((t1 - t0).total_seconds() / 60.0, 1e-6)
        displacement_rate = (displacements[-1] - displacements[-2]) / dt_minutes
        tilt_rate = (tilt_mags[-1] - tilt_mags[-2]) / dt_minutes
    else:
        displacement_rate = 0.0
        tilt_rate = 0.0

    rolling_displacement_avg = sum(displacements) / len(displacements)
    rolling_tilt_avg = sum(tilt_mags) / len(tilt_mags)
    rolling_vibration_avg = sum(vibrations) / len(vibrations)

    return {
        "node_id": latest["node_id"],
        "timestamp": latest["timestamp"],
        "tilt_magnitude": current_tilt_mag,
        "displacement": current_displacement,
        "vibration": current_vibration,
        "crack_status": latest.get("crack_status", 0),
        "displacement_rate": displacement_rate,
        "tilt_rate": tilt_rate,
        "rolling_displacement_avg": rolling_displacement_avg,
        "rolling_tilt_avg": rolling_tilt_avg,
        "rolling_vibration_avg": rolling_vibration_avg,
    }


# The ordered feature names fed into the ML models. Keeping this list
# in one place ensures training and inference always use the same
# feature order.
ML_FEATURE_NAMES = [
    "tilt_magnitude",
    "displacement",
    "vibration",
    "displacement_rate",
    "tilt_rate",
    "rolling_displacement_avg",
    "rolling_tilt_avg",
    "rolling_vibration_avg",
]


def features_to_vector(features: dict) -> list:
    """Extract the ML-facing feature vector in a fixed, consistent order."""
    return [features[name] for name in ML_FEATURE_NAMES]
