/* FerroTwin Operations Center — dependency-light dashboard (Chart.js from CDN). */

const STAGES = [
  { id: "stage01", name: "Heating" },
  { id: "stage02", name: "Rolling" },
  { id: "stage03", name: "Cooling" },
];

const DEFECT_COLORS = {
  crazing: "#4aa8ff",
  inclusion: "#b48ead",
  patches: "#ffb454",
  pitted_surface: "#35d0d6",
  "rolled-in_scale": "#ff5f6d",
  scratches: "#3ddc97",
  ok: "#8ba1ab",
};
const STAGE_COLORS = ["#3ddc97", "#4aa8ff", "#ffb454"];
const REFRESH_SECONDS = 5;
const TEMP_MIN = 20, TEMP_MAX = 1000; // gauge scaling range (°C)

const state = {
  apiUrl: sessionStorage.getItem("ferrotwin-api-url") || "",
  key: sessionStorage.getItem("ferrotwin-function-key") || "",
  objectUrl: null,
  stageReadings: {},
  paused: false,
  countdown: REFRESH_SECONDS,
  lastSuccessTime: null,
  charts: {},
};

const $ = (id) => document.getElementById(id);
const apiUrl = () => state.apiUrl.replace(/\/$/, "");
const headers = () => ({ "x-functions-key": state.key });
const esc = (v) => String(v ?? "—").replace(/[&<>'"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" }[c]));
const time = (v) => (v ? new Date(v).toLocaleString() : "—");
const clock = (v) => (v ? new Date(v).toLocaleTimeString() : "—");
const temp = (v) => (v === undefined || v === null || Number.isNaN(Number(v)) ? "—" : `${Number(v).toFixed(1)}°C`);
const titleCase = (v) => String(v || "").replace(/[_-]/g, " ");

function setConnection(status, text) { const el = $("connection-status"); el.className = `connection ${status}`; el.textContent = text; }
async function get(path) {
  const sep = path.includes("?") ? "&" : "?";

  const res = await fetch(
    `${apiUrl()}${path}${sep}_=${Date.now()}`,
    {
      headers: headers(),
      cache: "no-store"
    }
  );

  if (!res.ok)
    throw new Error(`Request failed (${res.status}) on ${path}`);

  return res.json();
}

function fillStageSelectors() {
  const opts = STAGES.map((s) => `<option value="${s.id}">${s.name} (${s.id})</option>`).join("");
  $("inspection-stage").innerHTML = opts;
}

/* ---------- Chart.js theme + factories ---------- */
function initCharts() {
  if (!window.Chart) return;
  Chart.defaults.color = "#8ba1ab";
  Chart.defaults.font.family = "Inter, sans-serif";
  Chart.defaults.font.size = 11;

  state.charts.temperature = new Chart($("temperature-chart"), {
    type: "line",
    data: { labels: [], datasets: STAGES.map((s, i) => ({
      label: s.name, data: [], borderColor: STAGE_COLORS[i], backgroundColor: STAGE_COLORS[i] + "22",
      tension: 0.35, borderWidth: 2, pointRadius: 0, fill: true,
    })) },
    options: {
      responsive: true, maintainAspectRatio: false, interaction: { mode: "index", intersect: false },
      plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c) => `${c.dataset.label}: ${c.parsed.y?.toFixed(1)}°C` } } },
      scales: {
        x: { grid: { color: "rgba(34,52,65,.35)" }, ticks: { maxTicksLimit: 7 } },
        y: { grid: { color: "rgba(34,52,65,.35)" }, ticks: { callback: (v) => v + "°" } },
      },
    },
  });

  state.charts.donut = new Chart($("defect-donut"), {
    type: "doughnut",
    data: { labels: [], datasets: [{ data: [], backgroundColor: [], borderColor: "#0c141b", borderWidth: 2 }] },
    options: {
      responsive: true, maintainAspectRatio: false, cutout: "62%",
      plugins: { legend: { position: "right", labels: { boxWidth: 11, padding: 12, font: { size: 11 } } } },
    },
  });

  state.charts.timeline = new Chart($("defect-timeline"), {
    type: "bar",
    data: { labels: [], datasets: [] },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false }, tooltip: { mode: "index" } },
      scales: {
        x: { stacked: true, grid: { display: false } },
        y: { stacked: true, grid: { color: "rgba(34,52,65,.35)" }, ticks: { precision: 0 }, beginAtZero: true },
      },
    },
  });
}

