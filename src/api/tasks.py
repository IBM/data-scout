from .celery_worker import celery_app
from src.models import UserArgs
from src.pipeline.run_wrapper import run_pipeline_from_args_dict
from src.processing.utils import get_default_logger
from src.job_tracking.job_tracker import JobTracker
from src.config import SearchConfig
import json
from src.pipeline.pipeline import GracefulInterruptException

class JobStatusTask(celery_app.Task):
    """Records a terminal job status even when the task body never got to.

    The handlers inside run_pipeline_task run *in the child process*, so they
    cover exceptions but not the child dying outright -- a SIGSEGV in a native
    extension (libxml2 via trafilatura), an OOM kill, or a stopped container
    leaves no Python frame to run them in. The job hash then keeps the "running"
    it was given at the start, so the dashboard shows the job running forever
    and there is no worker left to correct it.

    on_failure runs in the MainProcess, which outlives the child and is where
    billiard raises WorkerLostError, so it still fires in exactly those cases.
    """

    _TERMINAL_STATUSES = {"completed", "failed", "interrupted"}

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        logger = get_default_logger()
        job_id = kwargs.get("job_id") or (args[0] if args else None)
        if not job_id:
            logger.error(f"Task {task_id} failed with no job_id to record it against: {exc}")
            return

        try:
            tracker = JobTracker(job_id, redis_url=SearchConfig().redis_url)
            current = tracker.redis.hget(tracker.key, "status")
            current = current.decode() if isinstance(current, bytes) else current

            # The task body already recorded an outcome for every failure it could
            # catch; only fill in the ones it could not.
            if current in self._TERMINAL_STATUSES:
                return

            reason = f"{type(exc).__name__}: {exc}"
            logger.error(f"Job {job_id} died without recording an outcome ({reason}); marking failed")
            tracker.set_status("failed")
            tracker.set_progress(f"Job stopped unexpectedly and did not finish ({reason}).")
            tracker.set_error(reason)
        except Exception as bookkeeping_error:  # pragma: no cover - defensive
            # Never let status bookkeeping mask the original failure.
            logger.error(f"Could not record failure for job {job_id}: {bookkeeping_error}")


@celery_app.task(bind=True, base=JobStatusTask)
def run_pipeline_task(self, job_id: str, args_dict: dict):
    logger = get_default_logger()
    config = SearchConfig()
    tracker = JobTracker(job_id, redis_url=config.redis_url)

    try:
        tracker.set_status("running")
        tracker.set_progress("Starting pipeline...")

        def progress_callback(message: str):
            logger.info(f"[{job_id} progress] {message}")
            tracker.set_progress(message)

        def metrics_callback(metrics: dict):
            metrics_json = json.dumps(metrics)
            logger.info(f"[{job_id} metrics] {metrics_json}")
            tracker.set_metrics(metrics_json)

        run_pipeline_from_args_dict(
            args_dict,
            run_id=job_id,
            progress_callback=progress_callback,
            metrics_callback=metrics_callback,
            tracker=tracker
        )

        tracker.set_status("completed")
        tracker.set_progress("Job completed.")
        logger.info("Job completed.")

        return {"status": "completed", "job_id": job_id}

    except GracefulInterruptException as e:
        logger.warning(f"Job interrupted: {e}")
        tracker.set_status("failed")
        tracker.set_progress("Job was interrupted and stopped.")
        tracker.set_error(str(e))
        return {"status": "interrupted", "job_id": job_id, "error": str(e)}

    except Exception as e:
        error_message = f"Job failed: {e}"
        logger.error(error_message)
        tracker.set_status("failed")
        tracker.set_progress(error_message)
        tracker.set_error(str(e))
        return {"status": "failed", "job_id": job_id, "error": str(e)}

