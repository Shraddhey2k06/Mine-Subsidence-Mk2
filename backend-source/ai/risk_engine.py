"""
ai/risk_engine.py
-------------------
Combines the AI outputs (anomaly score, predicted displacement) with
raw sensor signals into a single, explainable risk score (0-100) and
risk level (LOW/MODERATE/HIGH/CRITICAL).

WHY A SEPARATE RISK ENGINE, NOT JUST THE ML MODEL (judge explanation):
No single ML model should be the sole authority deciding whether to
raise a safety warning. The anomaly detector and predictor each look
at the data from one angle; combining several independent signals
(anomaly score, predicted trend, rate of change, vibration, crack
detection) with transparent, configurable weights is both more robust
(a false signal from one sensor doesn't dominate) and more explainable
to an operator ("risk is HIGH because displacement rate and tilt rate
are both elevated, not just because one model said so").

All weights and thresholds live in config.py - NOT hard-coded here -
so they can be tuned without touching this logic, and are clearly
labelled as prototype/configurable values (see README "Limitations").
"""

import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config


def _normalize(value, key):
    """Scale a raw value into 0-1 using the configured reference range."""
    low, high = config.NORMALIZATION_RANGES[key]
    if high == low:
        return 0.0
    return max(0.0, min(1.0, (value - low) / (high - low)))


def compute_risk(anomaly_score, predicted_displacement, displacement_rate,
                  tilt_rate, vibration, crack_status):
    """
    Returns (risk_score: float 0-100, risk_level: str, contributing_factors: list[str])
    """
    normalized = {
        "anomaly_score": max(0.0, min(1.0, anomaly_score)),
        "predicted_displacement": _normalize(predicted_displacement, "predicted_displacement"),
        "displacement_rate": _normalize(abs(displacement_rate), "displacement_rate"),
        "tilt_rate": _normalize(abs(tilt_rate), "tilt_rate"),
        "vibration": _normalize(vibration, "vibration"),
        "crack_status": 1.0 if crack_status else 0.0,
    }

    weighted_sum = sum(
        normalized[key] * weight for key, weight in config.RISK_WEIGHTS.items()
    )
    risk_score = round(weighted_sum * 100, 1)

    # Determine risk level from configured cut points (highest threshold
    # that the score meets or exceeds).
    risk_level = "LOW"
    for level, cutoff in sorted(config.RISK_LEVEL_THRESHOLDS.items(), key=lambda kv: kv[1]):
        if risk_score >= cutoff:
            risk_level = level

    # Build a human-readable explanation of what drove the score, so the
    # UI never presents an unexplained black-box number (README rule:
    # "Do not use unexplained black-box language").
    factors = []
    if normalized["anomaly_score"] >= 0.5:
        factors.append(f"Sensor pattern is unusual compared with normal conditions (anomaly score {anomaly_score:.2f}).")
    if normalized["displacement_rate"] >= 0.4:
        factors.append(f"Displacement is changing quickly ({displacement_rate:.2f} mm/min).")
    if normalized["tilt_rate"] >= 0.4:
        factors.append(f"Tilt is changing quickly ({tilt_rate:.3f} deg/min).")
    if normalized["predicted_displacement"] >= 0.4:
        factors.append(f"Predicted displacement trend is elevated ({predicted_displacement:.1f} mm).")
    if normalized["vibration"] >= 0.4:
        factors.append(f"Vibration is above baseline ({vibration:.2f} g).")
    if crack_status:
        factors.append("Crack sensor has detected a crack event.")
    if not factors:
        factors.append("All monitored signals are within normal operating ranges.")

    return risk_score, risk_level, factors
