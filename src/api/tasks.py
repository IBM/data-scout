from .celery_worker import celery_app
from src.models import UserArgs
from src.pipeline.run_wrapper import run_pipeline_from_args_dict
from src.processing.utils import get_default_logger
from src.job_tracking.job_tracker import JobTracker
from src.config import SearchConfig
import json
from src.pipeline.pipeline import GracefulInterruptException

@celery_app.task(bind=True)
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

