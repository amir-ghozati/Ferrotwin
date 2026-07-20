"""Azure Table Storage history for telemetry, inspections, and alarms."""

import json
import os
import uuid
from datetime import datetime, timezone

from azure.data.tables import TableServiceClient

from azure_clients import get_credential, get_storage_connection_string


class HistoryService:
    TABLES = {
        "readings": "StageReadings",
        "inspections": "InspectionHistory",
        "alerts": "ProductionAlerts",
    }

    def __init__(self) -> None:
        connection_string = get_storage_connection_string()
        if connection_string:
            self.service = TableServiceClient.from_connection_string(connection_string)
        else:
            account_name = os.environ["STORAGE_ACCOUNT_NAME"]
            self.service = TableServiceClient(
                endpoint=f"https://{account_name}.table.core.windows.net",
                credential=get_credential(),
            )
        self.tables = {
            name: self.service.create_table_if_not_exists(table_name=table_name)
            for name, table_name in self.TABLES.items()
        }

    @staticmethod
    def _entity_key(timestamp: datetime) -> str:
        return f"{timestamp.isoformat()}_{uuid.uuid4().hex}"

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    def record_reading(self, stage_id: str, temperature: float, status: str) -> dict:
        now = self._now()
        entity = {
            "PartitionKey": stage_id,
            "RowKey": self._entity_key(now),
            "temperature": temperature,
            "status": status,
            "recordedAt": now.isoformat(),
        }
        self.tables["readings"].create_entity(entity)
        return entity

    def record_inspection(
        self, stage_id: str, station_id: str, defect: str, confidence: float,
        image_url: str, inspection_id: str | None = None,
    ) -> dict:
        now = self._now()
        entity = {
            "PartitionKey": stage_id,
            "RowKey": inspection_id or self._entity_key(now),
            "stationId": station_id,
            "defect": defect,
            "confidence": confidence,
            "imageUrl": image_url,
            "recordedAt": now.isoformat(),
        }
        # The inspection id is also the Event Grid idempotency key. A redelivery
        # updates the same entity rather than creating a duplicate inspection.
        self.tables["inspections"].upsert_entity(entity)
        return entity

    def record_alert(self, stage_id: str, alarm_type: str, severity: str, message: str, details: dict) -> dict:
        now = self._now()
        entity = {
            "PartitionKey": stage_id,
            "RowKey": self._entity_key(now),
            "alarmType": alarm_type,
            "severity": severity,
            "message": message,
            "details": json.dumps(details, separators=(",", ":")),
            "recordedAt": now.isoformat(),
        }
        self.tables["alerts"].create_entity(entity)
        return entity

    def _list(self, table_key: str, stage_id: str | None, limit: int) -> list[dict]:
        filter_query = f"PartitionKey eq '{stage_id}'" if stage_id else None
        rows = list(self.tables[table_key].query_entities(query_filter=filter_query))
        rows.sort(key=lambda item: item.get("recordedAt", ""), reverse=True)
        return [dict(row) for row in rows[:max(1, min(limit, 1000))]]

    def list_readings(self, stage_id: str | None = None, limit: int = 100) -> list[dict]:
        return self._list("readings", stage_id, limit)

    def list_inspections(self, stage_id: str | None = None, limit: int = 100) -> list[dict]:
        return self._list("inspections", stage_id, limit)

    def list_alerts(self, stage_id: str | None = None, limit: int = 100) -> list[dict]:
        return self._list("alerts", stage_id, limit)

    def count_recent_defects(self, stage_id: str, defect: str, since: datetime) -> int:
        return sum(
            1 for item in self.list_inspections(stage_id, 1000)
            if item.get("defect") == defect and item.get("recordedAt", "") >= since.isoformat()
        )
