from fastapi import APIRouter, HTTPException, Request, Query
from uuid import uuid4
from src.job_tracking.job_tracker import JobTracker
from src.models import UserArgs
from .tasks import run_pipeline_task
from celery.result import AsyncResult
from src.api.celery_worker import celery_app
from fastapi import WebSocket, WebSocketDisconnect
from src.config import SearchConfig
import asyncio
import redis.asyncio as aioredis
from src.processing.utils import get_default_logger
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

@router.get("/jobs/{job_id}")
def get_job_details(job_id: str):
    tracker = _tracker(job_id)
    return tracker.get_job_info()

@router.post("/jobs/")
def submit_job(args: UserArgs):
    job_id = uuid4().hex
    tracker = _tracker(job_id)
    tracker.set_job_args(args.model_dump())

    celery_task = run_pipeline_task.delay(job_id, args.model_dump())

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

@router.get("/jobs/{job_id}/download-zip")
def get_zip_presigned_url(job_id: str, request: Request):
    tracker = _tracker(job_id)

    zip_path = tracker.get_storage_file_path("zip")
    if not zip_path:
        raise HTTPException(status_code=404, detail="Zip file path not found for job.")

    try:
        storage = request.app.state.storage
        presigned_url = storage.generate_presigned_url(zip_path)

        if not presigned_url:
            raise HTTPException(status_code=501, detail="Presigned URLs not supported by current storage backend.")

        return {"job_id": job_id, "download_url": presigned_url}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate presigned URL: {str(e)}")

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
    else:
        return {
            "job_id": job_id,
            "status": result.state.lower(),
            "message": f"Job is already in state '{result.state}', cannot be interrupted."
        }
