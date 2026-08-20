import pytest
import json
from unittest.mock import MagicMock, patch
from src.job_tracking.job_tracker import JobTracker


@pytest.fixture
def mock_redis():
    return MagicMock()


@pytest.fixture
def tracker(mock_redis):
    return JobTracker("test-job-123", redis_client=mock_redis)


class TestJobTrackerInit:
    def test_stores_job_id(self, tracker):
        assert tracker.job_id == "test-job-123"
        assert tracker.key == "job:test-job-123"

    def test_uses_provided_redis(self, mock_redis, tracker):
        assert tracker.redis is mock_redis


class TestSetStatus:
    def test_sets_status_in_redis(self, tracker, mock_redis):
        tracker.set_status("running")

        calls = mock_redis.hset.call_args_list
        status_call = [c for c in calls if c[0] == (tracker.key, "status", "running")]
        assert len(status_call) == 1

    def test_publishes_log(self, tracker, mock_redis):
        tracker.set_status("completed")
        mock_redis.publish.assert_called()
        publish_args = mock_redis.publish.call_args[0]
        assert publish_args[0] == "logs:test-job-123"
        assert "[STATUS] completed" in publish_args[1]

    def test_appends_to_log_history(self, tracker, mock_redis):
        tracker.set_status("failed")
        mock_redis.rpush.assert_called()


class TestSetProgress:
    def test_sets_progress(self, tracker, mock_redis):
        tracker.set_progress("Step 2 of 5")
        mock_redis.hset.assert_any_call(tracker.key, "progress", "Step 2 of 5")

    def test_publishes_and_caches(self, tracker, mock_redis):
        tracker.set_progress("Working...")
        mock_redis.publish.assert_called()
        mock_redis.rpush.assert_called()


class TestSetMetrics:
    def test_stores_metrics(self, tracker, mock_redis):
        metrics = json.dumps({"queries": 10})
        tracker.set_metrics(metrics)
        mock_redis.hset.assert_any_call(tracker.key, "metrics", metrics)

    def test_publishes_metrics(self, tracker, mock_redis):
        metrics = json.dumps({"queries": 10})
        tracker.set_metrics(metrics)
        mock_redis.publish.assert_called_with("metrics:test-job-123", metrics)


class TestSetError:
    def test_stores_error(self, tracker, mock_redis):
        tracker.set_error("Something broke")
        mock_redis.hset.assert_any_call(tracker.key, "error", "Something broke")


class TestSetJobArgs:
    def test_stores_flattened_args(self, tracker, mock_redis):
        args = {"mode": "query", "input": "test", "recursion_depth": 2, "empty": None}
        tracker.set_job_args(args)

        call_args = mock_redis.hset.call_args
        mapping = call_args[1]["mapping"]
        assert mapping["mode"] == "query"
        assert mapping["input"] == "test"
        assert mapping["recursion_depth"] == "2"
        assert "empty" not in mapping
        assert "created_at" in mapping


class TestGetStatus:
    def test_returns_status(self, tracker, mock_redis):
        mock_redis.hget.return_value = b"running"
        result = tracker.get_status()
        assert result == b"running"

    def test_returns_none_when_missing(self, tracker, mock_redis):
        mock_redis.hget.return_value = None
        assert tracker.get_status() is None


class TestGetJobInfo:
    def test_decodes_all_fields(self, tracker, mock_redis):
        mock_redis.hgetall.return_value = {
            b"status": b"completed",
            b"mode": b"query",
            b"input": b"test topic",
        }
        info = tracker.get_job_info()
        assert info == {"status": "completed", "mode": "query", "input": "test topic"}

    def test_empty_hash(self, tracker, mock_redis):
        mock_redis.hgetall.return_value = {}
        assert tracker.get_job_info() == {}


class TestStorageFilePaths:
    def test_set_and_get_storage_upload_folder(self, tracker, mock_redis):
        tracker.set_storage_upload_folder("/bucket/path")
        mock_redis.hset.assert_called_with(tracker.key, "storage_upload_folder", "/bucket/path")

    def test_set_storage_filename(self, tracker, mock_redis):
        tracker.set_storage_filename("logs", "pipeline.log")
        mock_redis.hset.assert_called_with(tracker.key, "storage_logs_filename", "pipeline.log")

    def test_set_storage_filename_invalid_type(self, tracker):
        with pytest.raises(ValueError):
            tracker.set_storage_filename("invalid_type", "file.txt")

    def test_get_storage_file_path(self, tracker, mock_redis):
        mock_redis.hget.side_effect = lambda key, field: {
            "storage_upload_folder": b"bucket/folder",
            "storage_logs_filename": b"pipeline.log",
        }.get(field)

        path = tracker.get_storage_file_path("logs")
        assert path == "bucket/folder/pipeline.log"

    def test_get_storage_file_path_missing(self, tracker, mock_redis):
        mock_redis.hget.return_value = None
        assert tracker.get_storage_file_path("logs") is None


class TestGetAllJobs:
    def test_lists_and_sorts(self, mock_redis):
        mock_redis.keys.return_value = [b"job:aaa", b"job:bbb"]
        mock_redis.hgetall.side_effect = [
            {b"mode": b"query", b"input": b"first", b"status": b"completed", b"created_at": b"2024-01-01"},
            {b"mode": b"topic", b"input": b"second", b"status": b"running", b"created_at": b"2024-01-02"},
        ]

        jobs = JobTracker.get_all_jobs(redis_client=mock_redis)
        assert len(jobs) == 2
        assert jobs[0]["created_at"] == "2024-01-02"
        assert jobs[1]["created_at"] == "2024-01-01"


class TestClearMethods:
    def test_clear_logs(self, tracker, mock_redis):
        tracker.clear_logs()
        mock_redis.delete.assert_called_with("log_history:test-job-123")

    def test_clear_metrics(self, tracker, mock_redis):
        tracker.clear_metrics()
        mock_redis.delete.assert_called_with("metrics_history:test-job-123")

    def test_clear_all(self, tracker, mock_redis):
        tracker.clear()
        mock_redis.delete.assert_called_with(tracker.key)


class TestGetCachedLogs:
    def test_returns_joined_logs(self, tracker, mock_redis):
        mock_redis.lrange.return_value = [b"line1", b"line2", b"line3"]
        result = tracker.get_cached_logs()
        assert result == "line1\nline2\nline3"


class TestGetCachedMetrics:
    def test_returns_parsed_metrics(self, tracker, mock_redis):
        mock_redis.lrange.return_value = [
            b'{"queries": 10}',
            b'{"queries": 20}',
        ]
        result = tracker.get_cached_metrics()
        assert len(result) == 2
        assert result[0] == {"queries": 10}
        assert result[1] == {"queries": 20}
