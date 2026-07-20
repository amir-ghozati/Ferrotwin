import argparse
import os

from azure.core.exceptions import ResourceNotFoundError
from azure.identity import DefaultAzureCredential
from azure.digitaltwins.core import DigitalTwinsClient

ADT_HOST = os.environ["ADT_HOST"]

credential = DefaultAzureCredential(exclude_interactive_browser_credential=True)
client = DigitalTwinsClient(ADT_HOST, credential)

parser = argparse.ArgumentParser(description="Create the FerroTwin graph.")
parser.add_argument(
    "--recreate",
    action="store_true",
    help="Delete the existing graph first; required after a DTDL model-version upgrade.",
)
args = parser.parse_args()

twins = [
    (
        "factory01",
        {
            "$metadata": {
                "$model": "dtmi:ferrotwin:Factory;3"
            },
            "name": "Factory 01"
        }
    ),

    (
        "line01",
        {
            "$metadata": {
                "$model": "dtmi:ferrotwin:ProductionLine;3"
            },
            "name": "Line 01"
        }
    ),

    (
        "stage01",
        {
            "$metadata": {
                "$model": "dtmi:ferrotwin:ProcessStage;3"
            },
            "name": "Heating",
            "status": "Idle",
            "temperature": 25.0,
            "lastDetectedDefect": "",
            "lastDefectConfidence": 0.0,
            "lastAlertLevel": "",
            "lastAlertMessage": "",
            "lastAlertTime": ""
        }
    ),

    (
        "stage02",
        {
            "$metadata": {
                "$model": "dtmi:ferrotwin:ProcessStage;3"
            },
            "name": "Rolling",
            "status": "Idle",
            "temperature": 25.0,
            "lastDetectedDefect": "",
            "lastDefectConfidence": 0.0,
            "lastAlertLevel": "",
            "lastAlertMessage": "",
            "lastAlertTime": ""
        }
    ),

    (
        "stage03",
        {
            "$metadata": {
                "$model": "dtmi:ferrotwin:ProcessStage;3"
            },
            "name": "Cooling",
            "status": "Idle",
            "temperature": 25.0,
            "lastDetectedDefect": "",
            "lastDefectConfidence": 0.0,
            "lastAlertLevel": "",
            "lastAlertMessage": "",
            "lastAlertTime": ""
        }
    ),

    (
        "inspection01",
        {
            "$metadata": {
                "$model": "dtmi:ferrotwin:InspectionStation;3"
            },
            "name": "Vision Station",
            "cameraId": "CAM-01",
            "lastDefect": "",
            "confidence": 0.0,
            "lastInspectionTime": "",
            "lastImageUrl": "",
            "lastInspectionId": ""
        }
    ),
]

relationships = [

    (
        "factory01",
        "contains-line",
        {
            "$relationshipId": "contains-line",
            "$sourceId": "factory01",
            "$relationshipName": "contains",
            "$targetId": "line01"
        }
    ),

    (
        "line01",
        "contains-stage01",
        {
            "$relationshipId": "contains-stage01",
            "$sourceId": "line01",
            "$relationshipName": "contains",
            "$targetId": "stage01"
        }
    ),

    (
        "line01",
        "contains-stage02",
        {
            "$relationshipId": "contains-stage02",
            "$sourceId": "line01",
            "$relationshipName": "contains",
            "$targetId": "stage02"
        }
    ),

    (
        "line01",
        "contains-stage03",
        {
            "$relationshipId": "contains-stage03",
            "$sourceId": "line01",
            "$relationshipName": "contains",
            "$targetId": "stage03"
        }
    ),

    (
        "stage01",
        "feeds-stage02",
        {
            "$relationshipId": "feeds-stage02",
            "$sourceId": "stage01",
            "$relationshipName": "feedsInto",
            "$targetId": "stage02"
        }
    ),

    (
        "stage02",
        "feeds-stage03",
        {
            "$relationshipId": "feeds-stage03",
            "$sourceId": "stage02",
            "$relationshipName": "feedsInto",
            "$targetId": "stage03"
        }
    ),

    (
        "stage03",
        "contains-inspection",
        {
            "$relationshipId": "contains-inspection",
            "$sourceId": "stage03",
            "$relationshipName": "contains",
            "$targetId": "inspection01"
        }
    ),
]
if args.recreate:
    for twin_id in (
        "factory01",
        "line01",
        "stage01",
        "stage02",
        "stage03",
    ):
        try:
            for rel in client.list_relationships(twin_id):
                client.delete_relationship(
                    twin_id,
                    rel["$relationshipId"],
                )
        except Exception:
            pass
    for twin_id in ("inspection01", "stage03", "stage02", "stage01", "line01", "factory01"):
        try:
            client.delete_digital_twin(twin_id)
        except ResourceNotFoundError:
            pass
    print("Existing graph deleted.")


for twin_id, body in twins:
    client.upsert_digital_twin(twin_id, body)
    print("Created:", twin_id)

for source, rel_id, rel in relationships:
    client.upsert_relationship(
        source,
        rel_id,
        rel
    )
    print("Relationship:", rel_id)

print("\nDone.")
