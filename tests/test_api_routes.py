import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient


@pytest.fixture
def mock_celery():
    with patch("src.api.routes.run_pipeline_task") as mock_task:
        mock_result = MagicMock()
        mock_result.id = "celery-task-id-123"
        mock_task.delay.return_value = mock_result
        yield mock_task


@pytest.fixture
def mock_redis_client():
    mock = MagicMock()
    mock.keys.return_value = []
    mock.hgetall.return_value = {}
    mock.hget.return_value = None
    mock.hset.return_value = None
    mock.rpush.return_value = None
    mock.publish.return_value = None
    mock.lrange.return_value = []
    return mock


@pytest.fixture
def client(mock_celery, mock_redis_client):
    with patch("src.job_tracking.job_tracker.redis.Redis") as mock_redis_cls, \
         patch("src.api.main.create_storage_backend") as mock_storage_factory, \
         patch("src.api.main.SearchConfig") as mock_config_cls:

        mock_redis_cls.return_value = mock_redis_client
        mock_storage_factory.return_value = MagicMock()

        mock_config = MagicMock()
        mock_config.redis_url = "redis://localhost:6379/0"
        mock_config.api_key = ""
        mock_config.cors_origins = ["http://localhost:3000"]
        mock_config_cls.return_value = mock_config

        from src.api.main import app
        app.state.storage = mock_storage_factory.return_value
        app.state.redis_url = mock_config.redis_url
        app.state.api_key = mock_config.api_key

        with TestClient(app) as test_client:
            yield test_client


class TestSubmitJob:
    def test_creates_job(self, client, mock_celery):
        response = client.post("/jobs/", json={
            "mode": "query",
            "input": "test topic",
            "perform_search": False,
        })
        assert response.status_code == 200
        data = response.json()
        assert "job_id" in data
        assert data["status"] == "queued"
        mock_celery.delay.assert_called_once()

    def test_invalid_mode_rejected(self, client):
        response = client.post("/jobs/", json={
            "mode": "invalid",
            "input": "test",
        })
        assert response.status_code == 422


class TestListJobs:
    def test_returns_empty_list(self, client, mock_redis_client):
        mock_redis_client.keys.return_value = []
        response = client.get("/jobs/")
        assert response.status_code == 200
        data = response.json()
        assert "jobs" in data
        assert isinstance(data["jobs"], list)


class TestGetJobDetails:
    def test_returns_job_info(self, client, mock_redis_client):
        mock_redis_client.hgetall.return_value = {
            b"status": b"running",
            b"mode": b"query",
            b"input": b"test",
        }
        response = client.get("/jobs/test-id-123")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "running"

    def test_returns_empty_for_missing_job(self, client, mock_redis_client):
        mock_redis_client.hgetall.return_value = {}
        response = client.get("/jobs/nonexistent")
        assert response.status_code == 200
        assert response.json() == {}


class TestGetProgress:
    def test_returns_progress(self, client, mock_redis_client):
        mock_redis_client.hget.side_effect = lambda key, field: {
            "status": b"running",
            "progress": b"Step 3 of 5",
        }.get(field)

        response = client.get("/jobs/test-id/progress")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "running"
        assert data["progress"] == "Step 3 of 5"

    def test_not_found(self, client, mock_redis_client):
        mock_redis_client.hget.return_value = None
        response = client.get("/jobs/missing/progress")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "not found"


class TestGetRedisLogs:
    def test_returns_cached_logs(self, client, mock_redis_client):
        mock_redis_client.lrange.return_value = [b"log line 1", b"log line 2"]
        response = client.get("/jobs/test-id/logs/redis")
        assert response.status_code == 200
        data = response.json()
        assert "log line 1" in data["logs"]


class TestGetRedisMetrics:
    def test_returns_cached_metrics(self, client, mock_redis_client):
        mock_redis_client.lrange.return_value = [b'{"queries": 5}']
        response = client.get("/jobs/test-id/metrics/redis")
        assert response.status_code == 200
        data = response.json()
        assert len(data["metrics"]) == 1
        assert data["metrics"][0]["queries"] == 5


