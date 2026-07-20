# FerroTwin — REST API Reference

**Base URL:** `https://<function-app>.azurewebsites.net/api`

**Authentication:** all endpoints except `/health` and `/ping` require a Function
key sent as the `x-functions-key` header (or `?code=<key>` query string).

**Content type:** JSON for all responses. `/inspection` accepts
`multipart/form-data`; `/inspection-image` returns raw image bytes.

Error responses use `{ "status": "error", "message": "..." }` with an appropriate
HTTP status. Stack traces are never returned by the v2 endpoints.

---

## GET /health  · anonymous
Liveness + ADT connectivity.

```json
{ "status": "ok", "adtConnected": true, "factory": "Factory 01",
  "twinId": "factory01", "model": "dtmi:ferrotwin:Factory;2",
  "eventGridEnabled": false }
```
`503` if ADT is unreachable.

## GET /ping · anonymous
`{ "status": "ok", "timestamp": "2026-07-20T10:00:00Z" }`

---

## POST /telemetry · function key
Update a stage twin with a reading; logs history and evaluates alarms.

**Request**
```json
{ "stageId": "stage01", "temperature": 845.0, "status": "Running" }
```

**Response (direct mode)** — `200`
```json
{ "status": "ok", "updatedTwin": "stage01", "alarms": [] }
```

**Response (event-driven mode)** — `202`
```json
{ "status": "queued", "eventId": "…", "updatedTwin": "stage01" }
```
`400` if `stageId`, `temperature`, or `status` is missing/invalid.

---

## POST /inspection · function key
Classify an image, store it, update the stage + inspection twins, log history.

**Request:** `multipart/form-data`
- `image` (file, required, ≤ 10 MB, jpg/png/bmp)
- `stageId` (form field, default `stage01`)
- `stationId` (form field, default `inspection01`)

**Response (direct mode)** — `200`
```json
{ "defect": "crazing", "confidence": 0.9998, "stageId": "stage01",
  "stationId": "inspection01", "inspectionId": "…",
  "imageUrl": "https://…/inspections/…jpg",
  "status": "ok", "recordedAt": "2026-07-20T10:00:00Z", "alarms": [] }
```
Event-driven mode returns the same payload with `status: "queued"` + `eventId` and `202`.
`400` for a missing/empty/oversized image.

---

## GET /history/telemetry · function key
Query: `stageId` (optional), `limit` (1–1000, default 100). Newest first.
```json
{ "items": [ { "PartitionKey": "stage01", "RowKey": "…",
  "temperature": 845.0, "status": "Running", "recordedAt": "…" } ] }
```

## GET /history/inspections · function key
Query: `stageId` (optional), `limit`. Newest first.
```json
{ "items": [ { "PartitionKey": "stage01", "RowKey": "<inspectionId>",
  "stationId": "inspection01", "defect": "crazing", "confidence": 0.9998,
  "imageUrl": "https://…", "recordedAt": "…" } ] }
```

## GET /inspection-image · function key
Query: `blobUrl` (required) — must belong to the `inspections` container.
Returns raw image bytes with the stored content type. `400` if the URL is
outside the container.

---

## GET /alarms · function key
Query: `stageId` (optional), `limit`. Newest first.
```json
{ "items": [ { "PartitionKey": "stage03", "RowKey": "…",
  "alarmType": "high_temperature", "severity": "critical",
  "message": "Temperature 945.2°C exceeds the 900.0°C limit.",
  "details": "{\"temperature\":945.2}", "recordedAt": "…" } ] }
```
`severity` ∈ {`critical`, `warning`}. `alarmType` values: `high_temperature`,
`low_temperature`, `temperature_spike`, `stage_error`, `repeated_defect`,
`low_confidence`, `stale_telemetry`, `prolonged_idle`.

## GET /analytics · function key
Query: `stageId` (optional — omit for factory-wide), `limit` (default 500).
```json
{ "stageId": null, "telemetrySamples": 320, "inspectionCount": 48,
  "averageTemperature": 840.2, "maximumTemperature": 955.1,
  "defectFrequency": { "crazing": 9, "scratches": 7, "patches": 6 },
  "defectRate": 0.15 }
```

## GET /twins · function key
Full twin graph.
```json
{ "items": [ { "$dtId": "stage01",
  "$metadata": { "$model": "dtmi:ferrotwin:ProcessStage;3" },
  "name": "Heating", "status": "Running", "temperature": 845.0,
  "lastDetectedDefect": "", "lastAlertLevel": "" } ] }
```

---

## Internal (not HTTP-invokable)

- **`watchdog`** — timer trigger (every minute). Raises `stale_telemetry` and
  `prolonged_idle` alarms per stage; debounced.
- **`process_event`** — Event Grid trigger. Consumes `FerroTwin.TelemetryReceived`
  and `FerroTwin.InspectionCompleted` events in event-driven mode.

## Legacy (deprecated)

`/legacy/health`, `/legacy/telemetry`, `/legacy/ping`, `/legacy/inspection`
remain from the v1 API for backward compatibility and should not be used by new
clients.
