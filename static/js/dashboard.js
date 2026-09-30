/* static/js/dashboard.js
   -----------------------
   Polling-based real-time updates (see README "Real-Time Communication"
   for why AJAX polling was chosen over WebSockets for this prototype:
   it's simpler to reason about, easier to debug for a student team,
   and at this data rate/node count the extra latency of polling is not
   noticeable to an operator).
*/

const POLL_INTERVAL_MS = 3000;
const TICK_INTERVAL_MS = 3000;

let nodes = [];
let selectedNodeId = null;
let selectedMetric = "displacement";
let map = null;
let markers = {};
let riskHeatLayer = null;
let trendChart = null;
let lastHistory = [];

// ------------------------------------------------------------------
// Init
// ------------------------------------------------------------------
async function init() {
  nodes = await fetchJSON("/api/nodes");
  initMap();
  populateDemoNodeSelect();
  if (nodes.length > 0) selectNode(nodes[0].node_id);

  bindChartTabs();
  bindDemoControls();

  await refreshAll();
  setInterval(refreshAll, POLL_INTERVAL_MS);
  setInterval(tickSimulator, TICK_INTERVAL_MS);
}

async function fetchJSON(url, opts) {
  try {
    const res = await fetch(url, opts);
    if (!res.ok) return null;
    return await res.json();
  } catch (e) {
    setConnectionStatus(false);
    return null;
  }
}

function setConnectionStatus(online) {
  const el = document.getElementById("conn-status");
  if (online) {
    el.innerHTML = '<span class="status-dot online"></span>CONNECTED';
  } else {
    el.innerHTML = '<span class="status-dot offline"></span>OFFLINE — retrying';
  }
}

// ------------------------------------------------------------------
// Simulator tick (drives the demo forward)
// ------------------------------------------------------------------
async function tickSimulator() {
  await fetchJSON("/api/simulate/tick", { method: "POST" });
}

// ------------------------------------------------------------------
// Main refresh cycle
// ------------------------------------------------------------------
async function refreshAll() {
  const latest = await fetchJSON("/api/readings/latest");
  if (latest === null) { setConnectionStatus(false); return; }
  setConnectionStatus(true);
  document.getElementById("last-sync").textContent =
    "LAST SYNC: " + new Date().toLocaleTimeString();

  renderSensorTable(latest);
  updateMapMarkers(latest);
  await updateRiskHeatmap();
  await updateOverviewCards(latest);
  await refreshAlerts();

  if (selectedNodeId) {
    await refreshAiPanel(selectedNodeId);
    await refreshChart(selectedNodeId);
  }
}

// ------------------------------------------------------------------
// Sensor table
// ------------------------------------------------------------------
function renderSensorTable(readings) {
  const tbody = document.getElementById("sensor-table-body");
  if (!readings.length) {
    tbody.innerHTML = '<tr><td colspan="8" style="color:var(--text-faint); padding:16px;">No readings yet.</td></tr>';
    return;
  }
  tbody.innerHTML = "";
  readings.sort((a, b) => a.node_id.localeCompare(b.node_id));
  readings.forEach((r) => {
    const tr = document.createElement("tr");
    tr.className = r.node_id === selectedNodeId ? "selected" : "";
    tr.dataset.nodeId = r.node_id;
    const tiltMag = Math.sqrt(r.tilt_x ** 2 + r.tilt_y ** 2).toFixed(3);
    tr.innerHTML = `
      <td>${r.node_id}</td>
      <td>${tiltMag}</td>
      <td>${r.displacement.toFixed(2)}</td>
      <td>${r.vibration.toFixed(3)}</td>
      <td>${r.crack_status ? '<span class="crack-yes">YES</span>' : '<span class="crack-no">no</span>'}</td>
      <td class="anomaly-cell" data-node="${r.node_id}">—</td>
      <td class="risk-cell" data-node="${r.node_id}">—</td>
      <td>${new Date(r.timestamp).toLocaleTimeString()}</td>
    `;
    tr.addEventListener("click", () => selectNode(r.node_id));
    tbody.appendChild(tr);
  });
  readings.forEach((r) => fillRiskCell(r.node_id));
}

