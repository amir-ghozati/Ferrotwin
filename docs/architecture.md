# FerroTwin — Architecture

FerroTwin is a computer-vision **digital twin** of a steel production line on
Azure. Telemetry and AI surface-defect inspections continuously update a live
twin graph; an alarm engine, analytics layer, and historical store sit on top;
a static dashboard visualizes the line in real time.

---

## 1. Components

| Component | Technology | Responsibility |
|-----------|------------|----------------|
| Twin graph | Azure Digital Twins (DTDL v2/v3) | Live model of factory → line → stages → inspection station |
| API / compute | Azure Functions (Python, Linux Consumption) | Telemetry + inspection ingestion, history/analytics/alarm APIs, watchdog timer, Event Grid consumer |
| Vision model | ONNX Runtime (ResNet18, NEU-CLS) | 6-class surface-defect classification |
| History | Azure Table Storage | Telemetry, inspection, and alarm records |
| Images | Azure Blob Storage (private) | Inspection images, referenced by URL on the twin |
| Dashboard | Static HTML/JS + Chart.js on Storage static website | Real-time operations view |
| Messaging (optional) | Azure Event Grid custom topic | Asynchronous, decoupled ingestion |

```mermaid
flowchart LR
    SIM["demo_stream.py<br/>(telemetry + inspections)"] -->|HTTP + x-functions-key| FUNC
    subgraph FUNC["Azure Functions (Python)"]
        TEL["/telemetry"]
        INS["/inspection"]
        API["/analytics /alarms<br//history /twins"]
        WD["watchdog (timer)"]
        EVT["process_event<br/>(Event Grid trigger)"]
    end
    INS --> ONNX["ONNX ResNet18"]
    FUNC -->|patch twins| ADT[("Azure Digital Twins")]
    FUNC -->|history| TBL[("Table Storage")]
    INS -->|image| BLOB[("Blob Storage")]
    WD --> ADT
    DASH["Dashboard<br/>(static website)"] -->|HTTP polling every 5s| API
    API --> ADT
    API --> TBL
    EG{{"Event Grid topic<br/>(optional)"}} -.-> EVT
    TEL -.publish.-> EG
    INS -.publish.-> EG
```

---

## 2. Digital twin graph

```mermaid
flowchart TD
    F["factory01<br/>Factory"] -->|contains| L["line01<br/>ProductionLine"]
    L -->|contains| S1["stage01 · Heating<br/>ProcessStage"]
    L -->|contains| S2["stage02 · Rolling<br/>ProcessStage"]
    L -->|contains| S3["stage03 · Cooling<br/>ProcessStage"]
    S1 -->|feedsInto| S2
    S2 -->|feedsInto| S3
    S3 -->|contains| I1["inspection01<br/>InspectionStation"]
```

**Models** (`dtdl/`): `Factory;2`, `ProductionLine;2`, `ProcessStage;3`,
`InspectionStation;3` — all on the DTDL **v2 context** (chosen for ADT Explorer
compatibility). `ProcessStage` holds `status`, `temperature`,
`lastDetectedDefect`, `lastDefectConfidence`, and `lastAlert{Level,Message,Time}`.
`InspectionStation` holds `cameraId`, `lastDefect`, `confidence`,
`lastInspectionTime`, `lastImageUrl`, `lastInspectionId`.

The graph is built idempotently by `scripts/upload_models.py` (models) and
`scripts/create_twins.py` (twins + relationships).

---

## 3. Telemetry flow

```mermaid
sequenceDiagram
    participant C as Client (demo_stream)
    participant F as Function /telemetry
    participant A as Azure Digital Twins
    participant T as Table Storage
    participant AL as Alarm engine
    C->>F: POST {stageId, temperature, status}
    F->>A: patch stage twin (temperature, status)
    F->>T: append StageReadings row
    F->>AL: evaluate_telemetry()
    AL->>T: append ProductionAlerts (if any)
    AL->>A: patch lastAlert* (if any)
    F-->>C: 200 {status, updatedTwin, alarms}
```

## 4. Inspection flow

