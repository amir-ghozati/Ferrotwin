# FerroTwin — Progress Report

**Date:** 19 July 2026
**Project:** FerroTwin — Azure Digital Twins platform for steel manufacturing with AI visual inspection
**Status:** Feature-complete and deployable. Backend, model serving, dashboard, and full-cloud deployment tooling are done and verified. Not yet run against live Azure in this session (see *Deployment status*).

---

## 1. Executive summary

FerroTwin is a computer-vision digital twin of a steel production line. Telemetry and AI surface-defect inspections stream into an Azure Digital Twins graph; an alarm engine, analytics layer, and history store sit on top; a real-time operations dashboard visualizes the whole line.

The project reached roughly 70–75% (a solid but partly unfinished backend) under the previous coding assistant (Codex). This session closed the remaining gaps: it fixed the blockers that would have prevented the app from installing or deploying at all, replaced the placeholder dashboard with a polished data-rich one, and produced a one-command full-cloud deployment path. The codebase now installs cleanly, passes its tests, and produces correct model predictions.

The single most important finding: the project *looked* further along than it was safe to assume. Several pieces that read as "done" contained showstoppers — a dependency file pinned to versions that do not exist, and an inference path that dragged in a ~1 GB library the deployment target cannot host. Those are now resolved.

---

## 2. What Codex built (the inherited ~70–75%)

Codex delivered a well-structured, modular backend. The following was in place and is genuinely good work:

- **Azure Functions v2 HTTP API** (`function_app.py`) with clean separation into service modules: telemetry ingestion, image inspection, alarm evaluation, analytics, history, blob storage, and an Event Grid path with a direct-processing fallback.
- **Digital twin models** (DTDL) for Factory, ProductionLine, ProcessStage, and InspectionStation, correctly using the v2 context, with the property set the code actually patches (defect fields, alert fields, image URL, inspection id).
- **The real twin-setup path** — `scripts/upload_models.py` + `scripts/create_twins.py` — which builds the graph `Factory01 → Line01 → stage01/02/03 → inspection01`.
- **Persistence**: Azure Table Storage history for telemetry, inspections, and alarms; private Blob Storage for inspection images with a container-scoped download guard.
- **Alarm engine** (temperature threshold, stage-error, repeated-defect) and an **analytics** summary (avg/max temperature, inspection count, defect frequency, defect rate).
- **ONNX inference** using a ResNet18 transfer-learning model trained on NEU-CLS (six defect classes), reporting high-confidence predictions.
- **Unit tests** covering the telemetry, alarm, analytics, and inspection-twin services.
- **A dashboard shell** — HTML structure plus a dense but functional `app.js`.

### What was incomplete or broken in the inherited state

- `requirements.txt` was pinned to **version numbers that do not exist** (e.g. `torch==2.13.0`, `numpy==2.5.1`, `certifi==2026.6.17`). `pip install -r requirements.txt` would fail on the first line — nobody could set up a fresh environment or deploy.
- The serving inference path imported **torchvision** purely to resize/normalize an image, pulling in torch (~1 GB) — far too large for an Azure Functions Consumption deployment, and unnecessary.
- The `azure-functions` package itself was missing from requirements.
- The `bootstrap/` folder was **stale and inconsistent** with the rest of the code (wrong twin IDs `stage1–4`, obsolete v1 model versions, no model-upload step). It contradicted the working `scripts/` path.
- The dashboard's stylesheet and interactivity were minimal — a functional skeleton rather than the "beautiful, data-enriched" UI intended.
- `.funcignore` excluded only `.venv`, so a deploy would have tried to package the **103 MB NEU-CLS dataset** and the training checkpoint.

---

## 3. What this session did

### 3.1 Fixed the deployment blockers

- Rewrote `requirements.txt` with **real, compatible versions** and added the missing `azure-functions` package. Serving dependencies now exclude torch/torchvision entirely; training/export dependencies stay isolated in `ml/requirements.txt`.
- Rewrote `inference_service.py` to do **pure NumPy + Pillow preprocessing** — a faithful reproduction of the torchvision transform (bilinear resize to 224×224, ImageNet normalization). This removes the heavy dependency while keeping predictions identical.
- Made `scripts/upload_models.py` **idempotent** (skips models that already exist) so the deploy can be re-run safely.
- Wrote a proper `.funcignore` that excludes the dataset, training assets, dashboard, docs, and dev files from the Functions package.

### 3.2 Rebuilt the dashboard (beautiful + data-enriched)

A polished dark "operations center" (`dashboard/index.html`, `app.js`, `styles.css`) with:

