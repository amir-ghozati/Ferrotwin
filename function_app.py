from telemetry_service import TelemetryService
import azure.functions as func
import datetime
import json
import os
import logging
import uuid
import tempfile
from inspection_twin_service import InspectionTwinService
from inspection_service import inspect
from azure.identity import AzureCliCredential
from azure.digitaltwins.core import DigitalTwinsClient
from alarm_service import AlarmService
from analytics_service import AnalyticsService
from azure_clients import get_credential
from event_service import event_grid_enabled, publish_event
from history_service import HistoryService
from storage_service import InspectionImageStorage

app = func.FunctionApp()

credential = AzureCliCredential()




""" @app.blob_trigger(arg_name="myblob", path="blobname",
                               connection="Authorization:") 
def BlobTrigger(myblob: func.InputStream):
    logging.info(f"Python blob trigger function processed blob"
                f"Name: {myblob.name}"
                f"Blob Size: {myblob.length} bytes")
 """

# This example uses SDK types to directly access the underlying BlobClient object provided by the Blob storage trigger.
# To use, uncomment the section below and add azurefunctions-extensions-bindings-blob to your requirements.txt file
# Ref: aka.ms/functions-sdk-blob-python
#
# import azurefunctions.extensions.bindings.blob as blob
# @app.blob_trigger(arg_name="client", path="blobname",
#                   connection="Authorization:")
# def BlobTrigger(client: blob.BlobClient):
#     logging.info(
#         f"Python blob trigger function processed blob \n"
#         f"Properties: {client.get_blob_properties()}\n"
#         f"Blob content head: {client.download_blob().read(size=1)}"
#     )


@app.route(route="legacy/health", auth_level=func.AuthLevel.ANONYMOUS)
def health(req: func.HttpRequest) -> func.HttpResponse:
    try:

        adt_client = DigitalTwinsClient(
            os.environ["ADT_HOST"],
            credential,
        )

        twin = adt_client.get_digital_twin("factory01")
    
        response = {
            "status": "ok",
            "adtConnected": True,
            "factory": twin["name"],
            "twinId": twin["$dtId"],
            "model": twin["$metadata"]["$model"],
        }
        return func.HttpResponse(
            body=json.dumps(response),
            mimetype="application/json",
            status_code=200,
        )

    except Exception as ex:
        logging.exception(ex)

        return func.HttpResponse(
            body=json.dumps(
                {
                    "status": "error",
                    "message": str(ex),
                }
            ),
            mimetype="application/json",
            status_code=500,
    )

@app.route(
    route="legacy/telemetry",
    methods=["POST"],
    auth_level=func.AuthLevel.FUNCTION,
)
def telemetry(req: func.HttpRequest) -> func.HttpResponse:
    try:
        data = req.get_json()

        adt_client = DigitalTwinsClient(
            os.environ["ADT_HOST"],
            credential,
        )

        service = TelemetryService(adt_client)

        service.update_stage(
            stage_id=data["stageId"],
            temperature=float(data["temperature"]),
            status=data["status"],
        )

        return func.HttpResponse(
            body=json.dumps(
                {
                    "status": "ok",
                    "updatedTwin": data["stageId"],
                }
            ),
            mimetype="application/json",
            status_code=200,
        )

    except Exception as ex:
        import traceback

        return func.HttpResponse(
            body=json.dumps(
                {
                    "status": "error",
                    "message": str(ex),
                    "trace": traceback.format_exc(),
                }
            ),

            mimetype="application/json",
            status_code=500,
        )

# Retained temporarily only as a migration reference; v2 processing is registered below.
# @app.event_grid_trigger(arg_name="event")
def telemetry_event(event: func.EventGridEvent):

    with open("/tmp/event.txt", "w") as f:
        f.write("CALLED")
    logging.info("========== EVENT GRID RECEIVED ==========")
    logging.info(event.get_json())
    try:

        data = event.get_json()

        adt_client = DigitalTwinsClient(
            os.environ["ADT_HOST"],
            credential,
        )

        service = TelemetryService(adt_client)

        service.update_stage(
            stage_id=data["stageId"],
            temperature=float(data["temperature"]),
            status=data["status"],
        )

        logging.info(f"Updated twin {data['stageId']} from Event Grid.")

    except Exception:
        logging.exception("Event processing failed.")

@app.route(route="legacy/ping")
def ping(req: func.HttpRequest):
    logging.info("PING")
    return func.HttpResponse("OK")

