import os

import requests

FUNCTION_URL = os.getenv("FERROTWIN_FUNCTION_URL", "http://localhost:7071/api/telemetry")


def send_telemetry(
    stage_id: str,
    temperature: float,
    status: str,
):
    payload = {
        "stageId": stage_id,
        "temperature": temperature,
        "status": status,
    }

    headers = {}
    if function_key := os.getenv("FERROTWIN_FUNCTION_KEY"):
        headers["x-functions-key"] = function_key
    response = requests.post(
        FUNCTION_URL,
        json=payload,
        headers=headers,
    )

    return response


if __name__ == "__main__":

    response = send_telemetry(
        "stage01",
        845,
        "Running",
    )

    print(response.status_code)
    print(response.text)