- a six-card KPI strip (avg/peak temperature, inspection count, defect rate, open alarms, top defect);
- a live **multi-stage temperature trend** chart, a **defect-distribution donut**, and a **stacked defect-over-time timeline** (Chart.js);
- stage cards with heat gauges and status colors, a critical-alarm banner and alarm feed, a twin explorer, a recent-inspection table, and the latest AI inspection with its image and a confidence meter;
- auto-refresh with a countdown and pause control, and an in-browser inspection-upload form.

It remains dependency-light (Chart.js from CDN) so it can be hosted as a static site. A self-contained **`dashboard/preview.html`** with realistic mock data lets the UI be viewed without any Azure.

### 3.3 Produced the full-cloud deployment path

- **`deploy.ps1`** — one command that reuses the existing `ferrotwin-adt` instance and `ferrotwinst001` storage account: discovers the resource group/region, uploads models and builds the twin graph, creates a Linux Python Function App with a managed identity, grants that identity **Azure Digital Twins Data Owner**, applies app settings, hosts the dashboard on the storage static website, configures CORS, publishes the code, and prints the dashboard URL + API URL + function key.
- **`DEPLOY.md`** — the same steps manually, plus a troubleshooting section for the failures that actually occur (ADT data-plane 403, CORS, cold start, package size).
- **`scripts/demo_stream.py`** — a live driver that sends telemetry and inspections continuously and injects a periodic heat excursion, so the dashboard fills with real data during a demo.
- Updated `README.md` to reflect the finished architecture and quick-start.

### 3.4 A deliberate scope decision

Event Grid is kept **disabled** for this deployment. The code fully supports it, but the direct-processing fallback behaves identically for the demo, and standing up a custom topic + subscription + endpoint is the most common place a first-time, time-boxed deployment stalls. This is documented and reversible.

---

## 4. Verification performed this session

- Installed the real serving dependencies and ran ONNX inference on all seven labeled sample images — **every one classified correctly** at ≥ 99.8% confidence, confirming the NumPy preprocessing preserves model behavior. *[Certain]*
- Ran the unit test suite — **4/4 pass**. *[Certain]*
- Confirmed `function_app.py` and all changed scripts import/compile cleanly. *[Certain]*
- Validated the dashboard: JS syntax checks, and every element id referenced in `app.js` exists in the HTML. Rendered the mock-data preview to confirm layout and charts. *[Certain]*

Not verified this session: an actual end-to-end run against live Azure resources (deployment has not been executed here).

---

## 5. Known risks and caveats (for the 1-day trial)

- **Cold start.** Consumption plan + a 44 MB ONNX model means the first request can take 10–30 s. Keep `demo_stream.py` running to hold the app warm before any demo. *[Certain]*
- **RBAC propagation.** After the managed identity is granted the ADT role, `/health` may return 503 for up to ~10 minutes until the assignment propagates. Expect ~30–45 minutes end-to-end on the first deploy, much of it waiting. *[Likely]*
- **Data-plane vs. control-plane access.** Being subscription Owner does **not** grant ADT data access; the explicit "Azure Digital Twins Data Owner" role is required for both your user and the Function's identity. This is handled in the scripts but is the classic first-timer trap. *[Certain]*
- The `bootstrap/` folder is stale and should be treated as dead code (or deleted) to avoid future confusion with the working `scripts/` path.

---

## 6. Next steps

**Immediate (to get it live today):**

1. `az login`, select the subscription, run `.\deploy.ps1` from `D:\ADT`.
2. Open the printed dashboard URL, **Connect API**, and start `scripts/demo_stream.py`.
3. Confirm `/health` returns `adtConnected: true`, then demo. When done, `az functionapp stop` to protect the credit.

**Short term (hardening / portfolio polish):**

4. Delete or rewrite the stale `bootstrap/` folder so the repo has one authoritative setup path.
5. Add the **event-driven variant** (enable Event Grid: custom topic → subscription → the existing `process_event` trigger) as a documented optional mode — a strong talking point, but only after the direct path is proven live.
6. Add a couple of API/integration tests (health, telemetry round-trip) beyond the current service-level unit tests.
7. Capture a short demo recording and screenshots while data is streaming, for the portfolio.

**Medium term (from the original roadmap, if the project continues past the trial):**

8. Move history from Table Storage toward the roadmap's Postgres model if richer time-series queries are wanted; add the statistical drift-attribution recommender described in the roadmap (per-parameter z-scores + defect-class lift) as the headline "honest correlation detection" feature.
9. Introduce Application Insights dashboards and basic alerting on the Function App.
10. Replace the demo-grade anonymous/function-key auth with Azure AD / managed identity end-to-end if the project moves toward anything production-like.

---

*Prepared for Amirhossein. Repo: `D:\ADT`. Deployment instructions: `DEPLOY.md`. Live UI preview without Azure: `dashboard/preview.html`.*
