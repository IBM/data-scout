# Copyright 2025-2026 IBM Corporation
# SPDX-License-Identifier: Apache-2.0

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional


class StorageBackend(ABC):
    @abstractmethod
    def upload_folder(self, local_folder: Path, remote_prefix: str) -> bool:
        ...

    @abstractmethod
    def read_file(self, remote_path: str) -> bytes:
        ...

    @abstractmethod
    def file_exists(self, remote_path: str) -> bool:
        ...

    @abstractmethod
    def list_files(self, remote_prefix: str) -> list[str]:
        ...

    @abstractmethod
    def generate_presigned_url(self, remote_path: str, expires_in: int = 900) -> Optional[str]:
        ...

    @abstractmethod
    def get_file_info(self, remote_path: str) -> Optional[dict]:
        ...

    def local_path(self, remote_path: str) -> Optional[Path]:
        """Filesystem path for a stored file, or None if it is not on this host.

        Backends that keep files on disk return a path the API can serve
        directly; remote backends return None and are downloaded through a
        presigned URL instead.
        """
        return None
