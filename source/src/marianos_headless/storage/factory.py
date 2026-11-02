"""Build the configured storage adapter."""

from __future__ import annotations

from pathlib import Path

from marianos_headless.core.settings import StorageSettings
from marianos_headless.storage.base import StorageAdapter
from marianos_headless.storage.local import LocalStorageAdapter


def make_storage(settings: StorageSettings, base_dir: Path | None = None) -> StorageAdapter:
    if settings.backend == "local":
        root = Path(settings.local_root)
        if not root.is_absolute() and base_dir is not None:
            root = base_dir / root
        return LocalStorageAdapter(root)
    if not settings.azure_account_url or not settings.azure_container:
        raise ValueError("azure_blob storage needs azure_account_url and azure_container")
    from marianos_headless.storage.azure_blob import AzureBlobStorageAdapter

    return AzureBlobStorageAdapter(settings.azure_account_url, settings.azure_container)
