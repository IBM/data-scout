"""A worker child that dies outright leaves no frame for the task's own
`except` handlers, so the job hash kept the "running" it was given at the start
and the dashboard showed the job running forever. JobStatusTask.on_failure runs
in the MainProcess, which is where billiard raises WorkerLostError, so it still
records an outcome in those cases."""

from unittest.mock import MagicMock, patch

from billiard.exceptions import WorkerLostError

from src.api.tasks import JobStatusTask


def _on_failure(exc, args=("job-1",), kwargs=None, current_status=b"running"):
    """Invoke the handler with a stubbed tracker and report what it wrote."""
    tracker = MagicMock()
    tracker.redis.hget.return_value = current_status

    with patch("src.api.tasks.JobTracker", return_value=tracker), \
         patch("src.api.tasks.SearchConfig"):
        JobStatusTask().on_failure(exc, "task-1", args, kwargs or {}, None)

    return tracker


class TestLostWorkerIsRecorded:
    def test_segfaulted_worker_marks_the_job_failed(self):
        tracker = _on_failure(WorkerLostError("Worker exited prematurely: signal 11 (SIGSEGV) Job: 1."))

        tracker.set_status.assert_called_once_with("failed")

    def test_the_reason_is_kept_for_the_user(self):
        tracker = _on_failure(WorkerLostError("signal 11 (SIGSEGV)"))

        assert "SIGSEGV" in tracker.set_error.call_args[0][0]
        assert "SIGSEGV" in tracker.set_progress.call_args[0][0]

    def test_job_id_is_read_from_kwargs_when_called_that_way(self):
        tracker = _on_failure(WorkerLostError("x"), args=(), kwargs={"job_id": "job-2"})

        tracker.set_status.assert_called_once_with("failed")


class TestOutcomeAlreadyRecorded:
    """The task body handles every exception it can see and writes the status
    itself; on_failure must not overwrite that."""

    def test_completed_job_is_left_alone(self):
        tracker = _on_failure(WorkerLostError("x"), current_status=b"completed")

        tracker.set_status.assert_not_called()

    def test_failed_job_is_not_rewritten(self):
        tracker = _on_failure(WorkerLostError("x"), current_status=b"failed")

        tracker.set_status.assert_not_called()

    def test_interrupted_job_is_not_downgraded_to_failed(self):
        tracker = _on_failure(WorkerLostError("x"), current_status=b"interrupted")

        tracker.set_status.assert_not_called()


class TestBookkeepingNeverMasksTheFailure:
    def test_missing_job_id_does_not_raise(self):
        tracker = MagicMock()
        with patch("src.api.tasks.JobTracker", return_value=tracker), \
             patch("src.api.tasks.SearchConfig"):
            JobStatusTask().on_failure(WorkerLostError("x"), "task-1", (), {}, None)

        tracker.set_status.assert_not_called()

    def test_redis_failure_is_swallowed(self):
        with patch("src.api.tasks.JobTracker", side_effect=ConnectionError("redis down")), \
             patch("src.api.tasks.SearchConfig"):
            JobStatusTask().on_failure(WorkerLostError("x"), "task-1", ("job-1",), {}, None)


class TestTaskIsWiredToTheHandler:
    def test_run_pipeline_task_uses_the_status_recording_base(self):
        """A plain @celery_app.task would silently lose all of the above."""
        from src.api.tasks import run_pipeline_task

        assert isinstance(run_pipeline_task, JobStatusTask)
