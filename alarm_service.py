"""Rule-based alarms generated from telemetry and inspection events.

Rules
-----
Telemetry (evaluated on each reading):
  * high_temperature   — temperature >= TEMPERATURE_ALERT_THRESHOLD          (critical)
  * low_temperature    — temperature <= TEMPERATURE_MIN_THRESHOLD (if set)   (warning)
  * temperature_spike  — |temp - recent mean| >= TEMPERATURE_SPIKE_DELTA      (warning)
  * stage_error        — status in {error, failed, faulted}                  (critical)

Inspection (evaluated on each inspection):
  * repeated_defect    — same defect >= REPEATED_DEFECT_COUNT in window       (warning)
  * low_confidence     — confidence < CONFIDENCE_ALERT_THRESHOLD             (warning)

Watchdog (evaluated by the timer-triggered function, per stage):
  * stale_telemetry    — no reading for > STALE_TELEMETRY_SECONDS             (warning)
  * prolonged_idle     — status Idle for > IDLE_ALERT_MINUTES                 (warning)

Watchdog alarms are debounced (ALARM_DEBOUNCE_SECONDS) so the timer does not
re-raise the same condition every tick.
"""

import os
from datetime import datetime, timedelta, timezone

from history_service import HistoryService

ERROR_STATUSES = {"error", "failed", "faulted", "fault"}


def _f(name: str, default: str) -> float:
    return float(os.getenv(name, default))


