import os
import shutil
from pathlib import Path
from typing import Optional

from src.storage.base import StorageBackend


class LocalStorageBackend(StorageBackend):
    """Addresses files by a path relative to base_dir.

    base_dir defaults to the working directory because the prefixes handed to
    this backend already carry their own root (`results_dir` for a run folder,
    `storage_upload_dir` for a published copy). Rooting it at
    `storage_upload_dir` instead double-counted that segment.
    """

    def __init__(self, base_dir: str = "."):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def upload_folder(self, local_folder: Path, remote_prefix: str) -> bool:
        dest = self.base_dir / remote_prefix
        try:
            # With storage_upload_dir == results_dir the published copy *is* the
            # run folder. Without this guard the rmtree below would delete the
            # run's output and then copytree from the hole it just made.
            if dest.resolve() == Path(local_folder).resolve():
                return True
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(local_folder, dest)
            return True
        except Exception:
            return False

    def read_file(self, remote_path: str) -> bytes:
        full_path = self.base_dir / remote_path
        return full_path.read_bytes()

    def file_exists(self, remote_path: str) -> bool:
        return (self.base_dir / remote_path).is_file()

    def list_files(self, remote_prefix: str) -> list[str]:
        prefix_path = self.base_dir / remote_prefix
        if not prefix_path.exists():
            return []
        return [
            str(p.relative_to(self.base_dir))
            for p in prefix_path.rglob("*")
            if p.is_file()
        ]

    def generate_presigned_url(self, remote_path: str, expires_in: int = 900) -> Optional[str]:
        return None

    def local_path(self, remote_path: str) -> Optional[Path]:
        return self.base_dir / remote_path

    def get_file_info(self, remote_path: str) -> Optional[dict]:
        full_path = self.base_dir / remote_path
        if not full_path.is_file():
            return None
        stat = full_path.stat()
        return {
            "size_bytes": stat.st_size,
            "last_modified": None,
        }
