"""
simulator/sensor_simulator.py
------------------------------
Generates SIMULATED sensor readings so the full system can be
demonstrated without physical ESP32 hardware.

WHY THIS EXISTS: the SIH problem statement expects a wireless sensor
network of tilt/vibration/displacement/crack sensors. Building and
deploying real hardware is out of scope for a software-focused student
prototype, so this simulator produces physically plausible sequences
of readings and clearly labels them as simulated (is_simulated=1 in
the DB, and "DEMO / SIMULATED DATA" in the UI).

SCENARIOS
---------
NORMAL                - small random noise around a stable baseline
MINOR_ANOMALY         - one-off small spike, not sustained
MODERATE_DEFORMATION  - slow, steady increase in tilt/displacement
HIGH_RISK             - faster increase across tilt/displacement/vibration
CRITICAL_EVENT        - rapid increase + crack detection triggers
RECOVERY              - values gradually return toward baseline

Each node has its own independent state machine so different nodes can
be in different scenarios at once (e.g. one CRITICAL, others NORMAL).
"""

import random
import math
from datetime import datetime, timezone

SCENARIOS = [
    "NORMAL",
    "MINOR_ANOMALY",
    "MODERATE_DEFORMATION",
    "HIGH_RISK",
    "CRITICAL_EVENT",
    "RECOVERY",
]

# Baseline "resting" values for a healthy sensor node.
BASELINE = {
    "tilt_x": 0.05,
    "tilt_y": 0.05,
    "displacement": 0.5,
    "vibration": 0.05,
}


class NodeSimulatorState:
    """Tracks the evolving simulated condition of a single sensor node."""

    def __init__(self, node_id):
        self.node_id = node_id
        self.scenario = "NORMAL"
        self.step = 0  # how many ticks we've been in this scenario
        # Running "current" values - scenarios push these up/down over time
        self.tilt_x = BASELINE["tilt_x"]
        self.tilt_y = BASELINE["tilt_y"]
        self.displacement = BASELINE["displacement"]
        self.vibration = BASELINE["vibration"]
        self.crack_status = 0

    def set_scenario(self, scenario):
        if scenario not in SCENARIOS:
            raise ValueError(f"Unknown scenario '{scenario}'. Valid: {SCENARIOS}")
        self.scenario = scenario
        self.step = 0

    def _noise(self, magnitude):
        return random.uniform(-magnitude, magnitude)

    def tick(self):
        """Advance one simulated reading according to the current scenario."""
        self.step += 1

        if self.scenario == "NORMAL":
            self.tilt_x = BASELINE["tilt_x"] + self._noise(0.02)
            self.tilt_y = BASELINE["tilt_y"] + self._noise(0.02)
            self.displacement = max(0, self.displacement + self._noise(0.05))
            self.vibration = max(0, BASELINE["vibration"] + self._noise(0.02))
            self.crack_status = 0

        elif self.scenario == "MINOR_ANOMALY":
            # A brief, small spike that does not sustain - tests that the
            # system doesn't over-react to single-reading blips.
            spike = 0.15 if self.step % 4 == 0 else 0.0
            self.tilt_x = BASELINE["tilt_x"] + spike + self._noise(0.02)
            self.tilt_y = BASELINE["tilt_y"] + self._noise(0.02)
            self.displacement = max(0, self.displacement + self._noise(0.08) + (0.3 if spike else 0))
            self.vibration = max(0, BASELINE["vibration"] + self._noise(0.03))
            self.crack_status = 0

        elif self.scenario == "MODERATE_DEFORMATION":
            # Slow steady drift upward - simulates gradual ground movement.
            self.tilt_x += 0.01 + self._noise(0.005)
            self.tilt_y += 0.008 + self._noise(0.005)
            self.displacement += 0.4 + self._noise(0.1)
            self.vibration = max(0, BASELINE["vibration"] + 0.02 * math.log1p(self.step) + self._noise(0.02))
            self.crack_status = 0

        elif self.scenario == "HIGH_RISK":
            # Faster increase across multiple correlated signals.
            self.tilt_x += 0.03 + self._noise(0.01)
            self.tilt_y += 0.025 + self._noise(0.01)
            self.displacement += 1.2 + self._noise(0.2)
            self.vibration = min(1.0, self.vibration + 0.03 + self._noise(0.02))
            self.crack_status = 1 if self.step % 6 == 0 else self.crack_status

        elif self.scenario == "CRITICAL_EVENT":
            # Rapid change + persistent crack detection.
            self.tilt_x += 0.06 + self._noise(0.02)
            self.tilt_y += 0.05 + self._noise(0.02)
            self.displacement += 2.5 + self._noise(0.3)
            self.vibration = min(1.0, self.vibration + 0.06 + self._noise(0.02))
            self.crack_status = 1

        elif self.scenario == "RECOVERY":
            # Values relax back toward (but not fully to) baseline.
            self.tilt_x += (BASELINE["tilt_x"] - self.tilt_x) * 0.1
            self.tilt_y += (BASELINE["tilt_y"] - self.tilt_y) * 0.1
            self.displacement += (BASELINE["displacement"] * 3 - self.displacement) * 0.05
            self.vibration += (BASELINE["vibration"] - self.vibration) * 0.15
            self.crack_status = 0 if self.step > 5 else self.crack_status

        reading = {
            "node_id": self.node_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "tilt_x": round(self.tilt_x, 4),
            "tilt_y": round(self.tilt_y, 4),
            "displacement": round(self.displacement, 3),
            "vibration": round(max(0.0, self.vibration), 4),
            "crack_status": int(self.crack_status),
            "temperature": round(25 + self._noise(2), 1),
            "battery_level": round(max(0, 100 - self.step * 0.01), 1),
            "signal_strength": round(random.uniform(60, 100), 1),
        }
        return reading


class SensorSimulator:
    """Owns per-node simulator state for the whole network."""

    def __init__(self, node_ids):
        self.nodes = {nid: NodeSimulatorState(nid) for nid in node_ids}

    def set_scenario(self, node_id, scenario):
        if node_id not in self.nodes:
            self.nodes[node_id] = NodeSimulatorState(node_id)
        self.nodes[node_id].set_scenario(scenario)

    def generate_reading(self, node_id):
        if node_id not in self.nodes:
            self.nodes[node_id] = NodeSimulatorState(node_id)
        return self.nodes[node_id].tick()

    def generate_all(self):
        return [self.generate_reading(nid) for nid in self.nodes]


if __name__ == "__main__":
    # Quick manual smoke test - run directly to sanity check output.
    sim = SensorSimulator(["NODE_01", "NODE_02"])
    sim.set_scenario("NODE_02", "HIGH_RISK")
    for _ in range(3):
        for r in sim.generate_all():
            print(r)
