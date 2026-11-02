"""Azure Blob Storage adapter (Azure mode). Authenticates with managed identity / DefaultAzureCredential.

Not exercised against a real account yet: no Azure resources may be used before award and written
authorization (brief §20). The interface and immutability semantics match LocalStorageAdapter.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from marianos_headless.storage.base import StorageAdapter


class AzureBlobStorageAdapter(StorageAdapter):
    def __init__(self, account_url: str, container: str, credential: Any | None = None):
        from azure.identity import DefaultAzureCredential
        from azure.storage.blob import BlobServiceClient

        self._account_url = account_url
        self._container_name = container
        service = BlobServiceClient(
            account_url=account_url, credential=credential or DefaultAzureCredential()
        )
        self._container = service.get_container_client(container)

    def _read(self, key: str) -> bytes | None:
        from azure.core.exceptions import ResourceNotFoundError

        try:
            data: bytes = self._container.download_blob(key).readall()
        except ResourceNotFoundError:
            return None
        return data

    def _write(self, key: str, data: bytes, content_type: str, overwrite: bool) -> None:
        from azure.storage.blob import ContentSettings

        # overwrite=False makes the service reject a concurrent writer (If-None-Match: *).
        self._container.upload_blob(
            key, data, overwrite=overwrite, content_settings=ContentSettings(content_type=content_type)
        )

    def list(self, prefix: str) -> Iterator[str]:
        for blob in self._container.list_blobs(name_starts_with=prefix):
            yield str(blob.name)

    def describe(self) -> str:
        return f"azure_blob:{self._account_url}/{self._container_name}"
