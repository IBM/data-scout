import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from src.api import routes


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

        # Both construction paths return the same fake: JobTracker builds its
        # client via redis.Redis.from_url (so URL credentials and rediss:// are
        # honoured), while a direct redis.Redis(...) call must keep working too.
        mock_redis_cls.return_value = mock_redis_client
        mock_redis_cls.from_url.return_value = mock_redis_client
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
        # status, not just task_id: a job that really did finish has a terminal
        # tracked status, and that is what stops it being relabelled below.
        mock_redis_client.hget.side_effect = lambda key, field: {
            "task_id": b"celery-task-123",
            "status": b"completed",
        }.get(field)

        with patch("src.api.routes.AsyncResult") as mock_async:
            mock_result = MagicMock()
            mock_result.state = "SUCCESS"
            mock_async.return_value = mock_result

            response = client.post("/jobs/test-id/interrupt")
            assert response.status_code == 200
            data = response.json()
            assert "cannot be interrupted" in data["message"]

    def test_interrupt_does_not_relabel_a_job_that_already_finished(self, client, mock_redis_client):
        """A recorded outcome wins over Celery's view of the task."""
        mock_redis_client.hget.side_effect = lambda key, field: {
            "task_id": b"celery-task-123",
            "status": b"completed",
        }.get(field)

        with patch("src.api.routes.AsyncResult") as mock_async:
            mock_result = MagicMock()
            mock_result.state = "FAILURE"
            mock_async.return_value = mock_result

            response = client.post("/jobs/test-id/interrupt")
            assert response.json()["status"] == "completed"

        statuses = [
            c.args[2] for c in mock_redis_client.hset.call_args_list
            if len(c.args) > 2 and c.args[1] == "status"
        ]
        assert statuses == [], f"a finished job was relabelled to {statuses}"


class TestInterruptReconcilesStaleStatus:
    """A worker killed mid-task (container restart, SIGKILL, OOM) never writes a
    terminal status, so the job hash stays "running" while Celery reports the
    task as finished. The interrupt endpoint used to return 200 here without
    touching the hash, so the dashboard showed the job running forever and every
    repeated interrupt reported success and changed nothing."""

    def _interrupt_with(self, client, mock_redis_client, celery_state):
        mock_redis_client.hget.side_effect = lambda key, field: {
            "task_id": b"celery-task-123",
            "status": b"running",
        }.get(field)

        with patch("src.api.routes.AsyncResult") as mock_async:
            mock_result = MagicMock()
            mock_result.state = celery_state
            mock_async.return_value = mock_result

            response = client.post("/jobs/test-id/interrupt")

        written = [
            c.args[2] for c in mock_redis_client.hset.call_args_list
            if len(c.args) > 2 and c.args[1] == "status"
        ]
        return response, written

    def test_lost_worker_is_marked_failed(self, client, mock_redis_client):
        response, written = self._interrupt_with(client, mock_redis_client, "FAILURE")

        assert response.status_code == 200
        assert response.json()["status"] == "failed"
        assert "failed" in written, "job hash still says running"

    def test_revoked_task_is_marked_interrupted(self, client, mock_redis_client):
        response, written = self._interrupt_with(client, mock_redis_client, "REVOKED")

        assert response.json()["status"] == "interrupted"
        assert "interrupted" in written


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


class TestHealth:
    def test_health_is_ok(self, client):
        response = client.get("/health")

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_health_needs_no_api_key(self, client):
        """Container healthchecks cannot send one, so liveness must not require it."""
        client.app.state.api_key = "a-secret"
        try:
            response = client.get("/health")
        finally:
            client.app.state.api_key = ""

        assert response.status_code == 200


