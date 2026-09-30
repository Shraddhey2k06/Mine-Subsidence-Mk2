"""
ai/anomaly_detector.py
------------------------
Wraps scikit-learn's Isolation Forest for unsupervised anomaly
detection on sensor feature vectors.

WHY ISOLATION FOREST (judge explanation):
We need to flag "this combination of sensor values looks unusual"
without a large labelled dataset of real mine failures (which doesn't
exist for a student prototype). Isolation Forest is an UNSUPERVISED
method - it learns what "normal" looks like from mostly-normal training
data and isolates points that are easy to separate from the rest
(anomalies require fewer random partitions to isolate than typical
points). It's lightweight, fast to train, easy to explain ("outliers
are easy to isolate, normal points are buried in the crowd"), and
doesn't require deep learning infrastructure.

IMPORTANT: an anomaly score is NOT proof of subsidence. It means "this
reading pattern doesn't look like the training data's normal
operating conditions" - see the risk engine for how this is combined
with other signals before any warning is raised.
"""

import os
import joblib
import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import MinMaxScaler

import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from ai.feature_engineering import ML_FEATURE_NAMES, features_to_vector


class AnomalyDetector:
    def __init__(self):
        self.model = None
        self.scaler = None  # rescales raw isolation-forest scores to 0-1

    def train(self, feature_dicts: list):
        X = np.array([features_to_vector(f) for f in feature_dicts])

        self.model = IsolationForest(
            n_estimators=config.ISOLATION_FOREST_N_ESTIMATORS,
            contamination=config.ISOLATION_FOREST_CONTAMINATION,
            random_state=config.ISOLATION_FOREST_RANDOM_STATE,
        )
        self.model.fit(X)

        # Isolation Forest's raw score_samples() is higher = more normal
        # (roughly -0.5 to 0.5). We flip and min-max scale it to 0-1
        # where 1 = most anomalous, which is far more intuitive to show
        # on a dashboard than a raw, unbounded isolation-path score.
        raw_scores = -self.model.score_samples(X)  # flip: higher = more anomalous
        self.scaler = MinMaxScaler()
        self.scaler.fit(raw_scores.reshape(-1, 1))

        return self

    def score(self, feature_dict: dict) -> float:
        """Return an anomaly score in [0, 1], where 1 = most anomalous."""
        x = np.array([features_to_vector(feature_dict)])
        raw_score = -self.model.score_samples(x)[0]
        scaled = self.scaler.transform([[raw_score]])[0][0]
        return float(np.clip(scaled, 0.0, 1.0))

    def is_anomalous(self, score: float) -> bool:
        return score >= config.ANOMALY_SCORE_THRESHOLD

    def save(self, path=None):
        path = path or config.ANOMALY_MODEL_PATH
        os.makedirs(os.path.dirname(path), exist_ok=True)
        joblib.dump({"model": self.model, "scaler": self.scaler}, path)

    @classmethod
    def load(cls, path=None):
        path = path or config.ANOMALY_MODEL_PATH
        data = joblib.load(path)
        detector = cls()
        detector.model = data["model"]
        detector.scaler = data["scaler"]
        return detector
