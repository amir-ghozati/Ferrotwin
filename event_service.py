"""Publishing support for Event Grid with a direct-processing fallback."""

import os
import uuid

from azure.core.credentials import AzureKeyCredential
from azure.eventgrid import EventGridEvent, EventGridPublisherClient


def event_grid_enabled() -> bool:
    return os.getenv("EVENT_GRID_ENABLED", "false").lower() == "true"


def publish_event(event_type: str, subject: str, data: dict) -> str | None:
    """Publish to the configured custom topic and return the generated event id."""
    endpoint = os.getenv("EVENT_GRID_TOPIC_ENDPOINT")
    key = os.getenv("EVENT_GRID_TOPIC_KEY")
    if not event_grid_enabled() or not endpoint or not key:
        return None
    event_id = str(uuid.uuid4())
    event = EventGridEvent(
        subject=subject,
        event_type=event_type,
        data_version="1.0",
        data=data,
        id=event_id,
    )
    EventGridPublisherClient(endpoint, AzureKeyCredential(key)).send([event])
    return event_id
