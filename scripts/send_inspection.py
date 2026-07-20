import os
from pathlib import Path
import requests

IMAGE_PATH = (
    Path(__file__).resolve().parent.parent
    / "sample_images"
    / "crazing.jpg"
)

FUNCTION_URL = os.getenv("FERROTWIN_FUNCTION_URL", "http://localhost:7071/api/inspection")

files = {
    "image": open(IMAGE_PATH, "rb")
}

headers = {}
if function_key := os.getenv("FERROTWIN_FUNCTION_KEY"):
    headers["x-functions-key"] = function_key
response = requests.post(FUNCTION_URL, files=files, headers=headers)

print(response.status_code)
print(response.text)
