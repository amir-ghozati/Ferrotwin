from azure.digitaltwins.core import DigitalTwinsClient
from history_service import HistoryService

class TelemetryService:

    def __init__(self, adt_client: DigitalTwinsClient):
        self.adt_client = adt_client
        self.history = HistoryService()

    def update_stage(
        self,
        stage_id: str,
        temperature: float,
        status: str,
    ):

        patch = [
            {
                "op": "add",
                "path": "/temperature",
                "value": temperature,
            },
            {
                "op": "add",
                "path": "/status",
                "value": status,
            },
        ]

        self.adt_client.update_digital_twin(
            stage_id,
            patch,
        )
        self.history.record_reading(
            stage_id=stage_id,
            temperature=temperature,
            status=status
        )