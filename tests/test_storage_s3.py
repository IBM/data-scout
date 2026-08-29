# Copyright 2025-2026 IBM Corporation
# SPDX-License-Identifier: Apache-2.0

"""S3StorageBackend bucket/key resolution.

pyarrow's S3FileSystem addresses objects as "bucket/key", so every path here is
bucket-qualified by design. STORAGE_BUCKET was accepted and documented but never
read, so the bucket came solely from the first path segment."""
from unittest.mock import patch

from src.storage.s3 import S3StorageBackend


class TestS3BucketResolution:
    """#3 -- STORAGE_BUCKET was accepted and documented but never read."""

    def _backend(self, bucket):
        with patch("src.storage.s3.S3FileSystem"), patch("src.storage.s3.boto3.client"):
            return S3StorageBackend("ak", "sk", "https://s3.example", "us-east-1", bucket)

    def test_configured_bucket_is_used(self):
        b = self._backend("my-bucket")
        assert b._split_bucket_key("results/run/x.zip") == ("my-bucket", "results/run/x.zip")

    def test_bucket_qualified_path_is_not_double_prefixed(self):
        b = self._backend("my-bucket")
        assert b._split_bucket_key("my-bucket/run/x.zip") == ("my-bucket", "run/x.zip")

    def test_falls_back_to_first_segment_when_unset(self):
        """Historical behaviour, preserved: pyarrow paths are bucket-qualified."""
        b = self._backend("")
        assert b._split_bucket_key("results/run/x.zip") == ("results", "run/x.zip")

    def test_presigned_url_uses_configured_bucket(self):
        b = self._backend("my-bucket")
        b.generate_presigned_url("results/run/x.zip", expires_in=60)
        b._boto_client.generate_presigned_url.assert_called_once_with(
            "get_object",
            Params={"Bucket": "my-bucket", "Key": "results/run/x.zip"},
            ExpiresIn=60,
        )

    def test_presigned_url_without_configured_bucket(self):
        b = self._backend("")
        b.generate_presigned_url("results/run/x.zip")
        _, kwargs = b._boto_client.generate_presigned_url.call_args
        assert kwargs["Params"] == {"Bucket": "results", "Key": "run/x.zip"}
