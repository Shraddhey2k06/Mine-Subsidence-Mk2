# MineWatch — AI-Enabled Low-Cost Real-Time Mine Subsidence Monitoring, Prediction & Early Warning System

Student prototype built for **Smart India Hackathon 2026**, Problem Statement **SIH26025**:
*"Development of an AI-enabled Low Cost Real Time Mine Subsidence Monitoring, Prediction and Early Warning System for Underground Coal Mines in India."*

> **This is a student prototype, not a production mining safety system.** Every AI/ML
> component here favors being simple, explainable, and demonstrable over being
> "impressive." See [Limitations](#21-limitations) before drawing any real-world conclusions from it.

---

## 1. Problem Statement

Underground coal mining can cause gradual or sudden surface subsidence above mined-out
panels. Early detection of abnormal ground movement — via tilt, vibration, displacement
and crack sensors distributed across a mine panel — can give workers and planners
advance warning before conditions become dangerous. SIH26025 asks for a system that
combines a distributed wireless sensor network with IoT, AI/ML and GIS technologies to
monitor, predict, and warn.

## 2. System Objective

Demonstrate, using **simulated sensor data** (see [Section 6](#6-why-simulated-data)),
a complete pipeline from raw sensor readings to an operator-facing early warning:

```
Sensor Node → Wireless Network → Data Ingestion → Preprocessing → Feature Engineering
  → AI/ML (Anomaly Detection + Prediction) → Risk Engine → Database
  → Dashboard + GIS → Alerts
```

## 3. Architecture

**Backend:** Python + Flask, REST JSON API
**Database:** SQLite (see [`database/schema.sql`](database/schema.sql))
**Frontend:** HTML/CSS/JavaScript, Chart.js for time-series, Leaflet.js + OpenStreetMap for GIS
**AI/ML:** NumPy, Pandas-free scikit-learn pipeline — Isolation Forest (anomaly detection) +
Linear Regression (displacement prediction)
**Real-time updates:** AJAX polling (see [Section 13](#13-real-time-communication) for why)

```
project/
├── app.py                     # Flask app: routes, auth, AI-pipeline orchestration
├── config.py                  # ALL thresholds/weights in one place — no magic numbers
├── database/
│   ├── schema.sql             # nodes, sensor_readings, predictions, alerts, users
│   ├── db.py                  # thin SQLite access layer
│   └── seed.py                # creates demo nodes + demo users
├── simulator/
│   └── sensor_simulator.py    # per-node scenario state machine (NORMAL..CRITICAL_EVENT)
├── ai/
│   ├── feature_engineering.py # raw readings -> physically meaningful features
│   ├── preprocessing.py       # builds a training dataset from simulated scenarios
│   ├── anomaly_detector.py    # Isolation Forest wrapper
│   ├── predictor.py           # Linear Regression wrapper
│   ├── risk_engine.py         # transparent, weighted risk scoring
│   ├── gis_interpolation.py   # Inverse Distance Weighting for the risk-surface map
│   └── train_models.py        # end-to-end training pipeline (run this first)
├── notifications/
│   └── alert_service.py       # alert rules + cooldown/de-duplication
├── templates/                 # login.html, dashboard.html
├── static/{css,js}/           # dashboard styling + frontend logic
├── models/                    # trained .joblib models saved here
├── data/                      # minewatch.db (SQLite file)
└── tests/                     # smoke-test scripts
```

## 4. Hardware Assumptions

The problem statement specifies tilt/inclination, vibration, displacement/stretch and
crack-detection sensors on ESP32-class nodes communicating over a wireless mesh. This
prototype does **not** include physical hardware — instead:

- `POST /api/sensor-data` is the same endpoint a real ESP32 node would call. The JSON
  shape is identical whether data comes from the simulator or real hardware; only an
  `is_simulated` flag differs.
- The simulator (`simulator/sensor_simulator.py`) stands in for the sensor network so the
  full pipeline can be demonstrated without deployed hardware.

## 5. Software Architecture

See [Section 3](#3-architecture) above and the inline module docstrings — every file in
`ai/` explains *why* that technique was chosen, not just what it does (see
[Section 20](#20-judge-explanations) for a consolidated version).

## 6. Why Simulated Data

Real, labelled mine-subsidence failure data is not available to a student team — genuine
subsidence events are rare, safety-sensitive, and not published at sensor granularity.
`simulator/sensor_simulator.py` generates six clearly-labelled scenarios per node:

| Scenario | Behavior |
|---|---|
| `NORMAL` | small random noise around baseline |
| `MINOR_ANOMALY` | brief, small spikes that don't sustain |
| `MODERATE_DEFORMATION` | slow, steady upward drift |
| `HIGH_RISK` | faster, correlated increase across tilt/displacement/vibration |
| `CRITICAL_EVENT` | rapid increase + persistent crack detection |
| `RECOVERY` | gradual relaxation back toward baseline |

Simulated readings are tagged `is_simulated=1` in the database and the dashboard always
shows a **"DEMO / SIMULATED DATA"** flag. Simulated data is never presented as real mine
measurements.

## 7. Dataset Format

Each sensor reading:

```json
{
  "node_id": "NODE_01",
  "timestamp": "2026-09-18T07:00:00+00:00",
  "latitude": 23.7401,
  "longitude": 86.4131,
  "tilt_x": 0.32,
  "tilt_y": 0.18,
  "displacement": 2.4,
  "vibration": 0.05,
  "crack_status": 0,
  "temperature": 25.1,
  "battery_level": 98.3,
  "signal_strength": 87.0
}
```

## 8. Feature Engineering

See [`ai/feature_engineering.py`](ai/feature_engineering.py). Raw readings are converted
into a small set of **physically meaningful** features:

- `tilt_magnitude` — combines `tilt_x`/`tilt_y` into one resultant value
- `displacement_rate`, `tilt_rate` — rate of change per minute (subsidence is a
  *process*; speed of change matters more than a single instantaneous value)
- `rolling_displacement_avg`, `rolling_tilt_avg`, `rolling_vibration_avg` — smooth out
  single-reading sensor noise over the last `ROLLING_WINDOW_SIZE` readings

We deliberately kept this to 8 features, each independently explainable to a judge,
rather than generating dozens of opaque derived columns.

## 9. Anomaly Detection

**Algorithm:** Isolation Forest (unsupervised), from scikit-learn.

**Why:** we need to flag "this combination of sensor values looks unusual" without a
large labelled failure dataset. Isolation Forest learns what "normal" looks like from
mostly-normal training data and isolates points that are easy to separate from the rest —
anomalies need fewer random partitions to isolate than typical points. It's lightweight,
fast to train, and easy to explain to a non-ML audience.

The raw isolation score is rescaled to **0–1** (1 = most anomalous) for dashboard display.
Threshold: `config.ANOMALY_SCORE_THRESHOLD` (default 0.6).

**An anomaly score is not proof of subsidence** — it means the current reading pattern
doesn't resemble the training data's normal operating conditions and warrants further
attention. See the risk engine for how this is combined with other signals.

## 10. Prediction Model

**Algorithm:** Linear Regression, from scikit-learn.

**Why:** during steady deformation, near-future displacement tends to relate roughly
linearly to the current displacement, its rate of change, and recent trend — a
relationship linear regression captures directly and transparently (its coefficients
can literally be read off to see which feature drives the prediction most). We only
reach for a more complex model if evaluation shows linear regression is clearly
insufficient — it currently is not (see metrics below).

**Horizon:** `config.PREDICTION_HORIZON_MINUTES` (default 5 minutes ahead).

Training/evaluation metrics from the last run of `ai/train_models.py` (on a held-out,
shuffled 20% test split of simulated data — **not training data**):

- MAE, RMSE, R² are printed by the training script — see terminal output when you run it.
  These numbers are **never fabricated**; if you retrain, your numbers will differ
  slightly due to the random simulator seed.

The output is presented as **"predicted displacement trend,"** never as a certainty —
e.g. never "subsidence will occur in 30 minutes."

## 11. Risk Engine

See [`ai/risk_engine.py`](ai/risk_engine.py). **No single ML model is the sole authority**
on whether to raise a warning. The risk engine combines, with configurable weights
(`config.RISK_WEIGHTS`):

- anomaly score
- predicted displacement
- displacement rate
- tilt rate
- vibration level
- crack detection

into a `risk_score` (0–100) and a `risk_level` (`LOW` / `MODERATE` / `HIGH` / `CRITICAL`),
plus a **human-readable list of contributing factors** shown in the dashboard's AI
Analysis panel — never an unexplained black-box number.

All weights and cut points live in `config.py`, explicitly labelled as prototype/
configurable values requiring domain validation before any real deployment.

## 12. GIS

Leaflet.js + OpenStreetMap tiles. The map shows:

- Each sensor node, colored by its current risk level, with a popup of live readings
- An **Inverse Distance Weighting (IDW)** interpolated risk-surface heatmap
  (`ai/gis_interpolation.py`, served via `GET /api/risk-grid`) — nearby sensor readings
  have more influence on the estimated value at a given map point than distant ones.

**This is a prototype visualization, not a geologically validated subsidence boundary.**
Real risk-surface mapping would require geotechnical surveying.

## 13. Real-Time Communication

**Approach:** AJAX polling every 3 seconds (`static/js/dashboard.js`), not WebSockets.

**Why:** for this node count and data rate, polling is simpler to reason about and debug
for a student team, and the added latency versus WebSockets (Flask-SocketIO) is not
operationally significant for a monitoring dashboard. This mirrors the approach used
successfully in a related prior SIH prototype. WebSockets remain a reasonable future
upgrade if node count grows significantly (see [Future Improvements](#22-future-improvements)).

## 14. Offline Synchronization

Demonstrated via the dashboard's **Demo Controls → Simulate Connection Loss**:

- While "offline," new readings are still written to SQLite (`synced=0`) but the AI
  pipeline does **not** run on them yet — mirroring a real edge gateway that keeps
  logging locally while it can't reach cloud analytics.
- **Sync Now** (`POST /api/sync`) flushes all queued readings, marks them synced, and
  retroactively runs the AI pipeline so risk scores and alerts catch up on what happened
  while offline.
- The dashboard header and Demo Controls panel show live gateway status and queued-
  reading count.

## 15. Alert System

See [`notifications/alert_service.py`](notifications/alert_service.py). An alert is
raised when any of the following holds:

- `risk_score` exceeds `config.ALERT_RISK_SCORE_THRESHOLD`
- the anomaly detector flags the reading as anomalous
- the crack sensor triggers
- displacement is increasing unusually fast

**Cooldown/de-duplication:** an identical-severity alert for the same node will not be
re-raised within `config.ALERT_COOLDOWN_SECONDS`, so the same ongoing condition doesn't
spam the operator with duplicate alerts. SMS/email integration is out of scope for the
prototype but the module is isolated so a real notification channel could be added
without touching risk-scoring logic.

## 16. Authentication

Session-based login (`werkzeug.security` password hashing — **never** plaintext) with
three roles:

| Role | Username | Password | Focus |
|---|---|---|---|
| Operator | `operator` | `operator123` | live monitoring, alerts |
| Planner | `planner` | `planner123` | trends, predictions |
| Regulator | `regulator` | `regulator123` | overview, historical incidents |

**Change these credentials before any real use** — they exist only for demo purposes.
All dashboard pages and API routes (except `/login`, static assets, and `/api/health`)
require an authenticated session.

## 17. Installation

```bash
git clone <this-repo>
cd mine-subsidence
pip install flask werkzeug scikit-learn numpy joblib
```

## 18. Running the Application

```bash
# 1. Set up the database and demo nodes/users (one time)
python database/seed.py

# 2. Train the AI models (one time — creates /models/*.joblib)
python ai/train_models.py

# 3. Run the app
python app.py
```

Then open **http://127.0.0.1:5000** and sign in with any of the demo credentials above.

## 19. Running the Simulator

The simulator runs inside the Flask app itself — no separate process needed. From the
dashboard, use **Demo Controls** to:

- Set an individual node's scenario (`NORMAL` … `CRITICAL_EVENT`)
- Run the full automated demo sequence (steps through every scenario with realistic
  timing so judges can watch risk escalate and recover live)

The dashboard automatically ticks the simulator every 3 seconds while open.

## 19b. Training Models

```bash
python ai/train_models.py
```

This regenerates the simulated training dataset, retrains both models, prints honest
evaluation metrics (MAE/RMSE/R² for the regressor; anomaly counts at the configured
threshold for the detector), and saves them to `/models`. **Run this before starting
the app for the first time** — without trained models, the API returns "no prediction
available yet" instead of crashing.

## 20. API Documentation

All endpoints require an authenticated session except `/login` and `/api/health`.

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/nodes` | List all registered sensor nodes |
| GET | `/api/readings/latest` | Most recent reading per node |
| GET | `/api/readings/<node_id>?limit=N` | Last N readings for a node |
| GET | `/api/history/<node_id>?start=&end=` | Readings within a time range |
| POST | `/api/sensor-data` | Ingest one reading (real hardware or simulator) |
| GET | `/api/prediction/<node_id>` | Latest AI prediction/risk for a node |
| GET | `/api/alerts?limit=N` | Recent alerts |
| POST | `/api/acknowledge-alert` | `{"alert_id": N}` |
| GET | `/api/risk-grid` | IDW-interpolated risk surface for the GIS map |
| GET / POST | `/api/connectivity` | Get/set simulated gateway online status |
| POST | `/api/sync` | Flush queued offline readings + catch up AI pipeline |
| GET | `/api/simulate/scenarios` | List valid simulator scenario names |
| POST | `/api/simulate/scenario` | `{"node_id": .., "scenario": ..}` |
| POST | `/api/simulate/tick` | Generate one new reading per node |
| GET | `/api/health` | Health check (no auth required) |

## 21. Limitations

- Prototype data is **simulated**; no real mine sensor data was used.
- Real mine deployment requires **field calibration** — the risk weights and thresholds
  in `config.py` are prototype values, not validated against geotechnical data.
- Geological conditions vary significantly between mining locations; a model trained on
  one panel's behavior may not transfer to another without retraining.
- Model performance depends entirely on the quality and quantity of historical data
  available at deployment time.
- Predictions are **decision-support information**, not guaranteed forecasts.
- Interpolated GIS risk zones are prototype visualizations, not validated geological
  subsidence boundaries.
- Real deployment requires safety, communications, and sensor-reliability testing well
  beyond the scope of this software prototype.
- **This prototype alone cannot guarantee worker or public safety.**

## 22. Future Improvements

The architecture is deliberately structured so each of these can replace a component
without rewriting the whole system:

- SQLite → PostgreSQL for multi-mine, higher-volume deployments
- Simulator → real ESP32 sensor nodes (the `/api/sensor-data` contract already supports this)
- AJAX polling → Flask-SocketIO, if node count/data rate grows enough to need it
- Linear Regression → a validated, more sophisticated model, once real labelled failure
  data exists to justify it
- Basic IDW heatmap → professional GIS/geospatial backend with real geotechnical layers
- Dashboard-only alerts → SMS/email/mobile push notifications (module already isolated
  in `notifications/alert_service.py`)

---

## How the AI Works (Plain-Language Summary)

1. Every few seconds, each sensor node reports tilt, displacement, vibration, and crack
   status.
2. We compute a handful of derived numbers — how fast things are changing, and rolling
   averages to smooth out noise.
3. An Isolation Forest model checks whether this pattern looks unusual compared to what
   it saw during training (mostly-normal conditions). This gives an anomaly score
   from 0 to 1.
4. A Linear Regression model estimates where displacement is trending over the next few
   minutes, based on the current rate of change.
5. A transparent risk engine combines the anomaly score, the prediction, and the raw
   rates/vibration/crack signal — each with a configurable weight — into one risk score
   from 0 to 100, and a plain-language explanation of what's driving it.
6. If the risk score (or a crack event, or an anomaly) crosses a threshold, an alert is
   raised — but not repeated every few seconds for the same ongoing condition.
7. Everything is shown on a live dashboard: a GIS map colored by risk, live sensor
   tables, trend charts, and an alerts panel an operator can acknowledge.

No step in this pipeline is a black box — every number on the dashboard traces back to
a specific, explainable calculation.
