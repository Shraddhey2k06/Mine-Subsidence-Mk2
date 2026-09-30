"""
ai/preprocessing.py
--------------------
Builds a training dataset by running the simulator through a mix of
scenarios and computing features for every step.

WHY SIMULATED TRAINING DATA (judge explanation):
Real labelled mine-subsidence failure data is not available for a
student prototype - genuine subsidence events are rare, dangerous, and
not publicly released at sensor-level granularity. Instead we generate
a realistic MIX of scenarios (mostly NORMAL, a few of each anomaly
type) using the same simulator that powers the live demo, and train on
that. This is clearly documented as a limitation: see README
"Limitations" - the model has not seen real geological data, and
real deployment would require retraining on field-collected data.
"""

import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from simulator.sensor_simulator import NodeSimulatorState, SCENARIOS
from ai.feature_engineering import compute_features_for_node


# How many ticks to run for each scenario when building the training set.
# NORMAL gets far more ticks because it should dominate the "typical
# operating condition" the anomaly detector learns.
SCENARIO_TICK_COUNTS = {
    "NORMAL": 400,
    "MINOR_ANOMALY": 60,
    "MODERATE_DEFORMATION": 80,
    "HIGH_RISK": 60,
    "CRITICAL_EVENT": 40,
    "RECOVERY": 60,
}


def generate_training_dataset():
    """
    Returns a list of feature dicts (see feature_engineering) generated
    by simulating every scenario in sequence for a single synthetic
    training node, plus a matching list of scenario labels (for
    evaluation/analysis only - the anomaly detector itself is
    unsupervised and does not use these labels for training).
    """
    state = NodeSimulatorState("TRAIN_NODE")
    raw_readings = []
    labels = []

    for scenario, tick_count in SCENARIO_TICK_COUNTS.items():
        state.set_scenario(scenario)
        for _ in range(tick_count):
            reading = state.tick()
            raw_readings.append(reading)
            labels.append(scenario)

    features = []
    feature_labels = []
    for i in range(1, len(raw_readings) + 1):
        # Feed a growing window so rolling stats/rates are computed the
        # same way they will be at inference time.
        window_start = max(0, i - 20)
        feat = compute_features_for_node(raw_readings[window_start:i])
        if feat is not None:
            features.append(feat)
            feature_labels.append(labels[i - 1])

    return features, feature_labels


if __name__ == "__main__":
    feats, labels = generate_training_dataset()
    print(f"Generated {len(feats)} feature rows across scenarios: {set(labels)}")
    print("Sample row:", feats[0])
