from telemetry_service import TelemetryService
import azure.functions as func
import datetime
import json
import os
import logging

from azure.identity import DefaultAzureCredential
from azure.digitaltwins.core import DigitalTwinsClient

app = func.FunctionApp()

credential = DefaultAzureCredential()




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


@app.route(route="health", auth_level=func.AuthLevel.ANONYMOUS)
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
    route="telemetry",
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

@app.event_grid_trigger(arg_name="event")
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

@app.route(route="ping")
def ping(req: func.HttpRequest):
    logging.info("PING")
    return func.HttpResponse("OK")