@app.route(route="legacy/inspection", methods=["POST"])
def inspection(req: func.HttpRequest) -> func.HttpResponse:
    try:

        image = req.files["image"]

        suffix = os.path.splitext(image.filename)[1]

        temp_path = os.path.join(
            tempfile.gettempdir(),
            f"{uuid.uuid4()}{suffix}"
        )

        with open(temp_path, "wb") as f:
            f.write(image.stream.read())

        result = inspect(temp_path)
        adt_client = DigitalTwinsClient(
            os.environ["ADT_HOST"],
            credential,
        )

        patch = [
            {
                "op": "replace",
                "path": "/lastDefect",
                "value": result["defect"],
            },
            {
                "op": "replace",
                "path": "/confidence",
                "value": result["confidence"],
            },
            {    
                "op": "replace",
                "path": "/lastInspectionTime",
                "value": datetime.datetime.utcnow().isoformat(),
            },
        ]

        adt_client.update_digital_twin(
            "inspection01",
            patch,
        )

        service = InspectionTwinService(adt_client)

        service.update_defect(
            twin_id="stage01",
            defect=result["defect"],
            confidence=result["confidence"],
        )
        os.remove(temp_path)

        return func.HttpResponse(
            json.dumps(result),
            mimetype="application/json",
            status_code=200,
        )

    except Exception as ex:

        return func.HttpResponse(
            str(ex),
            status_code=500,
        )


# Version 2 API.  The legacy handlers above remain available under /api/legacy
# during the migration, so existing deployed clients fail safely rather than
# silently changing behavior.
def _json_response(payload, status_code=200):
    return func.HttpResponse(
        json.dumps(payload, default=str),
        mimetype="application/json",
        status_code=status_code,
    )


def _error(message, status_code=400):
    return _json_response({"status": "error", "message": message}, status_code)


def _adt_client():
    return DigitalTwinsClient(os.environ["ADT_HOST"], get_credential())


def _limit(req, default=100):
    try:
        return max(1, min(int(req.params.get("limit", default)), 1000))
    except ValueError:
        return default


def process_telemetry(data):
    return TelemetryService(_adt_client()).update_stage(
        stage_id=data["stageId"],
        temperature=float(data["temperature"]),
        status=data["status"],
    )


def process_inspection(data):
    history = HistoryService()
    record = history.record_inspection(
        stage_id=data["stageId"],
        station_id=data["stationId"],
        defect=data["defect"],
        confidence=float(data["confidence"]),
        image_url=data["imageUrl"],
        inspection_id=data["inspectionId"],
    )
    InspectionTwinService(_adt_client()).update_defect(
        twin_id=data["stageId"],
        defect=data["defect"],
        confidence=float(data["confidence"]),
        image_url=data["imageUrl"],
        inspection_id=data["inspectionId"],
        station_id=data["stationId"],
        inspected_at=record["recordedAt"],
    )
    alarms = AlarmService(history).evaluate_inspection(
        data["stageId"], data["defect"], float(data["confidence"]),
    )
    AlarmService.update_stage_twin(_adt_client(), data["stageId"], alarms)
    return record, alarms


@app.route(route="health", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def health_v2(req: func.HttpRequest) -> func.HttpResponse:
    try:
        twin = _adt_client().get_digital_twin("factory01")
        return _json_response({
            "status": "ok",
            "adtConnected": True,
            "factory": twin.get("name"),
            "twinId": twin.get("$dtId"),
            "model": twin.get("$metadata", {}).get("$model"),
            "eventGridEnabled": event_grid_enabled(),
        })
    except Exception:
        logging.exception("Health check failed")
        return _error("Azure Digital Twins is unavailable.", 503)


@app.route(route="telemetry", methods=["POST"], auth_level=func.AuthLevel.FUNCTION)
def telemetry_v2(req: func.HttpRequest) -> func.HttpResponse:
    try:
        data = req.get_json()
        if not all(key in data for key in ("stageId", "temperature", "status")):
            return _error("stageId, temperature, and status are required.")
        data["temperature"] = float(data["temperature"])
        if event_grid_enabled():
            event_id = publish_event("FerroTwin.TelemetryReceived", f"stages/{data['stageId']}", data)
            return _json_response({"status": "queued", "eventId": event_id, "updatedTwin": data["stageId"]}, 202)
        alarms = process_telemetry(data)
        return _json_response({"status": "ok", "updatedTwin": data["stageId"], "alarms": alarms})
    except (ValueError, KeyError, TypeError) as ex:
        return _error(str(ex))
    except Exception:
        logging.exception("Telemetry ingestion failed")
        return _error("Unable to process telemetry.", 500)


@app.route(route="inspection", methods=["POST"], auth_level=func.AuthLevel.FUNCTION)
def inspection_v2(req: func.HttpRequest) -> func.HttpResponse:
    temp_path = None
    try:
        image = req.files.get("image")
        if image is None or not image.filename:
            return _error("A multipart image field is required.")
        image_bytes = image.stream.read()
        if not image_bytes:
            return _error("The uploaded image is empty.")
        if len(image_bytes) > 10 * 1024 * 1024:
            return _error("The uploaded image must not exceed 10 MB.")

        suffix = os.path.splitext(image.filename)[1] or ".jpg"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            temp_file.write(image_bytes)
            temp_path = temp_file.name
        result = inspect(temp_path)
        stage_id = req.form.get("stageId") or req.params.get("stageId") or "stage01"
        station_id = req.form.get("stationId") or req.params.get("stationId") or "inspection01"
        payload = {
            **result,
            "stageId": stage_id,
            "stationId": station_id,
            "inspectionId": str(uuid.uuid4()),
            "imageUrl": InspectionImageStorage().upload(image_bytes, image.filename, image.content_type),
        }
        if event_grid_enabled():
            event_id = publish_event("FerroTwin.InspectionCompleted", f"stages/{stage_id}/inspections/{station_id}", payload)
            return _json_response({**payload, "status": "queued", "eventId": event_id}, 202)
        record, alarms = process_inspection(payload)
        return _json_response({**payload, "status": "ok", "recordedAt": record["recordedAt"], "alarms": alarms})
    except Exception:
        logging.exception("Inspection ingestion failed")
        return _error("Unable to process inspection.", 500)
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)


