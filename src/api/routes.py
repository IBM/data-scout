from fastapi import APIRouter, HTTPException, Request, Query
from fastapi.responses import FileResponse
from pathlib import Path
from typing import Optional
from uuid import uuid4
from src.job_tracking.job_tracker import JobTracker
from src.models import UserArgs
from .tasks import run_pipeline_task
from celery.result import AsyncResult
from kombu.exceptions import OperationalError
from redis.exceptions import ConnectionError as RedisConnectionError
from src.api.celery_worker import celery_app
from fastapi import WebSocket, WebSocketDisconnect
from src.config import SearchConfig
import asyncio
import redis.asyncio as aioredis
from src.processing.utils import get_default_logger
from src.processing.file_ops import zip_folder
import json
import logging

router = APIRouter()
# WebSocket routes live on a separate router: the HTTP router's auth dependency
# is built on APIKeyHeader/Request, which cannot resolve on a WebSocket scope.
ws_router = APIRouter()
logger = logging.getLogger("pipeline_logger")
_config = SearchConfig()


def _tracker(job_id: str) -> JobTracker:
    return JobTracker(job_id, redis_url=_config.redis_url)


# A job whose tracked status is one of these has already been accounted for and
# must not be relabelled from Celery's view of the task.
_TERMINAL_STATUSES = {"completed", "failed", "interrupted"}

# How a terminal Celery task state reads as a job status. REVOKED is what a
# successful interrupt produces; FAILURE covers both a genuine exception and a
# worker killed mid-task (WorkerLostError).
_CELERY_STATE_TO_STATUS = {
    "SUCCESS": "completed",
    "FAILURE": "failed",
    "REVOKED": "interrupted",
}

@router.get("/jobs/{job_id}")
def get_job_details(job_id: str):
    tracker = _tracker(job_id)
    return tracker.get_job_info()

@router.post("/jobs/")
def submit_job(args: UserArgs):
    job_id = uuid4().hex
    tracker = _tracker(job_id)
    tracker.set_job_args(args.model_dump())

    try:
        celery_task = run_pipeline_task.delay(job_id, args.model_dump())
    except (OperationalError, RedisConnectionError, RuntimeError) as e:
        # An unreachable broker/result backend otherwise surfaces as an
        # unhandled 500 after a long retry loop, which tells the operator
        # nothing about the actual cause.
        tracker.set_all(status="failed", progress="Could not queue job")
        raise HTTPException(
            status_code=503,
            detail=f"Task queue unavailable, job was not queued: {e}",
        )

    tracker.set_all(status="queued", progress="Job queued")
    tracker.redis.hset(tracker.key, "task_id", celery_task.id)

    return {
        "job_id": job_id,
        "status": "queued"
    }

@router.get("/jobs/")
def list_all_jobs():
    return {"jobs": JobTracker.get_all_jobs(redis_url=_config.redis_url)}

@router.get("/jobs/{job_id}/progress")
def get_progress(job_id: str):

    tracker = _tracker(job_id)

    status = tracker.get_status()
    progress = tracker.get_progress()

    if not status:
        return {"job_id": job_id, "status": "not found", "progress": None}

    return {
        "job_id": job_id,
        "status": status.decode() if isinstance(status, bytes) else status,
        "progress": progress.decode() if isinstance(progress, bytes) else progress,
    }

@router.get("/jobs/{job_id}/logs/storage")
def get_storage_logs(job_id: str, request: Request):
    tracker = _tracker(job_id)
    log_path = tracker.get_storage_file_path("logs")

    if not log_path:
        raise HTTPException(status_code=404, detail="Storage log file path not found for job.")

    try:
        storage = request.app.state.storage
        log_bytes = storage.read_file(log_path)
        log_contents = log_bytes.decode("utf-8")

        if "\\n" in log_contents and "\n" not in log_contents:
            log_contents = log_contents.replace("\\n", "\n")

    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Log file not found in storage.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch log file: {str(e)}")

    return {
        "job_id": job_id,
        "logs": log_contents
    }

@router.get("/jobs/{job_id}/logs/redis")
async def get_redis_cached_logs(job_id: str):
    tracker = _tracker(job_id)
    logs = tracker.get_cached_logs()
    return {"job_id": job_id, "logs": logs}

@ws_router.websocket("/ws/jobs/{job_id}/logs")
async def websocket_job_logs(websocket: WebSocket, job_id: str):
    await websocket.accept()

    redis_url = websocket.app.state.redis_url
    try:
        redis_client = aioredis.from_url(redis_url)
        pubsub = redis_client.pubsub()
        await pubsub.subscribe(f"logs:{job_id}")
    except Exception as e:
        logger.error(f"Failed to connect to Redis for job {job_id} logs: {e}")
        await websocket.close(code=1011)
        return

    try:
        while True:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)

            if message and message["type"] == "message":
                log_line = message["data"].decode()
                await websocket.send_text(log_line)

            await asyncio.sleep(0.1)

    except WebSocketDisconnect:
        logger.debug(f"Client disconnected from job {job_id} logs")
    except Exception as e:
        logger.error(f"Redis error in logs websocket for job {job_id}: {e}")
    finally:
        await pubsub.unsubscribe(f"logs:{job_id}")
        await pubsub.close()
        await redis_client.close()