/* ---------- Renderers ---------- */
function renderKpis(summary, alarms) {
  $("kpi-avg-temp").textContent = temp(summary.averageTemperature);
  $("kpi-max-temp").textContent = temp(summary.maximumTemperature);
  $("kpi-inspections").textContent = summary.inspectionCount ?? "—";
  $("kpi-defect-rate").textContent = summary.defectRate == null ? "—" : `${(summary.defectRate * 100).toFixed(1)}%`;
  const open = alarms.filter((a) => a.severity === "critical").length;
  $("kpi-alarms").textContent = alarms.length;
  $("kpi-alarms-sub").textContent = open ? `${open} critical` : "no critical alarms";
  const freq = summary.defectFrequency || {};
  const top = Object.entries(freq).sort((a, b) => b[1] - a[1])[0];
  $("kpi-top-defect").textContent = top ? titleCase(top[0]) : "None";
  $("kpi-top-defect-sub").textContent = top ? `${top[1]} detections` : "no defects yet";
}

function renderStages(twins, readings) {
  const byId = Object.fromEntries(twins.map((t) => [t.$dtId, t]));
  $("stages").innerHTML = STAGES.map((s) => {
    const twin = byId[s.id] || {};
    const reading = readings[s.id]?.[0] || {};
    const t = twin.temperature ?? reading.temperature;
    const status = twin.status ?? reading.status ?? "Unknown";
    const cls = /error|fault|failed/i.test(status) ? "error" : /running/i.test(status) ? "running" : "";
    const defect = twin.lastDetectedDefect;
    const pct = Math.max(4, Math.min(100, ((Number(t) - TEMP_MIN) / (TEMP_MAX - TEMP_MIN)) * 100)) || 4;
    const chip = defect ? `<span class="chip">${esc(titleCase(defect))}</span>` : `<span class="chip ok">No defect</span>`;
    return `<article class="stage-card ${cls}">
      <div class="stage-head"><h3>${esc(twin.name || s.name)}</h3><span class="stage-status ${cls}">${esc(status)}</span></div>
      <div class="stage-temp"><b>${t == null ? "—" : Number(t).toFixed(1)}</b><span>°C</span></div>
      <div class="stage-gauge"><div style="width:${pct}%"></div></div>
      <div class="stage-defect">Last defect: ${chip}</div>
    </article>`;
  }).join("");
}

function renderTemperatureChart() {
  const chart = state.charts.temperature;
  if (!chart) return;
  const series = STAGES.map((s) => (state.stageReadings[s.id] || []).slice(0, 30).reverse());
  const longest = series.reduce((a, b) => (b.length > a.length ? b : a), []);
  chart.data.labels = longest.map((r) => clock(r.recordedAt));
  series.forEach((rows, i) => { chart.data.datasets[i].data = rows.map((r) => Number(r.temperature)); });
  chart.update("none");
  $("temp-legend").innerHTML = STAGES.map((s, i) => `<span><i style="background:${STAGE_COLORS[i]}"></i>${s.name}</span>`).join("");
}

function renderDonut(freq) {
  const chart = state.charts.donut;
  if (!chart) return;
  const entries = Object.entries(freq || {}).sort((a, b) => b[1] - a[1]);
  chart.data.labels = entries.map(([k]) => titleCase(k));
  chart.data.datasets[0].data = entries.map(([, v]) => v);
  chart.data.datasets[0].backgroundColor = entries.map(([k]) => DEFECT_COLORS[k] || "#8ba1ab");
  chart.update("none");
  const total = entries.reduce((sum, [, v]) => sum + v, 0);
  $("defect-total").textContent = total ? `${total} defects` : "no defects";
}

function bucketInspections(inspections, nBuckets = 8) {
  const items = inspections.filter((i) => i.recordedAt).map((i) => ({ t: new Date(i.recordedAt).getTime(), d: i.defect || "ok" }));
  if (!items.length) return { labels: [], classes: [], counts: [] };
  const min = Math.min(...items.map((i) => i.t)), max = Math.max(...items.map((i) => i.t));
  const span = Math.max(max - min, 1), width = span / nBuckets;
  const labels = [], counts = Array.from({ length: nBuckets }, () => ({}));
  for (let b = 0; b < nBuckets; b++) labels.push(clock(new Date(min + width * (b + 0.5))));
  const classSet = new Set();
  items.forEach((i) => {
    const b = Math.min(nBuckets - 1, Math.floor((i.t - min) / width));
    counts[b][i.d] = (counts[b][i.d] || 0) + 1;
    classSet.add(i.d);
  });
  return { labels, classes: [...classSet], counts };
}

