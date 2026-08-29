# Copyright 2025-2026 IBM Corporation
# SPDX-License-Identifier: Apache-2.0

"""ResultHandler output writing and upload.

`save_metrics` and `compute_annotation_metrics` are exercised through the
pipeline; these cover the paths that were not: writing results in both formats,
zipping, and the upload wrapper that must not let a storage failure kill a run.
"""
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.pipeline.result_handler import ResultHandler

ROWS = [
    {"link": "https://a.example", "title": "A", "tags": ["x", "y"], "meta": {"k": 1}},
    {"link": "https://b.example", "title": "B", "tags": [], "meta": {}},
]


def _handler(tmp_path, output_format="jsonl", notify=None):
    return ResultHandler(
        output_folder=tmp_path,
        output_base="searchresults",
        output_format=output_format,
        settings=SimpleNamespace(storage_backend="local"),
        notify_fn=notify or MagicMock(),
    )


class TestSaveResultsJsonl:
    def test_writes_one_json_object_per_line(self, tmp_path):
        _handler(tmp_path).save_results(ROWS)

        lines = (tmp_path / "searchresults.jsonl").read_text().strip().splitlines()
        assert len(lines) == 2
        assert json.loads(lines[0])["link"] == "https://a.example"

    def test_nested_values_survive_the_round_trip(self, tmp_path):
        _handler(tmp_path).save_results(ROWS)

        first = json.loads((tmp_path / "searchresults.jsonl").read_text().splitlines()[0])
        assert first["tags"] == ["x", "y"]
        assert first["meta"] == {"k": 1}

    def test_reports_the_count(self, tmp_path):
        notify = MagicMock()
        _handler(tmp_path, notify=notify).save_results(ROWS)

        assert "2 results" in " ".join(str(c) for c in notify.call_args_list)


class TestSaveResultsParquet:
    def test_writes_a_readable_parquet(self, tmp_path):
        _handler(tmp_path, output_format="parquet").save_results(ROWS)

        df = pd.read_parquet(tmp_path / "searchresults.parquet")
        assert list(df["link"]) == ["https://a.example", "https://b.example"]

    def test_empty_collections_become_null_not_a_type_error(self, tmp_path):
        """Mixed empty/populated dict and list columns cannot be written directly;
        they are JSON-encoded, and empty ones nulled."""
        _handler(tmp_path, output_format="parquet").save_results(ROWS)

        df = pd.read_parquet(tmp_path / "searchresults.parquet")
        assert df["tags"].iloc[1] is None
        assert json.loads(df["tags"].iloc[0]) == ["x", "y"]


class TestUnsupportedFormat:
    def test_raises_rather_than_writing_nothing(self, tmp_path):
        with pytest.raises(ValueError, match="Unsupported format"):
            _handler(tmp_path, output_format="csv").save_results(ROWS)


class TestZipRunOutputs:
    def test_creates_an_archive_named_for_the_run(self, tmp_path):
        handler = _handler(tmp_path)
        handler.save_results(ROWS)

        handler.zip_run_outputs("run-123")

        assert (tmp_path / "searchresults_run-123.zip").is_file()

    def test_failure_is_reported_at_error_level(self, tmp_path):
        notify = MagicMock()
        handler = _handler(tmp_path, notify=notify)

        with patch("src.pipeline.result_handler.zip_folder", return_value=None):
            handler.zip_run_outputs("run-123")

        assert any(c.kwargs.get("level") == "error" for c in notify.call_args_list)


class TestUploadRunOutputs:
    def test_successful_upload_is_reported(self, tmp_path):
        notify = MagicMock()
        backend = MagicMock()
        backend.upload_folder.return_value = True

        with patch("src.pipeline.result_handler.create_storage_backend", return_value=backend):
            _handler(tmp_path, notify=notify).upload_run_outputs("results/searchresults/j1")

        backend.upload_folder.assert_called_once()
        assert "Successfully uploaded" in " ".join(str(c) for c in notify.call_args_list)

    def test_failed_upload_is_reported_without_raising(self, tmp_path):
        notify = MagicMock()
        backend = MagicMock()
        backend.upload_folder.return_value = False

        with patch("src.pipeline.result_handler.create_storage_backend", return_value=backend):
            _handler(tmp_path, notify=notify).upload_run_outputs("prefix")

        assert any(c.kwargs.get("level") == "error" for c in notify.call_args_list)

    def test_storage_exception_does_not_end_the_run(self, tmp_path):
        """The results are already on disk at this point; an upload failure must
        not lose the run."""
        notify = MagicMock()

        with patch("src.pipeline.result_handler.create_storage_backend",
                   side_effect=RuntimeError("endpoint unreachable")):
            _handler(tmp_path, notify=notify).upload_run_outputs("prefix")

        logged = " ".join(str(c) for c in notify.call_args_list)
        assert "endpoint unreachable" in logged