class TestInterruptJob:
    def test_interrupt_running_job(self, client, mock_redis_client):
        mock_redis_client.hget.side_effect = lambda key, field: {
            "task_id": b"celery-task-123",
        }.get(field)

        with patch("src.api.routes.AsyncResult") as mock_async:
            mock_result = MagicMock()
            mock_result.state = "STARTED"
            mock_async.return_value = mock_result

            response = client.post("/jobs/test-id/interrupt")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "interrupted"
            mock_result.revoke.assert_called_once()

    def test_interrupt_no_task_id(self, client, mock_redis_client):
        mock_redis_client.hget.return_value = None
        response = client.post("/jobs/missing/interrupt")
        assert response.status_code == 404

    def test_interrupt_already_completed(self, client, mock_redis_client):
        mock_redis_client.hget.side_effect = lambda key, field: {
            "task_id": b"celery-task-123",
        }.get(field)

        with patch("src.api.routes.AsyncResult") as mock_async:
            mock_result = MagicMock()
            mock_result.state = "SUCCESS"
            mock_async.return_value = mock_result

            response = client.post("/jobs/test-id/interrupt")
            assert response.status_code == 200
            data = response.json()
            assert "cannot be interrupted" in data["message"]


class TestZipDownload:
    """The local backend has no presigned URLs, so downloads go through our own
    route and the archive is built on first request."""

    ZIP_NAME = "searchresults_job1.zip"
    FOLDER = "results/searchresults/job1"

    @pytest.fixture
    def run_folder(self, tmp_path):
        folder = tmp_path / self.FOLDER
        folder.mkdir(parents=True)
        (folder / "topics.jsonl").write_text('{"topic": "math"}\n', encoding="utf-8")
        (folder / "metrics.json").write_text("{}", encoding="utf-8")
        return folder

    def _use_local_storage(self, client, tmp_path, mock_redis_client, folder=FOLDER):
        from src.storage.local import LocalStorageBackend

        client.app.state.storage = LocalStorageBackend(base_dir=str(tmp_path))
        mock_redis_client.hget.side_effect = lambda key, field: {
            "storage_upload_folder": folder.encode() if folder else None,
            "storage_zip_filename": self.ZIP_NAME.encode(),
        }.get(field)

    def test_returns_our_own_download_route(self, client, tmp_path, mock_redis_client, run_folder):
        self._use_local_storage(client, tmp_path, mock_redis_client)

        response = client.get("/jobs/job1/download-zip")

        assert response.status_code == 200
        assert response.json()["download_url"].endswith("/jobs/job1/download-zip/archive")

    def test_builds_the_archive_on_demand(self, client, tmp_path, mock_redis_client, run_folder):
        self._use_local_storage(client, tmp_path, mock_redis_client)
        assert not (run_folder / self.ZIP_NAME).exists()

        client.get("/jobs/job1/download-zip")

        assert (run_folder / self.ZIP_NAME).is_file()

    def test_serves_the_archive_contents(self, client, tmp_path, mock_redis_client, run_folder):
        import io
        import zipfile

        self._use_local_storage(client, tmp_path, mock_redis_client)

        response = client.get("/jobs/job1/download-zip/archive")

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/zip"
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            assert sorted(archive.namelist()) == ["metrics.json", "topics.jsonl"]

    def test_archive_route_reuses_an_existing_zip(self, client, tmp_path, mock_redis_client, run_folder):
        self._use_local_storage(client, tmp_path, mock_redis_client)
        client.get("/jobs/job1/download-zip/archive")
        first = (run_folder / self.ZIP_NAME).stat().st_mtime_ns

        client.get("/jobs/job1/download-zip/archive")

        assert (run_folder / self.ZIP_NAME).stat().st_mtime_ns == first

    def test_missing_run_folder_is_404(self, client, tmp_path, mock_redis_client):
        self._use_local_storage(client, tmp_path, mock_redis_client)

        assert client.get("/jobs/job1/download-zip").status_code == 404
        assert client.get("/jobs/job1/download-zip/archive").status_code == 404

    def test_job_without_a_recorded_folder_is_404(self, client, tmp_path, mock_redis_client, run_folder):
        """Runs from before the folder was always recorded."""
        self._use_local_storage(client, tmp_path, mock_redis_client, folder=None)

        assert client.get("/jobs/job1/download-zip").status_code == 404

    def test_presigned_url_still_wins(self, client, mock_redis_client):
        mock_redis_client.hget.side_effect = lambda key, field: {
            "storage_upload_folder": b"bucket/prefix",
            "storage_zip_filename": self.ZIP_NAME.encode(),
        }.get(field)
        storage = MagicMock()
        storage.generate_presigned_url.return_value = "https://example.invalid/signed"
        client.app.state.storage = storage

        response = client.get("/jobs/job1/download-zip")

        assert response.status_code == 200
        assert response.json()["download_url"] == "https://example.invalid/signed"
