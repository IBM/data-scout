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
