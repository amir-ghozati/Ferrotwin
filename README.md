# FerroTwin

An end-to-end **computer-vision digital twin** for a steel production line, built
on Azure Digital Twins. Telemetry and AI surface-defect inspections stream into
a live twin graph; an alarm engine and analytics layer sit on top; a real-time
operations dashboard visualizes the whole line.

## Architecture

```
 demo_stream.py ──HTTP──► Azure Functions (Python) ──► Azure Digital Twins (twin graph)
   (telemetry +                │  │  │                        ▲
    inspections)               │  │  └── ONNX model (ResNet18) surface-defect classifier
                               │  └───── Blob Storage (private inspection images)
                               └──────── Table Storage (telemetry / inspection / alarm history)
                                              │
 Dashboard (static site) ◄──HTTP (x-functions-key)──┘  analytics · alarms · history · twins
```

Event Grid is supported (`EVENT_GRID_ENABLED=true`) but ships **disabled** — the
functions process events directly, which is simpler and identical for demos.

## Function API

| Route | Auth | Purpose |
|-------|------|---------|
| `GET /health`, `GET /ping` | anonymous | ADT connectivity / liveness |
| `POST /telemetry` | function key | update a stage twin + log reading + evaluate alarms |
| `POST /inspection` | function key | classify an image (ONNX), store it, update twins, log |
| `GET /analytics` | function key | KPIs: avg/max temp, inspection count, defect rate + frequency |
| `GET /alarms` | function key | recent alarms |
| `GET /history/telemetry`, `GET /history/inspections` | function key | time-series history |
| `GET /twins` | function key | full twin graph |
| `GET /inspection-image?blobUrl=` | function key | proxy a private inspection image |

## Digital twin graph

`Factory 01 → Line 01 → { stage01 Heating, stage02 Rolling, stage03 Cooling }`,
with `stage01 →feedsInto→ stage02 →feedsInto→ stage03`, and
`stage03 →contains→ inspection01` (Vision Station). DTDL models are v2/v3 in
`dtdl/`; the graph is built by `scripts/upload_models.py` + `scripts/create_twins.py`.

## Documentation

- **[docs/architecture.md](docs/architecture.md)** — components, twin graph, data-flow and sequence diagrams, alarm rules, storage, security.
- **[docs/api.md](docs/api.md)** — full REST API reference.
- **[DEPLOY.md](DEPLOY.md)** — deployment runbook.

## Deploy to Azure

See **[DEPLOY.md](DEPLOY.md)** — one command (`.\deploy.ps1`) reusing the
existing `ferrotwin-adt` instance, or manual step-by-step. To switch to the
asynchronous Event Grid architecture afterwards, run `.\deploy-eventgrid.ps1`
(optional).

## Run locally (Function host + Azurite + cloud ADT)

```powershell
# terminal 1: storage emulator
azurite --location .\.azurite

# terminal 2: functions (needs local.settings.json with your ADT_HOST)
func start --cors http://localhost:8080

# terminal 3: dashboard
python -m http.server 8080 --directory dashboard
# open http://localhost:8080 -> Connect API -> http://localhost:7071/api + a function key
```

## Preview the dashboard right now (no Azure)

Open **`dashboard/preview.html`** in a browser — a self-contained build with
realistic mock data, so you can see the full UI without deploying anything.

## Model

ResNet18 transfer learning on **NEU-CLS** (6 classes: crazing, inclusion,
patches, pitted_surface, rolled-in_scale, scratches), exported to ONNX. Serving
uses `onnxruntime` + NumPy only (no torch), keeping the deployment package small.
Training / export code is in `ml/`.

## Tests

```powershell
python -m unittest tests.test_services -v
```