async function fillRiskCell(nodeId) {
  const pred = await fetchJSON(`/api/prediction/${nodeId}`);
  const anomalyCell = document.querySelector(`.anomaly-cell[data-node="${nodeId}"]`);
  const riskCell = document.querySelector(`.risk-cell[data-node="${nodeId}"]`);
  if (!pred || pred.message) {
    if (anomalyCell) anomalyCell.textContent = "—";
    if (riskCell) riskCell.innerHTML = '<span class="badge LOW">N/A</span>';
    return;
  }
  if (anomalyCell) {
    anomalyCell.textContent = pred.anomaly_score != null ? pred.anomaly_score.toFixed(2) : "—";
    anomalyCell.style.color = pred.is_anomalous ? "var(--risk-high)" : "var(--text-dim)";
  }
  if (riskCell && pred.risk_level) {
    riskCell.innerHTML = `<span class="badge ${pred.risk_level}">${pred.risk_level}</span>`;
  }
}

// ------------------------------------------------------------------
// Overview cards
// ------------------------------------------------------------------
async function updateOverviewCards(latest) {
  const activeNodes = nodes.filter((n) => n.status === "ACTIVE").length;
  const offlineNodes = nodes.filter((n) => n.status !== "ACTIVE").length;
  document.getElementById("ov-active-nodes").textContent = activeNodes;
  document.getElementById("ov-offline-nodes").textContent = offlineNodes;

  let anomalies = 0, highRisk = 0;
  for (const r of latest) {
    const pred = await fetchJSON(`/api/prediction/${r.node_id}`);
    if (pred && !pred.message) {
      if (pred.is_anomalous) anomalies++;
      if (pred.risk_level === "HIGH" || pred.risk_level === "CRITICAL") highRisk++;
    }
  }
  document.getElementById("ov-anomalies").textContent = anomalies;
  document.getElementById("ov-high-risk").textContent = highRisk;

  const alerts = await fetchJSON("/api/alerts?limit=200");
  const activeAlerts = alerts ? alerts.filter((a) => !a.acknowledged).length : 0;
  document.getElementById("ov-active-alerts").textContent = activeAlerts;
}

// ------------------------------------------------------------------
// Map
// ------------------------------------------------------------------
function initMap() {
  if (!nodes.length) return;
  const avgLat = nodes.reduce((s, n) => s + n.latitude, 0) / nodes.length;
  const avgLng = nodes.reduce((s, n) => s + n.longitude, 0) / nodes.length;
  map = L.map("map").setView([avgLat, avgLng], 15);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: "&copy; OpenStreetMap contributors",
    maxZoom: 19,
  }).addTo(map);

  nodes.forEach((n) => {
    const marker = L.circleMarker([n.latitude, n.longitude], {
      radius: 10,
      color: "#4c9a6a",
      fillColor: "#4c9a6a",
      fillOpacity: 0.6,
      weight: 2,
    }).addTo(map);
    marker.on("click", () => selectNode(n.node_id));
    markers[n.node_id] = marker;
  });
}

const RISK_COLORS = {
  LOW: "#4c9a6a",
  MODERATE: "#d9a441",
  HIGH: "#e07a3f",
  CRITICAL: "#c63b3b",
};

async function updateRiskHeatmap() {
  const grid = await fetchJSON("/api/risk-grid");
  if (!grid || !map) return;
  // Heat layer expects [lat, lng, intensity] with intensity 0-1.
  const points = grid.map((cell) => [cell.latitude, cell.longitude, cell.risk_score / 100]);
  if (riskHeatLayer) {
    map.removeLayer(riskHeatLayer);
  }
  riskHeatLayer = L.heatLayer(points, {
    radius: 35,
    blur: 25,
    maxZoom: 17,
    max: 1.0,
    gradient: { 0.0: "#4c9a6a", 0.3: "#d9a441", 0.55: "#e07a3f", 0.8: "#c63b3b" },
  }).addTo(map);
}

async function updateMapMarkers(latest) {
  for (const r of latest) {
    const marker = markers[r.node_id];
    if (!marker) continue;
    const pred = await fetchJSON(`/api/prediction/${r.node_id}`);
    const riskLevel = pred && !pred.message ? pred.risk_level : "LOW";
    const color = RISK_COLORS[riskLevel] || "#4c9a6a";
    marker.setStyle({ color, fillColor: color });
    const tiltMag = Math.sqrt(r.tilt_x ** 2 + r.tilt_y ** 2).toFixed(3);
    marker.bindPopup(`
      <b>${r.node_id}</b><br>
      Updated: ${new Date(r.timestamp).toLocaleTimeString()}<br>
      Tilt: ${tiltMag}&deg;<br>
      Displacement: ${r.displacement.toFixed(2)} mm<br>
      Vibration: ${r.vibration.toFixed(3)} g<br>
      Crack: ${r.crack_status ? "YES" : "no"}<br>
      Anomaly score: ${pred && !pred.message ? pred.anomaly_score.toFixed(2) : "—"}<br>
      Risk: <b>${riskLevel}</b>
    `);
  }
}

