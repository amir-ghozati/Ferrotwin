from pathlib import Path
import json
import yaml

from azure.identity import DefaultAzureCredential
from azure.digitaltwins.core import DigitalTwinsClient

HOST = "https://ferrotwin-adt.api.weu.digitaltwins.azure.net"

credential = DefaultAzureCredential()
client = DigitalTwinsClient(HOST, credential)

BASE = Path(__file__).parent.parent


def load_model(model_id: str, name: str):
    return {
        "$metadata": {
            "$model": model_id
        },
        "name": name
    }


with open(BASE / "bootstrap" / "graph.yaml", "r") as f:
    graph = yaml.safe_load(f)

# ---------- Factory ----------

factory = graph["factory"]

client.upsert_digital_twin(
    factory["id"],
    load_model(
        "dtmi:ferrotwin:Factory;1",
        factory["name"]
    )
)

# ---------- Lines ----------

for line in graph["lines"]:

    client.upsert_digital_twin(
        line["id"],
        load_model(
            "dtmi:ferrotwin:ProductionLine;1",
            line["name"]
        )
    )

    client.upsert_relationship(
        factory["id"],
        f"{factory['id']}-{line['id']}",
        {
            "$relationshipId": f"{factory['id']}-{line['id']}",
            "$sourceId": factory["id"],
            "$relationshipName": "contains",
            "$targetId": line["id"]
        }
    )

# ---------- Stages ----------

previous = None

for stage in graph["stages"]:

    client.upsert_digital_twin(
        stage["id"],
        load_model(
            "dtmi:ferrotwin:ProcessStage;1",
            stage["name"]
        )
    )

    if previous is not None:

        client.upsert_relationship(
            previous,
            f"{previous}-{stage['id']}",
            {
                "$relationshipId": f"{previous}-{stage['id']}",
                "$sourceId": previous,
                "$relationshipName": "feedsInto",
                "$targetId": stage["id"]
            }
        )

    previous = stage["id"]

# ---------- Stations ----------

for station in graph["stations"]:

    client.upsert_digital_twin(
        station["id"],
        load_model(
            "dtmi:ferrotwin:InspectionStation;1",
            station["name"]
        )
    )

print("Bootstrap complete.")