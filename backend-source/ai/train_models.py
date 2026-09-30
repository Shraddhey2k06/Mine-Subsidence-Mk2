"""
ai/train_models.py
--------------------
End-to-end training pipeline:
  1. Generate a simulated training dataset (preprocessing.py)
  2. Train the Isolation Forest anomaly detector
  3. Train the Linear Regression displacement predictor
  4. Evaluate both and print metrics (never fabricated - see README rule 4)
  5. Save trained models to /models so app.py loads them instead of
     retraining on every request

Run with: python ai/train_models.py
"""

import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from ai.preprocessing import generate_training_dataset
from ai.anomaly_detector import AnomalyDetector
from ai.predictor import DisplacementPredictor

# How many "ticks ahead" correspond to PREDICTION_HORIZON_MINUTES, given
# the simulator emits one reading per SIMULATOR_INTERVAL_SECONDS.
TICKS_PER_HORIZON = max(
    1,
    int((config.PREDICTION_HORIZON_MINUTES * 60) / config.SIMULATOR_INTERVAL_SECONDS)
)


def build_regression_targets(feature_dicts):
    """
    For each feature row, the regression target is the displacement
    value TICKS_PER_HORIZON steps ahead in the same feature sequence.
    Rows too close to the end (no future value available) are dropped.
    """
    X, y = [], []
    for i in range(len(feature_dicts) - TICKS_PER_HORIZON):
        X.append(feature_dicts[i])
        y.append(feature_dicts[i + TICKS_PER_HORIZON]["displacement"])
    return X, y


def main():
    print("=" * 60)
    print("MineWatch AI Training Pipeline")
    print("=" * 60)

    print("\n[1/4] Generating simulated training dataset...")
    feature_dicts, labels = generate_training_dataset()
    print(f"  Generated {len(feature_dicts)} feature rows.")
    print(f"  Scenario mix: {dict((l, labels.count(l)) for l in set(labels))}")
    print("  NOTE: this is SIMULATED data - see README 'Limitations'.")

    print("\n[2/4] Training Isolation Forest anomaly detector...")
    detector = AnomalyDetector()
    detector.train(feature_dicts)
    scores = [detector.score(f) for f in feature_dicts]
    anomalous_count = sum(1 for s in scores if detector.is_anomalous(s))
    print(f"  Trained on {len(feature_dicts)} rows.")
    print(f"  {anomalous_count}/{len(feature_dicts)} rows flagged anomalous "
          f"at threshold {config.ANOMALY_SCORE_THRESHOLD} (contamination={config.ISOLATION_FOREST_CONTAMINATION}).")

    print("\n[3/4] Training Linear Regression displacement predictor...")
    X_reg, y_reg = build_regression_targets(feature_dicts)
    predictor = DisplacementPredictor()
    predictor.train(X_reg, y_reg)
    print(f"  Trained on {len(X_reg)} rows (target = displacement "
          f"~{config.PREDICTION_HORIZON_MINUTES} min ahead).")
    print("  Evaluation on held-out test split (NOT training data):")
    for k, v in predictor.metrics.items():
        print(f"    {k}: {v}")

    print("\n[4/4] Saving trained models to /models ...")
    detector.save()
    predictor.save()
    print(f"  Saved: {config.ANOMALY_MODEL_PATH}")
    print(f"  Saved: {config.PREDICTOR_MODEL_PATH}")

    print("\nDone. app.py will load these models instead of retraining on each request.")


if __name__ == "__main__":
    main()
