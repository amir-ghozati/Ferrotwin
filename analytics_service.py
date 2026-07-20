"""Small, query-friendly production KPI aggregation service."""

from collections import Counter

from history_service import HistoryService


class AnalyticsService:
    def __init__(self, history: HistoryService | None = None) -> None:
        self.history = history or HistoryService()

    def summary(self, stage_id: str | None = None, limit: int = 500) -> dict:
        readings = self.history.list_readings(stage_id, limit)
        inspections = self.history.list_inspections(stage_id, limit)
        temperatures = [float(item["temperature"]) for item in readings if item.get("temperature") is not None]
        defects = Counter(item.get("defect") for item in inspections if item.get("defect"))
        return {
            "stageId": stage_id,
            "telemetrySamples": len(readings),
            "inspectionCount": len(inspections),
            "averageTemperature": round(sum(temperatures) / len(temperatures), 2) if temperatures else None,
            "maximumTemperature": max(temperatures) if temperatures else None,
            "defectFrequency": dict(defects),
            "defectRate": round(len(inspections) / len(readings), 4) if readings else None,
        }