@router.get("/jobs/{job_id}/metrics/redis")
async def get_redis_cached_metrics(job_id: str):
    tracker = _tracker(job_id)
    metrics = tracker.get_cached_metrics()
    return {"job_id": job_id, "metrics": metrics}

@router.get("/jobs/{job_id}/metrics/storage")
def get_storage_metrics(job_id: str, request: Request):
    tracker = _tracker(job_id)
    metrics_path = tracker.get_storage_file_path("metrics")

    if not metrics_path:
        raise HTTPException(status_code=404, detail="Storage metrics file path not found for job.")

    try:
        storage = request.app.state.storage
        metrics_bytes = storage.read_file(metrics_path)
        metrics_content = metrics_bytes.decode("utf-8")

    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Metrics file not found in storage.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch metrics file: {str(e)}")

    return {
        "job_id": job_id,
        "metrics": metrics_content
    }

@ws_router.websocket("/ws/jobs/{job_id}/metrics")
async def websocket_job_metrics(websocket: WebSocket, job_id: str):
    await websocket.accept()

    redis_url = websocket.app.state.redis_url
    try:
        redis_client = aioredis.from_url(redis_url)
        pubsub = redis_client.pubsub()
        await pubsub.subscribe(f"metrics:{job_id}")
    except Exception as e:
        logger.error(f"Failed to connect to Redis for job {job_id} metrics: {e}")
        await websocket.close(code=1011)
        return

    try:
        while True:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)

            if message and message["type"] == "message":
                metrics_json = message["data"].decode()
                await websocket.send_text(metrics_json)

            await asyncio.sleep(0.1)

    except WebSocketDisconnect:
        logger.debug(f"Client disconnected from metrics websocket for job {job_id}")
    except Exception as e:
        logger.error(f"Redis error in metrics websocket for job {job_id}: {e}")
    finally:
        await pubsub.unsubscribe(f"metrics:{job_id}")
        await pubsub.close()
        await redis_client.close()

def _local_zip(tracker, storage) -> Optional[Path]:
    """Path to a run's zip on a filesystem-backed store, building it if needed.

    The pipeline only zips a run when it uploads one, so for local storage the
    archive is created here on first request instead. Returns None when the
    backend keeps files off-host (presigned download applies) or when the run
    folder is gone.
    """
    resolve = getattr(storage, "local_path", None)
    if resolve is None:
        return None

    zip_rel = tracker.get_storage_file_path("zip")
    folder_rel = tracker.get_storage_upload_folder()
    if not zip_rel or not folder_rel:
        return None

    zip_abs = resolve(zip_rel)
    if zip_abs is None:
        return None
    if zip_abs.is_file():
        return zip_abs

    folder_abs = resolve(folder_rel)
    if folder_abs is None or not folder_abs.is_dir():
        return None

    # zip_folder skips the archive it is writing, so the run folder can be both
    # source and destination.
    created = zip_folder(str(folder_abs), str(folder_abs), zip_abs.name)
    return Path(created) if created else None


@router.get("/jobs/{job_id}/download-zip")
def get_zip_presigned_url(job_id: str, request: Request):
    tracker = _tracker(job_id)

    zip_path = tracker.get_storage_file_path("zip")
    if not zip_path:
        raise HTTPException(status_code=404, detail="Zip file path not found for job.")

    try:
        storage = request.app.state.storage
        presigned_url = storage.generate_presigned_url(zip_path)

        if presigned_url:
            return {"job_id": job_id, "download_url": presigned_url}

        # Local storage has no presigned URLs, so hand back our own download
        # route. Built absolute because the browser opens it directly, and the
        # UI is served from a different origin than the API.
        if _local_zip(tracker, storage) is not None:
            return {
                "job_id": job_id,
                "download_url": str(request.url_for("download_zip_archive", job_id=job_id)),
            }

        raise HTTPException(status_code=404, detail="Zip file not available for this job.")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to prepare zip download: {str(e)}")


@router.get("/jobs/{job_id}/download-zip/archive", name="download_zip_archive")
def download_zip_archive(job_id: str, request: Request):
    tracker = _tracker(job_id)
    storage = request.app.state.storage

    try:
        zip_abs = _local_zip(tracker, storage)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to build zip archive: {str(e)}")

    if zip_abs is None:
        raise HTTPException(status_code=404, detail="Zip file not available for this job.")

    return FileResponse(
        path=zip_abs,
        media_type="application/zip",
        filename=zip_abs.name,
    )

