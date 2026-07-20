# FerroTwin backend operations

## Services now available

- Private inspection images: Azure Blob container `inspections`.
- Persistent Azure Table Storage history: `StageReadings`, `InspectionHistory`, and `ProductionAlerts`.
- Alarm rules for over-temperature, error statuses, and repeated defects.
- Event Grid custom-topic processing.  Set `EVENT_GRID_ENABLED=true` only after creating the subscription below.
- Function-key protection on all data and dashboard endpoints.  Only `/api/health` and `/api/ping` are anonymous.
- Application Insights is configured by the Bicep deployment; structured failures are logged without returning stack traces to callers.

## API contract

All protected endpoints require a Function key (`x-functions-key` header or `?code=` query parameter).

| Method | Endpoint | Purpose |
| --- | --- | --- |
| POST | `/api/telemetry` | Body: `stageId`, `temperature`, `status`; updates the stage and records telemetry. |
| POST | `/api/inspection` | Multipart `image`, optional `stageId` and `stationId`; stores the private image, runs ONNX, records the result and updates twins. |
| GET | `/api/history/telemetry?stageId=stage01&limit=100` | Telemetry history. |
| GET | `/api/history/inspections?stageId=stage01&limit=100` | Inspection history. |
| GET | `/api/alarms?stageId=stage01&limit=100` | Alarm history. |
| GET | `/api/analytics?stageId=stage01` | Average/max temperature, inspection count, defect rate, and defect frequency. |
| GET | `/api/twins` | Snapshot of the Digital Twin graph for the dashboard. |

## Deploy and migrate

1. Copy `local.settings.example.json` to `local.settings.json` for local use. Keep actual secrets outside source control.
2. Deploy `infra/main.bicep`. It creates the private image container, managed identity, ADT and Storage data roles, Event Grid topic, and Application Insights settings.
3. Deploy the Function code, then create the Event Grid subscription. It is intentionally a separate deployment because Event Grid requires the `process_event` Function to exist:

```powershell
az deployment group create --resource-group ferrotwin-rg --template-file infra/modules/eventGridSubscription.bicep --parameters topicName=ferrotwin-events functionAppName=ferrotwin-func
```

4. Upload DTDL models and recreate the graph for model version 3:

```powershell
$env:ADT_HOST = 'https://<your-adt-instance>.api.weu.digitaltwins.azure.net'
.\.venv\Scripts\python.exe scripts\upload_models.py
.\.venv\Scripts\python.exe scripts\create_twins.py --recreate
```

`--recreate` is destructive only to the six FerroTwin twins and their relationships. It is necessary because Azure Digital Twins does not mutate an existing twin to a new DTDL model version.

## Local verification

Start Azurite and the Function host, then run:

```powershell
.\func.exe start --cors http://localhost:8080
.\.venv\Scripts\python.exe -m http.server 8080 --directory dashboard
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -v
.\.venv\Scripts\python.exe scripts\send_telemetry.py
.\.venv\Scripts\python.exe scripts\send_inspection.py
```

For local development, leave `EVENT_GRID_ENABLED=false`; requests are processed synchronously.  The production deployment enables Event Grid and returns `202 Accepted` once an event is queued.

## Dashboard

The dependency-free dashboard is in `dashboard/`. It gives a live factory flow, telemetry chart, inspection history and private image preview, alarm panel, twin explorer, and image upload. Enter the Function URL and Function key in **Connect API**; they are retained only in browser session storage. For a deployed dashboard, set `dashboardAllowedOrigin` to its exact HTTPS origin before deploying the Bicep template.
