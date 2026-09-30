"""
notifications/alert_service.py
---------------------------------
Decides whether a new prediction/risk result should raise an alert,
and if so, records it (with cooldown/de-duplication so the same
condition doesn't spam the operator with repeated alerts).

WHY ISOLATED HERE: keeping alerting logic separate from the risk engine
means we can add real notification channels (SMS/email) later - see
README "Alert System" - by extending this module only, without
touching the risk scoring logic.
"""

import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
import database.db as db


def maybe_raise_alert(node_id, timestamp, risk_score, risk_level, contributing_factors,
                       is_anomalous, crack_status, displacement_rate):
    """
    Evaluate alert conditions and insert an alert row if warranted and
    not currently in cooldown. Returns the alert dict if one was
    raised, else None.
    """
    triggering_conditions = []

    if risk_score >= config.ALERT_RISK_SCORE_THRESHOLD:
        triggering_conditions.append(f"Risk score {risk_score:.0f} exceeds threshold {config.ALERT_RISK_SCORE_THRESHOLD}.")
    if is_anomalous:
        triggering_conditions.append("Anomaly detected in sensor pattern.")
    if crack_status:
        triggering_conditions.append("Crack sensor triggered.")
    if abs(displacement_rate) >= config.NORMALIZATION_RANGES["displacement_rate"][1] * 0.75:
        triggering_conditions.append(f"Rapid displacement increase ({displacement_rate:.2f} mm/min).")

    if not triggering_conditions:
        return None

    # Cooldown / de-duplication: skip if an alert of the same severity
    # was already raised for this node within the cooldown window.
    recent = db.get_recent_alert_for_node(node_id, risk_level, config.ALERT_COOLDOWN_SECONDS)
    if recent is not None:
        return None

    message = f"{risk_level} risk detected at {node_id}: " + " ".join(triggering_conditions)

    alert = {
        "node_id": node_id,
        "timestamp": timestamp,
        "severity": risk_level,
        "message": message,
        "triggering_conditions": triggering_conditions,
    }
    alert_id = db.insert_alert(alert)
    alert["id"] = alert_id
    return alert