@router.get("/jobs/{job_id}/files")
def list_available_files(job_id: str, request: Request):
    tracker = _tracker(job_id)
    storage = request.app.state.storage

    available = []
    missing = []

    for file_type in ["topics", "results"]:
        full_path = tracker.get_storage_file_path(file_type)

        if not full_path:
            missing.append(file_type)
            continue

        try:
            file_info = storage.get_file_info(full_path)

            if not file_info:
                missing.append(file_type)
                continue

            available.append({
                "file_type": file_type,
                "filename": full_path.split("/")[-1],
                "path": full_path,
                "size_bytes": file_info["size_bytes"],
                "last_modified": file_info.get("last_modified")
            })
        except Exception as e:
            logger.error(f"Error reading file info for {full_path}: {e}")
            missing.append(file_type)

    return {
        "job_id": job_id,
        "available": available,
        "missing": missing
    }

@router.get("/jobs/{job_id}/files/view")
def view_file_content(
    job_id: str,
    file_type: str = Query(..., pattern="^(topics|results)$"),
    offset: int = Query(0, ge=0),
    limit: int = 50,
    request: Request = None,
):
    tracker = _tracker(job_id)
    path = tracker.get_storage_file_path(file_type)

    if not path:
        raise HTTPException(status_code=404, detail=f"{file_type} file not available for this job.")

    storage = request.app.state.storage

    try:
        file_bytes = storage.read_file(path)

        if path.endswith(".jsonl"):
            file_content = file_bytes.decode("utf-8", errors="replace")
            lines = file_content.strip().splitlines()
            paginated_lines = lines[offset:offset + limit]

            all_lines = []
            for i, line in enumerate(paginated_lines, start=offset):
                try:
                    parsed = json.loads(line)
                    all_lines.append(parsed)
                except json.JSONDecodeError:
                    all_lines.append({
                        "_error": f"Invalid JSON at line {i}",
                        "_raw": line
                    })

            return {
                "job_id": job_id,
                "file_type": file_type,
                "offset": offset,
                "limit": limit,
                "rows": all_lines,
            }

        elif path.endswith(".parquet"):
            import pyarrow.parquet as pq
            from io import BytesIO

            try:
                table = pq.read_table(BytesIO(file_bytes))
                all_rows = table.to_pylist()
                paginated_rows = all_rows[offset:offset + limit]

                return {
                    "job_id": job_id,
                    "file_type": file_type,
                    "offset": offset,
                    "limit": limit,
                    "rows": paginated_rows,
                    "schema": [field.name for field in table.schema]
                }

            except Exception as parquet_err:
                raise HTTPException(status_code=500, detail=f"Failed to parse parquet file: {str(parquet_err)}")

        else:
            raise HTTPException(status_code=400, detail="Unsupported file format.")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read {file_type} file: {str(e)}")

@router.post("/jobs/{job_id}/interrupt")
def interrupt_job(job_id: str):
    tracker = _tracker(job_id)
    app_logger = get_default_logger()

    task_id = tracker.redis.hget(tracker.key, "task_id")
    if not task_id:
        raise HTTPException(status_code=404, detail="Task ID not found for this job.")

    task_id = task_id.decode() if isinstance(task_id, bytes) else task_id
    result = AsyncResult(task_id, app=celery_app)

    if result.state in ["PENDING", "STARTED"]:
        app_logger.info(f"Interrupt requested for job {job_id} (task_id={task_id})")
        result.revoke(terminate=True, signal="SIGKILL")

        tracker.set_status("interrupted")
        tracker.set_progress("Job was interrupted by user.")

        return {"job_id": job_id, "status": "interrupted", "message": "Job interrupt signal sent successfully."}
    # The task is in a terminal Celery state, so there is nothing left to revoke.
    # The tracked status can still say "running" though: nothing writes a
    # terminal status when a worker dies mid-task (container restart, SIGKILL,
    # OOM), so the job hash keeps the status it had when the worker vanished.
    # This branch used to return 200 without touching the hash, which left the
    # dashboard showing the job as running forever while every repeated
    # interrupt reported success and changed nothing. Reconcile instead.
    tracked_status = tracker.redis.hget(tracker.key, "status")
    tracked_status = tracked_status.decode() if isinstance(tracked_status, bytes) else tracked_status
    reconciled = _CELERY_STATE_TO_STATUS.get(result.state)

    if reconciled and tracked_status not in _TERMINAL_STATUSES:
        app_logger.info(
            f"Job {job_id} is tracked as '{tracked_status}' but task {task_id} is "
            f"{result.state}; reconciling to '{reconciled}'"
        )
        tracker.set_status(reconciled)
        tracker.set_progress(
            f"Job stopped without recording an outcome (task state {result.state}); "
            f"marked as {reconciled}."
        )
        return {
            "job_id": job_id,
            "status": reconciled,
            "message": (
                f"Job was no longer running (task state {result.state}). "
                f"Its status was stale and has been corrected to '{reconciled}'."
            ),
        }

    return {
        "job_id": job_id,
        "status": tracked_status or result.state.lower(),
        "message": f"Job is already in state '{result.state}', cannot be interrupted."
    }
