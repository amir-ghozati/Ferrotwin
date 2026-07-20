from azure.digitaltwins.core import DigitalTwinsClient


class InspectionTwinService:

    def __init__(self, client: DigitalTwinsClient):
        self.client = client

    def update_defect(
        self,
        twin_id: str,
        defect: str,
        confidence: float,
        image_url: str,
        inspection_id: str,
        station_id: str,
        inspected_at: str,
    ):

        patch = [
            {
                "op": "replace",
                "path": "/lastDetectedDefect",
                "value": defect,
            },
            {
                "op": "replace",
                "path": "/lastDefectConfidence",
                "value": confidence,
            }
        ]

        self.client.update_digital_twin(
            twin_id,
            patch,
        )

        self.client.update_digital_twin(
            station_id,
            [
                {"op": "replace", "path": "/lastDefect", "value": defect},
                {"op": "replace", "path": "/confidence", "value": confidence},
                {"op": "replace", "path": "/lastImageUrl", "value": image_url},
                {"op": "replace", "path": "/lastInspectionId", "value": inspection_id},
                {"op": "replace", "path": "/lastInspectionTime", "value": inspected_at},
            ],
        )
