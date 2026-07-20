import os
import unittest

from alarm_service import AlarmService
from analytics_service import AnalyticsService
from inspection_twin_service import InspectionTwinService
from telemetry_service import TelemetryService


class FakeHistory:
    def __init__(self):
        self.readings = []
        self.inspections = []
        self.alerts = []

    def record_reading(self, stage_id, temperature, status):
        self.readings.append({"PartitionKey": stage_id, "temperature": temperature, "status": status})

    def record_alert(self, stage_id, alarm_type, severity, message, details):
        alert = {
            "PartitionKey": stage_id,
            "alarmType": alarm_type,
            "severity": severity,
            "message": message,
            "details": details,
            "recordedAt": "2026-07-19T00:00:00+00:00",
        }
        self.alerts.append(alert)
        return alert

    def count_recent_defects(self, stage_id, defect, since):
        return sum(1 for item in self.inspections if item["defect"] == defect)

    def list_readings(self, stage_id=None, limit=100):
        return self.readings[:limit]

    def list_inspections(self, stage_id=None, limit=100):
        return self.inspections[:limit]


class FakeTwinClient:
    def __init__(self):
        self.calls = []

    def update_digital_twin(self, twin_id, patch):
        self.calls.append((twin_id, patch))


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.previous_threshold = os.environ.get("TEMPERATURE_ALERT_THRESHOLD")
        os.environ["TEMPERATURE_ALERT_THRESHOLD"] = "900"

    def tearDown(self):
        if self.previous_threshold is None:
            os.environ.pop("TEMPERATURE_ALERT_THRESHOLD", None)
        else:
            os.environ["TEMPERATURE_ALERT_THRESHOLD"] = self.previous_threshold

    def test_telemetry_records_and_surfaces_temperature_alarm(self):
        history = FakeHistory()
        client = FakeTwinClient()
        alerts = TelemetryService(client, history).update_stage("stage01", 901, "Running")

        self.assertEqual(len(history.readings), 1)
        self.assertEqual(alerts[0]["alarmType"], "high_temperature")
        self.assertEqual(client.calls[0][0], "stage01")
        self.assertEqual(client.calls[1][0], "stage01")
        self.assertEqual(client.calls[1][1][0]["path"], "/lastAlertLevel")

    def test_repeated_defect_creates_alert(self):
        history = FakeHistory()
        history.inspections = [{"defect": "scratches"}] * 3
        alarms = AlarmService(history).evaluate_inspection("stage01", "scratches", 0.99)

        self.assertEqual(alarms[0]["alarmType"], "repeated_defect")
        self.assertEqual(alarms[0]["severity"], "warning")

    def test_analytics_returns_temperature_and_defect_kpis(self):
        history = FakeHistory()
        history.readings = [{"temperature": 800}, {"temperature": 900}]
        history.inspections = [{"defect": "scratches"}, {"defect": "scratches"}, {"defect": "patches"}]

        summary = AnalyticsService(history).summary("stage01")
        self.assertEqual(summary["averageTemperature"], 850.0)
        self.assertEqual(summary["maximumTemperature"], 900.0)
        self.assertEqual(summary["defectFrequency"], {"scratches": 2, "patches": 1})

    def test_low_confidence_inspection_raises_warning(self):
        history = FakeHistory()  # no prior inspections -> no repeated_defect
        alarms = AlarmService(history).evaluate_inspection("stage01", "crazing", 0.42)
        types = [a["alarmType"] for a in alarms]
        self.assertIn("low_confidence", types)
        self.assertNotIn("repeated_defect", types)

    def test_high_confidence_inspection_is_quiet(self):
        history = FakeHistory()
        alarms = AlarmService(history).evaluate_inspection("stage01", "crazing", 0.98)
        self.assertEqual(alarms, [])

    def test_temperature_spike_raises_warning(self):
        history = FakeHistory()
        # newest row first; prior baseline ~500, current param 700 -> delta 200 >= 45
        history.readings = [
            {"temperature": 700}, {"temperature": 500}, {"temperature": 500}, {"temperature": 500},
        ]
        alarms = AlarmService(history).evaluate_telemetry("stage01", 700, "Running")
        types = [a["alarmType"] for a in alarms]
        self.assertIn("temperature_spike", types)
        self.assertNotIn("high_temperature", types)  # 700 < 900

    def test_inspection_updates_stage_and_station_twins(self):
        client = FakeTwinClient()
        InspectionTwinService(client).update_defect(
            twin_id="stage01",
            defect="crazing",
            confidence=0.99,
            image_url="https://example.test/inspection.jpg",
            inspection_id="inspection-id",
            station_id="inspection01",
            inspected_at="2026-07-19T00:00:00+00:00",
        )

        self.assertEqual([call[0] for call in client.calls], ["stage01", "inspection01"])
        self.assertEqual(client.calls[1][1][-1]["path"], "/lastInspectionTime")


if __name__ == "__main__":
    unittest.main()
