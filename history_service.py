from azure.data.tables import TableServiceClient
from azure.identity import DefaultAzureCredential

from datetime import datetime, timezone
import uuid
import os
import logging


class HistoryService:

    def __init__(self):

        logging.info("HistoryService initialized")

        endpoint = (
            f"https://{os.environ['STORAGE_ACCOUNT_NAME']}.table.core.windows.net"
        )

        credential = DefaultAzureCredential()

        self.service = TableServiceClient(
            endpoint=endpoint,
            credential=credential,
        )

        self.table_client = self.service.create_table_if_not_exists(
            table_name="StageReadings"
        )

    def record_reading(
        self,
        stage_id: str,
        temperature: float,
        status: str,
    ):

        logging.info("Saving reading to Azure Table Storage")

        now = datetime.now(timezone.utc)

        self.table_client.upsert_entity(
            {
                "PartitionKey": stage_id,
                "RowKey": f"{now.isoformat()}_{uuid.uuid4().hex}",

                "temperature": temperature,
                "status": status,
                "timestamp": now.isoformat(),
            }
        )

        logging.info("Reading saved.")