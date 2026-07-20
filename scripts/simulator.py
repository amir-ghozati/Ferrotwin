import random
import time

from send_telemetry import send_telemetry


STAGES = {
    "stage01": {
        "base_temperature": 845,
        "status": "Running",
    },
    "stage02": {
        "base_temperature": 770,
        "status": "Running",
    },
    "stage03": {
        "base_temperature": 905,
        "status": "Running",
    },
}


print("Simulator started...")
print("Press Ctrl+C to stop.\n")

try:

    while True:

        for stage_id, stage in STAGES.items():

            temperature = (
                stage["base_temperature"]
                + random.uniform(-3, 3)
            )

            response = send_telemetry(
                stage_id=stage_id,
                temperature=round(temperature, 1),
                status=stage["status"],
            )

            print(
                f"{stage_id:<8}"
                f"{temperature:>8.1f} °C"
                f"   HTTP {response.status_code}"
            )

        print("-" * 40)

        time.sleep(3)

except KeyboardInterrupt:

    print("\nSimulator stopped.")
