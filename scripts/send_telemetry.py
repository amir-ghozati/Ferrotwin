import requests

FUNCTION_URL = "http://localhost:7071/api/telemetry"

payload = {
    "stageId": "stage1",
    "temperature": 845,
    "status": "Running",
}

response = requests.post(FUNCTION_URL, json=payload)

print(response.status_code)
print(response.text)