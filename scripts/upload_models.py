"""Upload the current DTDL model versions in dependency order."""

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from azure.core.exceptions import HttpResponseError
from azure.digitaltwins.core import DigitalTwinsClient
from azure_clients import get_credential

client = DigitalTwinsClient(os.environ["ADT_HOST"], get_credential())

# Upload in dependency order (leaf models first). Idempotent: a model version
# that already exists is skipped, so this is safe to re-run during deploys.
for filename in ("InspectionStation.json", "ProcessStage.json", "ProductionLine.json", "Factory.json"):
    model = json.loads((ROOT / "dtdl" / filename).read_text(encoding="utf-8"))
    try:
        client.create_models([model])
        print(f"Uploaded: {model['@id']}")
    except HttpResponseError as ex:
        if ex.status_code == 409 or "ModelIdAlreadyExists" in str(ex):
            print(f"Exists, skipped: {model['@id']}")
        else:
            raise