@app.event_grid_trigger(arg_name="event")
def process_event(event: func.EventGridEvent) -> None:
    data = event.get_json()
    logging.info("Processing Event Grid event %s (%s)", event.id, event.event_type)
    if event.event_type in {"FerroTwin.Telemetry", "FerroTwin.TelemetryReceived"}:
        process_telemetry(data)
    elif event.event_type == "FerroTwin.InspectionCompleted":
        process_inspection(data)
    else:
        logging.warning("Ignoring unsupported Event Grid event type: %s", event.event_type)


@app.timer_trigger(arg_name="timer", schedule="0 */1 * * * *", run_on_startup=False, use_monitor=True)
def watchdog(timer: func.TimerRequest) -> None:
    """Every minute, check each stage for stale telemetry and prolonged idle."""
    try:
        client = _adt_client()
        rows = client.query_twins(
            "SELECT * FROM DIGITALTWINS T WHERE IS_OF_MODEL(T, 'dtmi:ferrotwin:ProcessStage;3')"
        )
        stage_ids = [r["$dtId"] for r in rows if r.get("$dtId")]
        raised = AlarmService().evaluate_watchdog(client, stage_ids)
        if raised:
            logging.info("Watchdog raised %d alarm(s): %s", len(raised), [a["alarmType"] for a in raised])
    except Exception:
        logging.exception("Watchdog evaluation failed")


@app.route(route="history/telemetry", methods=["GET"], auth_level=func.AuthLevel.FUNCTION)
def telemetry_history(req: func.HttpRequest) -> func.HttpResponse:
    try:
        return _json_response({"items": HistoryService().list_readings(req.params.get("stageId"), _limit(req))})
    except Exception:
        logging.exception("Unable to read telemetry history")
        return _error("Unable to read telemetry history.", 500)


@app.route(route="history/inspections", methods=["GET"], auth_level=func.AuthLevel.FUNCTION)
def inspection_history(req: func.HttpRequest) -> func.HttpResponse:
    try:
        return _json_response({"items": HistoryService().list_inspections(req.params.get("stageId"), _limit(req))})
    except Exception:
        logging.exception("Unable to read inspection history")
        return _error("Unable to read inspection history.", 500)


@app.route(route="inspection-image", methods=["GET"], auth_level=func.AuthLevel.FUNCTION)
def inspection_image(req: func.HttpRequest) -> func.HttpResponse:
    try:
        blob_url = req.params.get("blobUrl")
        if not blob_url:
            return _error("blobUrl is required.")
        image_bytes, content_type = InspectionImageStorage().download(blob_url)
        return func.HttpResponse(image_bytes, mimetype=content_type, status_code=200)
    except ValueError as ex:
        return _error(str(ex))
    except Exception:
        logging.exception("Unable to read inspection image")
        return _error("Unable to read inspection image.", 500)


@app.route(route="alarms", methods=["GET"], auth_level=func.AuthLevel.FUNCTION)
def alarms(req: func.HttpRequest) -> func.HttpResponse:
    try:
        return _json_response({"items": HistoryService().list_alerts(req.params.get("stageId"), _limit(req))})
    except Exception:
        logging.exception("Unable to read alarms")
        return _error("Unable to read alarms.", 500)


@app.route(route="analytics", methods=["GET"], auth_level=func.AuthLevel.FUNCTION)
def analytics(req: func.HttpRequest) -> func.HttpResponse:
    try:
        return _json_response(AnalyticsService().summary(req.params.get("stageId"), _limit(req, 500)))
    except Exception:
        logging.exception("Unable to calculate analytics")
        return _error("Unable to calculate analytics.", 500)


@app.route(route="twins", methods=["GET"], auth_level=func.AuthLevel.FUNCTION)
def twins(req: func.HttpRequest) -> func.HttpResponse:
    try:
        all_twins = list(_adt_client().query_twins("SELECT * FROM DIGITALTWINS"))

        allowed = {
            "factory01",
            "line01",
            "stage01",
            "stage02",
            "stage03",
            "inspection01",
        }

        items = [t for t in all_twins if t.get("$dtId") in allowed]

        return _json_response({"items": items})

    except Exception:
        logging.exception("Unable to query twins")
        return _error("Unable to query digital twins.", 500)
@app.route(route="ping", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def ping_v2(req: func.HttpRequest) -> func.HttpResponse:
    return _json_response({"status": "ok", "timestamp": datetime.datetime.now(datetime.UTC).isoformat()})
