import os
import time
import logging
from pathlib import Path
from typing import Optional

import boto3
from pyarrow.fs import S3FileSystem, copy_files, FileType


logger = logging.getLogger("pipeline_logger")


class S3StorageBackend:
    def __init__(self, access_key: str, secret_key: str, endpoint: str, region: str = "us-east-1", bucket: str = ""):
        self.access_key = access_key
        self.secret_key = secret_key
        self.endpoint = endpoint
        self.region = region
        self.bucket = bucket

        self._s3fs = S3FileSystem(
            access_key=self.access_key,
            secret_key=self.secret_key,
            endpoint_override=self.endpoint,
            region=self.region,
        )

        self._boto_client = boto3.client(
            "s3",
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            endpoint_url=self.endpoint,
            region_name=self.region,
        )

    def upload_folder(self, local_folder: Path, remote_prefix: str) -> bool:
        src_folder = str(local_folder)
        try:
            for root, _, files in os.walk(src_folder):
                for file_name in files:
                    local_path = os.path.join(root, file_name)
                    rel_path = os.path.relpath(local_path, src_folder)
                    dest_path = os.path.join(remote_prefix, rel_path).replace("\\", "/")

                    tries = 0
                    while tries < 10:
                        try:
                            copy_files(local_path, dest_path, destination_filesystem=self._s3fs)
                            logger.info(f"Wrote {dest_path}")
                            break
                        except Exception as e:
                            logger.error(f"Could not write {dest_path}. Error: {e}")
                            time.sleep(5)
                            tries += 1
                    else:
                        raise Exception(f"Failed to upload file after 10 tries: {local_path}")

            return True

        except Exception as e:
            logger.error(f"Upload folder failed: {e}")
            return False

    def read_file(self, remote_path: str) -> bytes:
        with self._s3fs.open_input_file(remote_path) as f:
            return f.read()

    def file_exists(self, remote_path: str) -> bool:
        info = self._s3fs.get_file_info(remote_path)
        return info.type == FileType.File

    def list_files(self, remote_prefix: str) -> list[str]:
        from pyarrow.fs import FileSelector
        selector = FileSelector(remote_prefix, recursive=True)
        file_infos = self._s3fs.get_file_info(selector)
        return [fi.path for fi in file_infos if fi.type == FileType.File]

    def generate_presigned_url(self, remote_path: str, expires_in: int = 900) -> Optional[str]:
        bucket, key = remote_path.split("/", 1)
        return self._boto_client.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": key},
            ExpiresIn=expires_in,
        )

    def get_file_info(self, remote_path: str) -> Optional[dict]:
        info = self._s3fs.get_file_info(remote_path)
        if info.type != FileType.File:
            return None
        return {
            "size_bytes": info.size,
            "last_modified": info.mtime.isoformat() if info.mtime else None,
        }
