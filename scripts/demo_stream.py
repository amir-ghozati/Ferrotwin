"""Live demo driver for FerroTwin.

Continuously sends telemetry for all three stages and periodically posts a real
inspection image, so the dashboard fills with temperature trends, defect
distribution, inspection history, and alarms.

Every few minutes it injects a heat excursion on stage03 to trigger the alarm
engine (temperature >= threshold) — useful for showing the alarm banner live.

Configure with environment variables (same ones the other scripts use):
    FERROTWIN_FUNCTION_URL   e.g. https://<app>.azurewebsites.net/api
    FERROTWIN_FUNCTION_KEY   the Function (host) key

Run:
    python scripts/demo_stream.py
Stop with Ctrl+C.
"""

import os
import random
import time
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from datetime import datetime

BASE_URL = os.getenv("FERROTWIN_FUNCTION_URL", "http://localhost:7071/api").rstrip("/")
KEY = os.getenv("FERROTWIN_FUNCTION_KEY", "")
HEADERS = {"x-functions-key": KEY} if KEY else {}

SAMPLE_DIR = Path(__file__).resolve().parent.parent / "sample_images"
SAMPLES = sorted(p for p in SAMPLE_DIR.glob("*.jpg"))

STAGES = {
    "stage01": {"base": 845, "band": 4},
    "stage02": {"base": 770, "band": 4},
    "stage03": {"base": 905, "band": 5},
}

TELEMETRY_EVERY = 3          # seconds between telemetry sweeps
INSPECT_EVERY = 4            # send an inspection every N sweeps
EXCURSION_EVERY = 40         # force a stage03 heat alarm every N sweeps
EXCURSION_TEMP = 955         # >= default 900 threshold -> critical alarm

session = requests.Session()

retry = Retry(
    total=5,
    connect=5,
    read=5,
    backoff_factor=1,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=frozenset(["GET", "POST"])
)

adapter = HTTPAdapter(max_retries=retry)

session.mount("http://", adapter)
session.mount("https://", adapter)
def post_telemetry(stage_id, temperature, status="Running"):
    for attempt in range(3):
        try:
            r = session.post(
            f"{BASE_URL}/telemetry",
            json={"stageId": stage_id, "temperature": round(temperature, 1), "status": status},
            headers=HEADERS, timeout=30,
        )
            return r.status_code
        
        except requests.RequestException as ex:
            print(f"Telemetry failed ({ex}), retry {attempt+1}/3")
            time.sleep(2)
    return None


def post_inspection(stage_id):
    for attempt in range(3):
        try:
            image = random.choice(SAMPLES)
            with open(image, "rb") as f:
                r = session.post(
                    f"{BASE_URL}/inspection",
                    files={"image": (image.name, f, "image/jpeg")},
                    data={"stageId": stage_id, "stationId": "inspection01"},
                    headers=HEADERS, timeout=60,
                )
            body = r.json()
            return r.status_code, body.get("defect"), body.get("confidence")
        
        except Exception as ex:
            print(f"Inspection failed ({ex}), retry {attempt+1}/3")
            time.sleep(2)
    return None, None, None


def main():
    if not SAMPLES:
        raise SystemExit(f"No sample images found in {SAMPLE_DIR}")
    print(f"Streaming to {BASE_URL}  (key {'set' if KEY else 'MISSING'})")
    print("Ctrl+C to stop.\n")
    sweep = 0
    try:
        while True:
            sweep += 1
            timestamp = datetime.now().strftime("%H:%M:%S")
            print(f"\n[{timestamp}] Sweep {sweep}")
            
            force_excursion = sweep % EXCURSION_EVERY == 0
            for stage_id, cfg in STAGES.items():
                if force_excursion and stage_id == "stage03":
                    temp, status = EXCURSION_TEMP + random.uniform(0, 8), "Error"
                else:
                    temp, status = cfg["base"] + random.uniform(-cfg["band"], cfg["band"]), "Running"
                code = post_telemetry(stage_id, temp, status)
                flag = "  <-- HEAT EXCURSION" if (force_excursion and stage_id == "stage03") else ""
                print(f"  {stage_id}  {temp:7.1f}C  HTTP {code}{flag}")

            if sweep % INSPECT_EVERY == 0:
                stage = random.choice(list(STAGES))
                code, defect, conf = post_inspection(stage)
                conf_txt = f"{conf*100:.1f}%" if conf is not None else "n/a"
                print(f"  inspection @ {stage}: {defect} ({conf_txt})  HTTP {code}")

            print("-" * 46)
            time.sleep(TELEMETRY_EVERY)
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