class AlarmService:
    def __init__(self, history: HistoryService | None = None) -> None:
        self.history = history or HistoryService()
        # temperature
        self.temperature_threshold = _f("TEMPERATURE_ALERT_THRESHOLD", "900")
        raw_min = os.getenv("TEMPERATURE_MIN_THRESHOLD", "").strip()
        self.temperature_min = float(raw_min) if raw_min else None
        self.spike_delta = _f("TEMPERATURE_SPIKE_DELTA", "45")
        self.spike_min_samples = int(os.getenv("TEMPERATURE_SPIKE_MIN_SAMPLES", "3"))
        # inspection
        self.repeat_window_minutes = int(os.getenv("REPEATED_DEFECT_WINDOW_MINUTES", "30"))
        self.repeat_defect_count = int(os.getenv("REPEATED_DEFECT_COUNT", "3"))
        self.confidence_threshold = _f("CONFIDENCE_ALERT_THRESHOLD", "0.60")
        # watchdog
        self.stale_seconds = _f("STALE_TELEMETRY_SECONDS", "120")
        self.idle_minutes = _f("IDLE_ALERT_MINUTES", "15")
        self.debounce_seconds = _f("ALARM_DEBOUNCE_SECONDS", "300")

    # ---------------- telemetry ----------------
    def evaluate_telemetry(self, stage_id: str, temperature: float, status: str) -> list[dict]:
        alerts = []
        if temperature >= self.temperature_threshold:
            alerts.append(self._record(
                stage_id, "high_temperature", "critical",
                f"Temperature {temperature:.1f}°C exceeds the {self.temperature_threshold:.1f}°C limit.",
                {"temperature": temperature, "status": status},
            ))
        if self.temperature_min is not None and temperature <= self.temperature_min:
            alerts.append(self._record(
                stage_id, "low_temperature", "warning",
                f"Temperature {temperature:.1f}°C is at or below the {self.temperature_min:.1f}°C floor.",
                {"temperature": temperature, "status": status},
            ))
        spike = self._temperature_spike(stage_id, temperature)
        if spike is not None:
            mean, delta = spike
            alerts.append(self._record(
                stage_id, "temperature_spike", "warning",
                f"Temperature {temperature:.1f}°C deviates {delta:.1f}°C from the recent mean ({mean:.1f}°C).",
                {"temperature": temperature, "recentMean": round(mean, 1), "delta": round(delta, 1)},
            ))
        if status.lower() in ERROR_STATUSES:
            alerts.append(self._record(
                stage_id, "stage_error", "critical",
                f"Stage status is {status}.", {"status": status},
            ))
        return alerts

    def _temperature_spike(self, stage_id: str, temperature: float):
        """Return (recent_mean, delta) if the current reading is an outlier, else None.

        Assumes the current reading is already the newest row in history (the
        telemetry service records before evaluating), so prior readings are [1:].
        """
        rows = self.history.list_readings(stage_id, self.spike_min_samples + 1)
        prior = []
        for r in rows[1:]:
            try:
                prior.append(float(r["temperature"]))
            except (KeyError, TypeError, ValueError):
                continue
        if len(prior) < self.spike_min_samples:
            return None
        mean = sum(prior) / len(prior)
        delta = abs(temperature - mean)
        return (mean, delta) if delta >= self.spike_delta else None

    # ---------------- inspection ----------------
    def evaluate_inspection(self, stage_id: str, defect: str, confidence: float) -> list[dict]:
        alerts = []
        since = datetime.now(timezone.utc) - timedelta(minutes=self.repeat_window_minutes)
        count = self.history.count_recent_defects(stage_id, defect, since)
        if count >= self.repeat_defect_count:
            alerts.append(self._record(
                stage_id, "repeated_defect", "warning",
                f"{count} {defect} detections in the last {self.repeat_window_minutes} minutes.",
                {"defect": defect, "confidence": confidence, "count": count},
            ))
        if confidence < self.confidence_threshold:
            alerts.append(self._record(
                stage_id, "low_confidence", "warning",
                f"Inspection confidence {confidence * 100:.0f}% is below the "
                f"{self.confidence_threshold * 100:.0f}% review threshold — manual review advised.",
                {"defect": defect, "confidence": confidence},
            ))
        return alerts

    # ---------------- watchdog (timer) ----------------
    def evaluate_watchdog(self, adt_client, stage_ids: list[str]) -> list[dict]:
        raised = []
        now = datetime.now(timezone.utc)
        for stage_id in stage_ids:
            rows = self.history.list_readings(stage_id, 60)
            if not rows:
                continue
            last = rows[0]
            last_ts = self._parse(last.get("recordedAt"))
            if last_ts is None:
                continue

            age = (now - last_ts).total_seconds()
            if age > self.stale_seconds and not self._debounced(stage_id, "stale_telemetry"):
                alert = self._record(
                    stage_id, "stale_telemetry", "warning",
                    f"No telemetry from {stage_id} for {int(age)}s (limit {int(self.stale_seconds)}s).",
                    {"ageSeconds": int(age)},
                )
                self.update_stage_twin(adt_client, stage_id, [alert])
                raised.append(alert)

            if str(last.get("status", "")).lower() == "idle":
                active = next((r for r in rows if str(r.get("status", "")).lower() != "idle"), None)
                idle_since = self._parse(active.get("recordedAt")) if active else self._parse(rows[-1].get("recordedAt"))
                if idle_since is not None:
                    idle_secs = (now - idle_since).total_seconds()
                    if idle_secs > self.idle_minutes * 60 and not self._debounced(stage_id, "prolonged_idle"):
                        alert = self._record(
                            stage_id, "prolonged_idle", "warning",
                            f"{stage_id} has been idle for {int(idle_secs // 60)} min "
                            f"(limit {int(self.idle_minutes)} min).",
                            {"idleSeconds": int(idle_secs)},
                        )
                        self.update_stage_twin(adt_client, stage_id, [alert])
                        raised.append(alert)
        return raised

    def _debounced(self, stage_id: str, alarm_type: str) -> bool:
        """True if an alarm of this type was already raised within the debounce window."""
        cutoff = (datetime.now(timezone.utc) - timedelta(seconds=self.debounce_seconds)).isoformat()
        return any(
            a.get("alarmType") == alarm_type and a.get("recordedAt", "") >= cutoff
            for a in self.history.list_alerts(stage_id, 25)
        )

    @staticmethod
    def _parse(value):
        try:
            return datetime.fromisoformat(value)
        except (TypeError, ValueError):
            return None

    # ---------------- shared ----------------
    def _record(self, stage_id: str, alarm_type: str, severity: str, message: str, details: dict) -> dict:
        return self.history.record_alert(
            stage_id=stage_id,
            alarm_type=alarm_type,
            severity=severity,
            message=message,
            details=details,
        )

    @staticmethod
    def update_stage_twin(client, stage_id: str, alerts: list[dict]) -> None:
        """Expose the most recent alarm on the stage twin for real-time clients."""
        if not alerts:
            return
        alert = alerts[-1]
        client.update_digital_twin(stage_id, [
            {"op": "replace", "path": "/lastAlertLevel", "value": alert["severity"]},
            {"op": "replace", "path": "/lastAlertMessage", "value": alert["message"]},
            {"op": "replace", "path": "/lastAlertTime", "value": alert["recordedAt"]},
        ])