// ------------------------------------------------------------------
// Node selection
// ------------------------------------------------------------------
function selectNode(nodeId) {
  selectedNodeId = nodeId;
  document.getElementById("chart-node-label").textContent = nodeId;
  document.querySelectorAll("#sensor-table-body tr").forEach((tr) => {
    tr.classList.toggle("selected", tr.dataset.nodeId === nodeId);
  });
  refreshAiPanel(nodeId);
  refreshChart(nodeId);
}

function populateDemoNodeSelect() {
  const sel = document.getElementById("demo-node-select");
  sel.innerHTML = nodes.map((n) => `<option value="${n.node_id}">${n.node_id}</option>`).join("");
}

// ------------------------------------------------------------------
// AI Analysis panel
// ------------------------------------------------------------------
async function refreshAiPanel(nodeId) {
  const pred = await fetchJSON(`/api/prediction/${nodeId}`);
  const panel = document.getElementById("ai-panel");
  if (!pred || pred.message) {
    panel.innerHTML = `<div style="color:var(--text-faint);">No AI analysis yet for ${nodeId}. Waiting for enough readings to run the pipeline.</div>`;
    return;
  }
  const factors = (pred.contributing_factors || [])
    .map((f) => `<li>${f}</li>`)
    .join("");
  panel.innerHTML = `
    <div class="ai-row"><span class="k">Node</span><span class="v">${nodeId}</span></div>
    <div class="ai-row"><span class="k">Condition</span><span class="v">${pred.is_anomalous ? "Anomalous" : "Normal"}</span></div>
    <div class="ai-row"><span class="k">Anomaly score</span><span class="v">${pred.anomaly_score != null ? pred.anomaly_score.toFixed(2) : "—"}</span></div>
    <div class="ai-row"><span class="k">Predicted displacement</span><span class="v">${pred.predicted_displacement != null ? pred.predicted_displacement.toFixed(2) + " mm" : "—"}</span></div>
    <div class="ai-row"><span class="k">Risk score</span><span class="v">${pred.risk_score != null ? Math.round(pred.risk_score) + " / 100" : "—"}</span></div>
    <div class="ai-row"><span class="k">Risk level</span><span class="v"><span class="badge ${pred.risk_level}">${pred.risk_level}</span></span></div>
    ${factors ? `<div style="margin-top:8px; color:var(--text-dim); font-size:12px;">Contributing factors:</div><ul class="factor-list">${factors}</ul>` : ""}
  `;
}

// ------------------------------------------------------------------
// Trend chart
// ------------------------------------------------------------------
function bindChartTabs() {
  document.querySelectorAll(".chart-tabs button").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".chart-tabs button").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      selectedMetric = btn.dataset.metric;
      renderChartFromHistory();
    });
  });
}

async function refreshChart(nodeId) {
  const history = await fetchJSON(`/api/readings/${nodeId}?limit=40`);
  if (!history) return;
  lastHistory = history;
  renderChartFromHistory();
}

function renderChartFromHistory() {
  const labels = lastHistory.map((r) => new Date(r.timestamp).toLocaleTimeString());
  let data, label, unit, color;
  if (selectedMetric === "displacement") {
    data = lastHistory.map((r) => r.displacement);
    label = "Displacement"; unit = "mm"; color = "#4a9fd8";
  } else if (selectedMetric === "tilt") {
    data = lastHistory.map((r) => Math.sqrt(r.tilt_x ** 2 + r.tilt_y ** 2));
    label = "Tilt magnitude"; unit = "deg"; color = "#d9a441";
  } else {
    data = lastHistory.map((r) => r.vibration);
    label = "Vibration"; unit = "g"; color = "#e07a3f";
  }

  const ctx = document.getElementById("trend-chart").getContext("2d");
  if (trendChart) trendChart.destroy();
  trendChart = new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: [{
        label: `${label} (${unit})`,
        data,
        borderColor: color,
        backgroundColor: color + "22",
        fill: true,
        tension: 0.25,
        pointRadius: 0,
        borderWidth: 2,
      }],
    },
    options: {
      responsive: true,
      plugins: {
        legend: { labels: { color: "#d8dee4" } },
        tooltip: { mode: "index", intersect: false },
      },
      scales: {
        x: { ticks: { color: "#838f9b", maxTicksLimit: 8 }, grid: { color: "#2b333b" } },
        y: { ticks: { color: "#838f9b" }, grid: { color: "#2b333b" }, title: { display: true, text: unit, color: "#838f9b" } },
      },
    },
  });
}