function renderTimeline(inspections) {
  const chart = state.charts.timeline;
  if (!chart) return;
  const { labels, classes, counts } = bucketInspections(inspections, 8);
  chart.data.labels = labels;
  chart.data.datasets = (classes || []).map((c) => ({
    label: titleCase(c), data: counts.map((b) => b[c] || 0),
    backgroundColor: DEFECT_COLORS[c] || "#8ba1ab", borderRadius: 3, stack: "defects",
  }));
  chart.update("none");
}

function renderAlarms(items) {
  $("alarm-count").textContent = items.length;
  $("alarms").innerHTML = items.length
    ? items.slice(0, 12).map((a) => `<div class="alarm ${esc(a.severity)}">
        <div class="alarm-row"><strong>${esc(titleCase(a.alarmType))} · ${esc(a.PartitionKey)}</strong><span class="sev ${esc(a.severity)}">${esc(a.severity)}</span></div>
        <p>${esc(a.message)}</p><small>${time(a.recordedAt)}</small></div>`).join("")
    : '<p class="empty-state">No alarms recorded — line is healthy.</p>';
  const banner = $("alert-banner");
  const critical = items.find((a) => a.severity === "critical");
  banner.classList.toggle("hidden", !critical);
  banner.textContent = critical ? `Critical: ${critical.message}` : "";
}

function renderExplorer(twins) {
  $("twin-count").textContent = twins.length;
  const order = { Factory: 0, ProductionLine: 1, ProcessStage: 2, InspectionStation: 3 };
  const modelName = (t) => (t.$metadata?.$model || "").split(":").pop().replace(/;.*/, "");
  const sorted = [...twins].sort((a, b) => (order[modelName(a)] ?? 9) - (order[modelName(b)] ?? 9));
  $("twin-explorer").innerHTML = sorted.length
    ? sorted.map((t) => {
        const stateText = t.temperature != null ? temp(t.temperature) : (t.lastDefect ? titleCase(t.lastDefect) : (t.status || t.name || "—"));
        return `<div class="twin-row"><div><div class="twin-id">${esc(t.$dtId)}</div><div class="twin-model">${esc(modelName(t))}</div></div><div class="twin-state">${esc(stateText)}</div></div>`;
      }).join("")
    : '<p class="empty-state">No twins returned.</p>';
}

function renderHistory(items) {
  $("inspection-history").innerHTML = items.length
    ? items.slice(0, 10).map((i) => `<tr>
        <td>${clock(i.recordedAt)}</td><td>${esc(i.PartitionKey)}</td>
        <td><span class="pill" style="color:${DEFECT_COLORS[i.defect] || "#8ba1ab"}">${esc(titleCase(i.defect))}</span></td>
        <td class="conf-cell">${(Number(i.confidence) * 100).toFixed(1)}%</td></tr>`).join("")
    : '<tr><td colspan="4" class="empty-state">No inspection history found.</td></tr>';
}

async function renderLatestInspection(item) {
  $("inspection-confidence").textContent = item ? `${(Number(item.confidence) * 100).toFixed(1)}%` : "—";
  const conf = item ? Number(item.confidence) * 100 : 0;
  $("confidence-fill").style.width = `${conf}%`;
  $("confidence-text").textContent = item ? `${conf.toFixed(1)}% confidence` : "—";
  $("inspection-details").innerHTML = item
    ? `<strong style="color:${DEFECT_COLORS[item.defect] || "#eef4f6"}">${esc(titleCase(item.defect))}</strong><span>${esc(item.PartitionKey)} · ${time(item.recordedAt)}</span>`
    : "<strong>—</strong><span>No inspection history found.</span>";
  const wrap = $("inspection-image-wrap");
  if (!item?.imageUrl) { wrap.innerHTML = "<span>No image</span>"; return; }
  try {
    const res = await fetch(
      `${apiUrl()}/inspection-image?blobUrl=${encodeURIComponent(item.imageUrl)}`,
      {
          headers: headers(),
          cache: "no-store"
      }
  );
    if (!res.ok) throw new Error();
    const blob = await res.blob();
    if (state.objectUrl) URL.revokeObjectURL(state.objectUrl);
    state.objectUrl = URL.createObjectURL(blob);
    wrap.innerHTML = `<img src="${state.objectUrl}" alt="Latest ${esc(item.defect)} inspection" />`;
  } catch { wrap.innerHTML = "<span>Private image unavailable</span>"; }
}

