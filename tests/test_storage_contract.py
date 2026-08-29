# Copyright 2025-2026 IBM Corporation
# SPDX-License-Identifier: Apache-2.0

"""Both storage backends must satisfy the StorageBackend interface.

They used to be plain classes, so the ABC enforced nothing and
`create_storage_backend`'s `-> StorageBackend` annotation was inaccurate. That is
why S3StorageBackend was missing `local_path` and routes.py probed for it with
getattr."""
import inspect
from types import SimpleNamespace

import pytest

from src.storage import create_storage_backend
from src.storage.base import StorageBackend
from src.storage.local import LocalStorageBackend
from src.storage.s3 import S3StorageBackend


class TestStorageBackendsImplementTheABC:
    """Both were plain classes, so the ABC enforced nothing and
    `create_storage_backend`'s return annotation was inaccurate. That is why
    S3StorageBackend was missing `local_path` and routes.py needed a getattr."""

    @pytest.mark.parametrize("cls", [LocalStorageBackend, S3StorageBackend])
    def test_backend_subclasses_the_abc(self, cls):
        assert issubclass(cls, StorageBackend)

    def test_local_backend_is_the_annotated_type(self):
        backend = create_storage_backend(SimpleNamespace(storage_backend="local"))

        assert isinstance(backend, StorageBackend)

    def test_missing_method_now_fails_at_instantiation(self):
        """The point of inheriting: the next missing method is caught immediately."""

        class Incomplete(StorageBackend):
            pass

        with pytest.raises(TypeError):
            Incomplete()

    def test_local_path_is_a_declared_method_not_a_duck_typed_extra(self):
        assert "local_path" in StorageBackend.__dict__

    def test_s3_inherits_the_none_default(self):
        s3 = S3StorageBackend.__new__(S3StorageBackend)

        assert s3.local_path("bucket/key") is None

    def test_routes_calls_local_path_directly(self):
        """The getattr workaround should be gone now that it is on the ABC."""
        from src.api import routes

        assert 'getattr(storage, "local_path"' not in inspect.getsource(routes)