// ------------------------------------------------------------------
// Alerts panel
// ------------------------------------------------------------------
async function refreshAlerts() {
  const alerts = await fetchJSON("/api/alerts?limit=20");
  const panel = document.getElementById("alerts-panel");
  if (!alerts || !alerts.length) {
    panel.innerHTML = '<div style="color:var(--text-faint);">No alerts yet.</div>';
    return;
  }
  panel.innerHTML = alerts.map((a) => `
    <div class="alert-item">
      <div class="alert-sev-bar ${a.severity}"></div>
      <div style="flex:1;">
        <div class="alert-message">${a.message}</div>
        <div class="alert-meta">${a.node_id} &middot; ${new Date(a.timestamp).toLocaleString()}</div>
      </div>
      ${a.acknowledged
        ? '<span style="color:var(--text-faint); font-size:11px;">Acknowledged</span>'
        : `<button class="ack-btn" data-alert-id="${a.id}">Acknowledge</button>`}
    </div>
  `).join("");

  panel.querySelectorAll(".ack-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      await fetchJSON("/api/acknowledge-alert", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ alert_id: parseInt(btn.dataset.alertId, 10) }),
      });
      refreshAlerts();
    });
  });
}

// ------------------------------------------------------------------
// Demo controls
// ------------------------------------------------------------------
function bindDemoControls() {
  document.getElementById("demo-apply-scenario").addEventListener("click", async () => {
    const nodeId = document.getElementById("demo-node-select").value;
    const scenario = document.getElementById("demo-scenario-select").value;
    await setScenario(nodeId, scenario);
  });

  document.getElementById("demo-run-sequence").addEventListener("click", runFullDemoSequence);

  document.getElementById("demo-toggle-connectivity").addEventListener("click", async () => {
    const status = await fetchJSON("/api/connectivity");
    const goOnline = status ? !status.online : true;
    await fetchJSON("/api/connectivity", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ online: goOnline }),
    });
    refreshConnectivityStatus();
  });

  document.getElementById("demo-sync-now").addEventListener("click", async () => {
    const result = await fetchJSON("/api/sync", { method: "POST" });
    if (result) {
      document.getElementById("last-sync").textContent =
        "LAST SYNC: " + new Date().toLocaleTimeString() + ` (${result.synced_count} synced)`;
    }
    refreshConnectivityStatus();
  });

  refreshConnectivityStatus();
  setInterval(refreshConnectivityStatus, POLL_INTERVAL_MS);
}

async function refreshConnectivityStatus() {
  const status = await fetchJSON("/api/connectivity");
  const el = document.getElementById("connectivity-status");
  const btn = document.getElementById("demo-toggle-connectivity");
  if (!status) return;
  if (status.online) {
    el.innerHTML = `Gateway status: <span style="color:var(--risk-low);">ONLINE</span>. Queued readings: ${status.queued_readings}.`;
    btn.textContent = "Simulate Connection Loss";
    setConnectionStatus(true);
  } else {
    el.innerHTML = `Gateway status: <span style="color:var(--risk-critical);">OFFLINE</span>. Queued readings: ${status.queued_readings} (not yet analyzed).`;
    btn.textContent = "Restore Connection";
    setConnectionStatus(false);
  }
}

async function setScenario(nodeId, scenario) {
  await fetchJSON("/api/simulate/scenario", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ node_id: nodeId, scenario }),
  });
}

async function runFullDemoSequence() {
  const nodeId = document.getElementById("demo-node-select").value;
  const sequence = [
    { scenario: "NORMAL", holdMs: 4000 },
    { scenario: "MINOR_ANOMALY", holdMs: 6000 },
    { scenario: "MODERATE_DEFORMATION", holdMs: 8000 },
    { scenario: "HIGH_RISK", holdMs: 8000 },
    { scenario: "CRITICAL_EVENT", holdMs: 8000 },
    { scenario: "RECOVERY", holdMs: 8000 },
  ];
  selectNode(nodeId);
  for (const step of sequence) {
    await setScenario(nodeId, step.scenario);
    await new Promise((resolve) => setTimeout(resolve, step.holdMs));
  }
}

init();
