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

    def _split_bucket_key(self, remote_path: str) -> tuple[str, str]:
        """Split a bucket-qualified remote path into (bucket, key).

        Every path in this class is bucket-qualified, because pyarrow's
        S3FileSystem addresses objects as "bucket/key" -- so the prefix handed in
        (STORAGE_UPLOAD_DIR/output_base/run_id) must begin with the bucket name.
        That convention is load-bearing and is kept here.

        What was broken is that STORAGE_BUCKET was accepted, documented in
        .env.example, and then never read: the bucket came solely from the first
        path segment. Setting STORAGE_BUCKET=my-bucket with the default
        STORAGE_UPLOAD_DIR=results silently addressed a bucket named "results".
        When STORAGE_BUCKET is set it now wins, and a path already carrying it is
        not double-prefixed.
        """
        if self.bucket:
            prefix = f"{self.bucket}/"
            if remote_path == self.bucket:
                return self.bucket, ""
            if remote_path.startswith(prefix):
                return self.bucket, remote_path[len(prefix):]
            return self.bucket, remote_path.lstrip("/")

        # No STORAGE_BUCKET configured: fall back to the historical behaviour of
        # treating the first path segment as the bucket.
        if "/" not in remote_path:
            return remote_path, ""
        bucket, key = remote_path.split("/", 1)
        return bucket, key

    def generate_presigned_url(self, remote_path: str, expires_in: int = 900) -> Optional[str]:
        bucket, key = self._split_bucket_key(remote_path)
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