class TestErrorDetailsAreNotLeaked:
    """Route handlers used to interpolate exception text straight into `detail`,
    which can carry absolute paths and a Redis URL with credentials. It is now
    gated behind DEBUG_ERRORS."""

    SECRET = "redis://:sup3rs3cret@10.0.0.5:6379/0"

    def _failing_logs_request(self, client, mock_redis_client, debug):
        mock_redis_client.hget.side_effect = lambda key, field: {
            "storage_logs_filename": b"pipeline.log",
            "storage_upload_folder": b"results/searchresults/j1",
        }.get(field)
        client.app.state.storage.read_file.side_effect = RuntimeError(f"boom {self.SECRET}")

        with patch.object(routes._config, "debug_errors", debug):
            return client.get("/jobs/j1/logs/storage")

    def test_credentials_do_not_reach_the_client(self, client, mock_redis_client):
        response = self._failing_logs_request(client, mock_redis_client, debug=False)

        assert response.status_code == 500
        assert "sup3rs3cret" not in response.text
        assert "Failed to fetch log file" in response.text

    def test_debug_errors_restores_the_cause(self, client, mock_redis_client):
        response = self._failing_logs_request(client, mock_redis_client, debug=True)

        assert response.status_code == 500
        assert self.SECRET in response.text


class TestFileViewLimits:
    """`limit` was a bare int with no ceiling, so limit=10000000 returned the whole
    file in one response. offset was already validated with ge=0."""

    def _job(self, mock_redis_client, filename=b"searchresults.jsonl"):
        mock_redis_client.hget.side_effect = lambda key, field: {
            "storage_results_filename": filename,
            "storage_upload_folder": b"results/searchresults/j1",
        }.get(field)

    def test_absurd_limit_is_rejected(self, client, mock_redis_client):
        self._job(mock_redis_client)

        response = client.get("/jobs/j1/files/view?file_type=results&limit=10000000")

        assert response.status_code == 422

    def test_zero_limit_is_rejected(self, client, mock_redis_client):
        self._job(mock_redis_client)

        response = client.get("/jobs/j1/files/view?file_type=results&limit=0")

        assert response.status_code == 422

    def test_the_documented_ceiling_is_accepted(self, client, mock_redis_client):
        from src.api.routes import MAX_FILE_VIEW_LIMIT

        self._job(mock_redis_client)
        client.app.state.storage.read_file.return_value = b'{"a": 1}\n'

        response = client.get(
            f"/jobs/j1/files/view?file_type=results&limit={MAX_FILE_VIEW_LIMIT}"
        )

        assert response.status_code == 200

    def test_default_limit_still_works(self, client, mock_redis_client):
        self._job(mock_redis_client)
        client.app.state.storage.read_file.return_value = b'{"a": 1}\n{"b": 2}\n'

        response = client.get("/jobs/j1/files/view?file_type=results")

        assert response.status_code == 200
        assert len(response.json()["rows"]) == 2

    def test_negative_offset_still_rejected(self, client, mock_redis_client):
        self._job(mock_redis_client)

        response = client.get("/jobs/j1/files/view?file_type=results&offset=-1")

        assert response.status_code == 422


class _RecordingTable:
    """Records whether the route sliced before converting rows."""

    def __init__(self, table):
        self._table = table
        self.sliced_with = None
        self.converted_whole_table = False

    def slice(self, offset, length):
        self.sliced_with = (offset, length)
        return self._table.slice(offset, length)

    def to_pylist(self):
        self.converted_whole_table = True
        return self._table.to_pylist()

    def __getattr__(self, name):
        # everything else (schema, num_rows, ...) passes through to the real table
        return getattr(self._table, name)


class TestParquetPaginationDoesNotMaterialiseEverything:
    """`to_pylist()` on the whole table converted every row to Python objects
    before pagination, so even limit=50 paid for the entire file."""

    def test_parquet_is_sliced_before_conversion(self, client, mock_redis_client):
        import io as _io

        import pyarrow as pa
        import pyarrow.parquet as pq

        table = pa.table({"n": list(range(500))})
        buf = _io.BytesIO()
        pq.write_table(table, buf)

        mock_redis_client.hget.side_effect = lambda key, field: {
            "storage_results_filename": b"searchresults.parquet",
            "storage_upload_folder": b"results/searchresults/j1",
        }.get(field)
        client.app.state.storage.read_file.return_value = buf.getvalue()

        recorder = _RecordingTable(table)
        with patch("pyarrow.parquet.read_table", return_value=recorder):
            response = client.get("/jobs/j1/files/view?file_type=results&offset=10&limit=5")

        assert response.status_code == 200
        assert [r["n"] for r in response.json()["rows"]] == [10, 11, 12, 13, 14]
        assert recorder.sliced_with == (10, 5), "the table was not sliced before conversion"
        assert not recorder.converted_whole_table, "every row was materialised anyway"
