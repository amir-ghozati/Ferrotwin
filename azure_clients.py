"""Shared Azure client configuration for local development and Azure hosting."""

import os

from azure.identity import DefaultAzureCredential


def get_credential() -> DefaultAzureCredential:
    """Use managed identity in Azure and Azure CLI credentials locally."""
    return DefaultAzureCredential(
        exclude_interactive_browser_credential=True,
        exclude_visual_studio_code_credential=True,
    )


def get_storage_connection_string() -> str | None:
    """Return the Functions storage connection string when it is configured."""
    return os.getenv("AzureWebJobsStorage") or os.getenv("AZURE_STORAGE_CONNECTION_STRING")