```mermaid
sequenceDiagram
    participant C as Client
    participant F as Function /inspection
    participant M as ONNX model
    participant B as Blob Storage
    participant A as Azure Digital Twins
    participant T as Table Storage
    C->>F: POST multipart image (+ stageId, stationId)
    F->>M: classify image
    M-->>F: {defect, confidence}
    F->>B: upload private image -> URL
    F->>A: patch stage + inspection twins
    F->>T: append InspectionHistory row
    F->>F: alarm evaluation (repeated_defect, low_confidence)
    F-->>C: 200 {defect, confidence, imageUrl, alarms}
```

---

## 5. Ingestion modes

**Direct (default, `EVENT_GRID_ENABLED=false`)** — the HTTP handler performs the
twin update, history write, and alarm evaluation inline and returns `200`.
Simple and fully synchronous.

**Event-driven (`EVENT_GRID_ENABLED=true`)** — the handler publishes an event to
a custom Event Grid topic and returns `202 Accepted`; the `process_event`
trigger consumes it and does the work asynchronously. Decoupled and scalable.
Because events originate from our own handlers (not from ADT twin-change routes),
`process_event` never re-triggers itself — there is no feedback loop. Enable with
`deploy-eventgrid.ps1`.

```mermaid
flowchart LR
    H["/telemetry, /inspection"] -->|publish| TOP{{"Event Grid topic"}}
    TOP -->|subscription| PE["process_event"]
    PE --> ADT[("ADT")]
    PE --> TBL[("Table Storage")]
```

---

## 6. Alarm rules

| Rule | Trigger | Severity | Source |
|------|---------|----------|--------|
| `high_temperature` | temp ≥ `TEMPERATURE_ALERT_THRESHOLD` (900) | critical | telemetry |
| `low_temperature` | temp ≤ `TEMPERATURE_MIN_THRESHOLD` (if set) | warning | telemetry |
| `temperature_spike` | \|temp − recent mean\| ≥ `TEMPERATURE_SPIKE_DELTA` (45) | warning | telemetry |
| `stage_error` | status ∈ {error, failed, faulted} | critical | telemetry |
| `repeated_defect` | same defect ≥ `REPEATED_DEFECT_COUNT` (3) in window (30 min) | warning | inspection |
| `low_confidence` | confidence < `CONFIDENCE_ALERT_THRESHOLD` (0.60) | warning | inspection |
| `stale_telemetry` | no reading for > `STALE_TELEMETRY_SECONDS` (120) | warning | watchdog (timer) |
| `prolonged_idle` | status Idle > `IDLE_ALERT_MINUTES` (15) | warning | watchdog (timer) |

The **watchdog** runs on a 1-minute timer, discovers stages via
`IS_OF_MODEL(...ProcessStage;3)`, and debounces repeat alarms
(`ALARM_DEBOUNCE_SECONDS`, default 300) so a standing condition is not re-raised
every tick. The most recent alarm per stage is mirrored onto the twin
(`lastAlertLevel/Message/Time`) for real-time clients.

---

## 7. Storage layout

Table Storage (partitioned by `stageId`):

- `StageReadings` — `temperature`, `status`, `recordedAt`
- `InspectionHistory` — `stationId`, `defect`, `confidence`, `imageUrl`, `recordedAt` (RowKey = inspection id, so redeliveries upsert)
- `ProductionAlerts` — `alarmType`, `severity`, `message`, `details`, `recordedAt`

Blob Storage: private container `inspections`, path
`YYYY/MM/DD/HHMMSS-<uuid>-<name>.jpg`. Images are never public — the dashboard
reads them through the authenticated `/inspection-image` proxy.

---

## 8. Security model

- Ingestion and query endpoints require a **Function key** (`x-functions-key`);
  `/health` and `/ping` are anonymous.
- The Function App authenticates to ADT with a **system-assigned managed
  identity** holding **Azure Digital Twins Data Owner** (data-plane role — not
  granted by subscription Owner/Contributor).
- Table and Blob access use the Functions storage connection string.
- Inspection images are private; the dashboard proxies them with the caller's key.

See **[api.md](api.md)** for the full endpoint reference and
**[../DEPLOY.md](../DEPLOY.md)** for deployment.
