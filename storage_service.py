"""Private Blob Storage persistence for inspection images."""

import os
import re
import uuid
from datetime import datetime, timezone
from urllib.parse import unquote
from urllib.parse import unquote

from azure.storage.blob import BlobServiceClient, ContentSettings
from azure.core.exceptions import ResourceExistsError

from azure_clients import get_credential, get_storage_connection_string


class InspectionImageStorage:
    def __init__(self) -> None:
        self.container_name = os.getenv("INSPECTION_BLOB_CONTAINER", "inspections")
        connection_string = get_storage_connection_string()
        if connection_string:
            self.service = BlobServiceClient.from_connection_string(connection_string)
        else:
            account_name = os.environ["STORAGE_ACCOUNT_NAME"]
            self.service = BlobServiceClient(
                account_url=f"https://{account_name}.blob.core.windows.net",
                credential=get_credential(),
            )
        self.container = self.service.get_container_client(self.container_name)
        try:
            self.container.create_container()
        except ResourceExistsError:
            pass

    def upload(self, image_bytes: bytes, filename: str, content_type: str | None) -> str:
        extension = os.path.splitext(filename)[1].lower()
        if extension not in {".jpg", ".jpeg", ".png", ".bmp"}:
            extension = ".jpg"
        safe_filename = re.sub(r"[^a-zA-Z0-9_-]", "-", os.path.splitext(filename)[0])[:80]
        timestamp = datetime.now(timezone.utc).strftime("%Y/%m/%d/%H%M%S")
        blob_name = f"{timestamp}-{uuid.uuid4().hex}-{safe_filename or 'inspection'}{extension}"
        blob = self.container.get_blob_client(blob_name)
        blob.upload_blob(
            image_bytes,
            overwrite=False,
            content_settings=ContentSettings(content_type=content_type or "application/octet-stream"),
        )
        return blob.url

    def download(self, blob_url: str) -> tuple[bytes, str]:
        """Read a private inspection image only when it belongs to this container."""
        prefix = f"{self.container.url}/"
        if not blob_url.startswith(prefix):
            raise ValueError("The requested image is outside the inspections container.")
        blob_name = unquote(blob_url[len(prefix):])
        response = self.container.get_blob_client(blob_name).download_blob()
        content_type = response.properties.content_settings.content_type or "application/octet-stream"
        return response.readall(), content_type

    def download(self, blob_url: str) -> tuple[bytes, str]:
        """Read a private inspection image only when it belongs to this container."""
        prefix = f"{self.container.url}/"
        if not blob_url.startswith(prefix):
            raise ValueError("The requested image is outside the inspections container.")
        blob_name = unquote(blob_url[len(prefix):])
        response = self.container.get_blob_client(blob_name).download_blob()
        content_type = response.properties.content_settings.content_type or "application/octet-stream"
        return response.readall(), content_type
