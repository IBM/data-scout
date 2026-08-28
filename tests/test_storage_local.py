import pytest
from pathlib import Path

from src.storage import create_storage_backend
from src.storage.local import LocalStorageBackend


@pytest.fixture
def run_folder(tmp_path):
    """A run folder as the pipeline would leave it."""
    folder = tmp_path / "results" / "searchresults" / "abc123"
    folder.mkdir(parents=True)
    (folder / "topics.jsonl").write_text('{"topic": "math"}\n', encoding="utf-8")
    return folder


class TestLocalStorageBackendRooting:
    def test_prefix_is_relative_to_working_directory(self, run_folder, monkeypatch, tmp_path):
        """A run prefix resolves without any extra directory segment prepended."""
        monkeypatch.chdir(tmp_path)
        backend = LocalStorageBackend()

        info = backend.get_file_info("results/searchresults/abc123/topics.jsonl")

        assert info is not None
        assert info["size_bytes"] == len('{"topic": "math"}\n')

    def test_create_storage_backend_does_not_reroot_local(self, monkeypatch, tmp_path):
        """storage_upload_dir must not become the local backend's root: the
        prefixes stored per job already contain their own root segment."""
        monkeypatch.chdir(tmp_path)

        class _Config:
            storage_backend = "local"
            storage_upload_dir = "results"

        backend = create_storage_backend(_Config())

        assert backend.base_dir == Path(".")

    def test_missing_file_reports_none(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        backend = LocalStorageBackend()

        assert backend.get_file_info("results/searchresults/nope/topics.jsonl") is None


class TestLocalStorageBackendUpload:
    def test_upload_onto_itself_preserves_the_run_folder(self, run_folder, monkeypatch, tmp_path):
        """When the published location is the run folder, upload is a no-op --
        it must not clear the destination first and destroy the outputs."""
        monkeypatch.chdir(tmp_path)
        backend = LocalStorageBackend()

        assert backend.upload_folder(run_folder, "results/searchresults/abc123") is True
        assert (run_folder / "topics.jsonl").is_file()

    def test_upload_to_a_separate_prefix_copies(self, run_folder, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        backend = LocalStorageBackend()

        assert backend.upload_folder(run_folder, "published/searchresults/abc123") is True
        assert (tmp_path / "published/searchresults/abc123/topics.jsonl").is_file()
        assert (run_folder / "topics.jsonl").is_file()

    def test_upload_replaces_stale_destination(self, run_folder, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        backend = LocalStorageBackend()
        stale = tmp_path / "published/searchresults/abc123"
        stale.mkdir(parents=True)
        (stale / "leftover.jsonl").write_text("old", encoding="utf-8")

        assert backend.upload_folder(run_folder, "published/searchresults/abc123") is True
        assert not (stale / "leftover.jsonl").exists()
        assert (stale / "topics.jsonl").is_file()
