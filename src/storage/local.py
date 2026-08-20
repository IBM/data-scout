import os
import shutil
from pathlib import Path
from typing import Optional


class LocalStorageBackend:
    def __init__(self, base_dir: str = "storage_output"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def upload_folder(self, local_folder: Path, remote_prefix: str) -> bool:
        dest = self.base_dir / remote_prefix
        try:
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

    def get_file_info(self, remote_path: str) -> Optional[dict]:
        full_path = self.base_dir / remote_path
        if not full_path.is_file():
            return None
        stat = full_path.stat()
        return {
            "size_bytes": stat.st_size,
            "last_modified": None,
        }
