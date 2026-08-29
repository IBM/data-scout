# Copyright 2025-2026 IBM Corporation
# SPDX-License-Identifier: Apache-2.0

from src.storage.base import StorageBackend
from src.storage.s3 import S3StorageBackend
from src.storage.local import LocalStorageBackend


def create_storage_backend(config) -> StorageBackend:
    if config.storage_backend == "s3":
        return S3StorageBackend(
            access_key=config.storage_access_key_id,
            secret_key=config.storage_secret_access_key,
            endpoint=config.storage_endpoint,
            region=config.storage_region,
            bucket=config.storage_bucket,
        )
    # Rooted at the working directory: the prefixes stored per job are already
    # relative to it (see SearchPipeline._prepare_output_folder), so passing
    # storage_upload_dir here would prepend that segment a second time.
    return LocalStorageBackend()


__all__ = ["StorageBackend", "S3StorageBackend", "LocalStorageBackend", "create_storage_backend"]
