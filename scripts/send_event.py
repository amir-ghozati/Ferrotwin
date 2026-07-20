import os

from azure.eventgrid import (
    EventGridPublisherClient,
    EventGridEvent,
)
from azure.core.credentials import AzureKeyCredential

TOPIC_ENDPOINT = os.environ["EVENT_GRID_TOPIC_ENDPOINT"]
TOPIC_KEY = os.environ["EVENT_GRID_TOPIC_KEY"]

client = EventGridPublisherClient(
    TOPIC_ENDPOINT,
    AzureKeyCredential(TOPIC_KEY),
)

event = EventGridEvent(
    subject="factory/stage01",
    event_type="FerroTwin.Telemetry",
    data_version="1.0",
    data={
        "stageId": "stage01",
        "temperature": 842,
        "status": "Running",
    },
)

client.send([event])

print("Telemetry event published.")