/* ---------- Refresh loop ---------- */
async function refresh() {
  if (!state.apiUrl || !state.key) { setConnection("offline", "Not connected"); return; }
  try {
    const [health, twins, summary, alarms, inspections, ...telemetry] = await Promise.all([
      get("/health").catch(() => ({})),
      get("/twins"),
      get("/analytics?limit=500"),
      get("/alarms?limit=50"),
      get("/history/inspections?limit=60"),
      ...STAGES.map((s) => get(`/history/telemetry?stageId=${s.id}&limit=50`)),
    ]);
    state.stageReadings = Object.fromEntries(STAGES.map((s, i) => [s.id, telemetry[i].items]));

    renderKpis(summary, alarms.items);
    renderStages(twins.items, state.stageReadings);
    renderTemperatureChart();
    renderDonut(summary.defectFrequency);
    renderTimeline(inspections.items);
    renderAlarms(alarms.items);
    renderExplorer(twins.items);
    renderHistory(inspections.items);
    await renderLatestInspection(inspections.items[0]);

    if (health.factory) $("meta-factory").textContent = health.factory;
    $("meta-eventmode").textContent = health.eventGridEnabled ? "Event Grid" : "Direct";
    $("footer-health").textContent = `ADT connected · ${twins.items.length} twins · model ${health.model || "n/a"}`;
    $("last-updated").textContent = `Last updated ${new Date().toLocaleTimeString()}`;
    setConnection("online", "Connected");
    state.countdown = REFRESH_SECONDS;
    state.lastSuccessTime = Date.now();
  } catch (err) {
    console.error(err);
    setConnection("error", "Connection failed");
    $("last-updated").textContent = err.message;
    $("footer-health").textContent = "Connection error";
  }
}
const STALE_ORANGE_MS = 60 * 1000;
const STALE_RED_MS = 3 * 60 * 1000;
const GRACE_MS = 15 * 1000;

function updateLiveBadge() {
  const badge = document.querySelector(".live-tag");
  if (!badge || !state.lastSuccessTime) return;
  const elapsed = Date.now() - state.lastSuccessTime;
  badge.classList.remove("live-tag-stale", "live-tag-dead");

  if (elapsed < GRACE_MS) {
    badge.innerHTML = `<span class="live-dot"></span>🟢 LIVE`;
    return;
  }
  const s = Math.floor(elapsed / 1000);
  badge.innerHTML = `<span class="live-dot"></span>● No telemetry received for ${s}s`;
  if (elapsed >= STALE_RED_MS) badge.classList.add("live-tag-dead");
  else if (elapsed >= STALE_ORANGE_MS) badge.classList.add("live-tag-stale");
}
function tick() {
  updateLiveBadge();
  if (state.paused || !state.apiUrl || !state.key) { $("refresh-countdown").textContent = state.paused ? "paused" : "—"; return; }
  state.countdown -= 1;
  $("refresh-countdown").textContent = `${Math.max(state.countdown, 0)}s`;
  if (state.countdown <= 0) { state.countdown = REFRESH_SECONDS; refresh(); }
}

/* ---------- Events ---------- */
$("configure-button").addEventListener("click", () => { $("api-url").value = state.apiUrl; $("function-key").value = state.key; $("configuration-dialog").showModal(); });
$("close-dialog").addEventListener("click", () => $("configuration-dialog").close());
$("configuration-form").addEventListener("submit", (e) => {
  e.preventDefault();
  state.apiUrl = $("api-url").value.replace(/\/$/, "");
  state.key = $("function-key").value;
  sessionStorage.setItem("ferrotwin-api-url", state.apiUrl);
  sessionStorage.setItem("ferrotwin-function-key", state.key);
  $("configuration-dialog").close();
  refresh();
});
$("refresh-button").addEventListener("click", refresh);
$("pause-button").addEventListener("click", () => {
  state.paused = !state.paused;
  $("pause-button").textContent = state.paused ? "Resume" : "Pause";
  $("refresh-indicator").classList.toggle("active", !state.paused);
});
$("inspection-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const file = $("inspection-file").files[0];
  if (!file) return;
  const form = new FormData();
  form.append("image", file);
  form.append("stageId", $("inspection-stage").value);
  $("inspection-result").textContent = "Uploading and running inference…";
  try {
    const res = await fetch(`${apiUrl()}/inspection`, { method: "POST", headers: headers(), body: form });
    const result = await res.json();
    if (!res.ok) throw new Error(result.message || "Inspection failed");
    $("inspection-result").textContent = `✓ ${titleCase(result.defect)} — ${(result.confidence * 100).toFixed(1)}% confidence`;
    $("inspection-file").value = "";
    await refresh();
  } catch (err) { $("inspection-result").textContent = err.message; }
});

/* ---------- Boot ---------- */
fillStageSelectors();
initCharts();
$("refresh-indicator").classList.add("active");
if (state.apiUrl && state.key) refresh();
setInterval(tick, 1000);
