import os
from azure.eventgrid import (
    EventGridPublisherClient,
    EventGridEvent,
)
from azure.core.credentials import AzureKeyCredential

TOPIC_ENDPOINT = "https://ferrotwin-events.westeurope-1.eventgrid.azure.net/api/events"
TOPIC_KEY = os.environ["EVENT_GRID_KEY"]

client = EventGridPublisherClient(
    TOPIC_ENDPOINT,
    AzureKeyCredential(TOPIC_KEY),
)

event = EventGridEvent(
    subject="factory/stage1",
    event_type="FerroTwin.Telemetry",
    data_version="1.0",
    data={
        "stageId": "stage1",
        "temperature": 842,
        "status": "Running",
    },
)

client.send([event])

print("Telemetry event published.")