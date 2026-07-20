from azure.digitaltwins.core import DigitalTwinsClient
from history_service import HistoryService
from alarm_service import AlarmService

class TelemetryService:

    def __init__(self, adt_client: DigitalTwinsClient, history: HistoryService | None = None):
        self.adt_client = adt_client
        self.history = history or HistoryService()
        self.alarms = AlarmService(self.history)

    def update_stage(
        self,
        stage_id: str,
        temperature: float,
        status: str,
    ):

        patch = [
            {
                "op": "replace",
                "path": "/temperature",
                "value": temperature,
            },
            {
                "op": "replace",
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
        alerts = self.alarms.evaluate_telemetry(stage_id, temperature, status)
        self.alarms.update_stage_twin(self.adt_client, stage_id, alerts)
        return alerts
