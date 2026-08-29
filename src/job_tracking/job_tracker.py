# Copyright 2025-2026 IBM Corporation
# SPDX-License-Identifier: Apache-2.0

import redis
from datetime import datetime, timezone
from typing import Optional
import json


def _redis_from_url(redis_url: str) -> redis.Redis:
    """Connect from a URL, delegating to redis-py's own parser.

    Hand-parsing only host/port/db silently dropped any username/password in the
    URL -- so `redis://:pw@host/0` connected *unauthenticated* -- and turned
    `rediss://` into a plaintext connection. Celery parses the same URL
    correctly with its own code, so on an authenticated or TLS Redis the worker
    connected while the tracker did not.
    """
    return redis.Redis.from_url(redis_url)


class JobTracker:
    def __init__(self, job_id: str, redis_client: Optional[redis.Redis] = None, redis_url: str = "redis://localhost:6379/0"):
        self.job_id = job_id
        self.redis = redis_client or _redis_from_url(redis_url)
        self.key = f"job:{self.job_id}"

    @classmethod
    def get_all_jobs(cls, redis_client: Optional[redis.Redis] = None, redis_url: str = "redis://localhost:6379/0") -> list[dict]:
        r = redis_client or _redis_from_url(redis_url)
        # scan_iter, not keys(): KEYS walks the entire keyspace in one blocking
        # call, which stalls every other client on a large database.
        job_keys = list(r.scan_iter(match="job:*", count=100))
        jobs = []

        for key in job_keys:
            job_id = key.decode().split(":")[1]
            tracker = cls(job_id, redis_client=r)
            job_info = tracker.get_job_info()

            public_fields = {
                "job_id": job_id,
                "mode": job_info.get("mode"),
                "input": job_info.get("input"),
                "status": job_info.get("status"),
                "progress": job_info.get("progress"),
                "created_at": job_info.get("created_at"),
                "error": job_info.get("error"),
            }

            jobs.append(public_fields)

        def sort_key(job):
            return job.get("created_at", "")

        return sorted(jobs, key=sort_key, reverse=True)

    def get_cached_logs(self) -> str:
        logs = self.redis.lrange(f"log_history:{self.job_id}", 0, -1)
        return "\n".join([line.decode("utf-8") for line in logs])

    def get_cached_metrics(self) -> list[dict]:
        metrics = self.redis.lrange(f"metrics_history:{self.job_id}", 0, -1)
        decoded = [metric.decode("utf-8") for metric in metrics]
        parsed = [json.loads(m) for m in decoded]
        return parsed

    def _current_utc_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def set_status(self, status: str):
        self.redis.hset(self.key, "status", status)
        self.redis.hset(self.key, "status_updated_at", self._current_utc_iso())
        log_line = f"[STATUS] {status}"
        self.redis.publish(f"logs:{self.job_id}", log_line)
        self.redis.rpush(f"log_history:{self.job_id}", log_line)

    def set_progress(self, message: str):
        self.redis.hset(self.key, "progress", message)
        self.redis.hset(self.key, "progress_updated_at", self._current_utc_iso())
        self.redis.publish(f"logs:{self.job_id}", message)
        self.redis.rpush(f"log_history:{self.job_id}", message)

    def set_metrics(self, metrics_json: str):
        self.redis.hset(self.key, "metrics", metrics_json)
        self.redis.hset(self.key, "metrics_updated_at", self._current_utc_iso())
        self.redis.publish(f"metrics:{self.job_id}", metrics_json)
        self.redis.rpush(f"metrics_history:{self.job_id}", metrics_json)

    def set_error(self, error_message: str):
        self.redis.hset(self.key, "error", error_message)
        self.redis.hset(self.key, "error_updated_at", self._current_utc_iso())
        log_line = f"[ERROR] {error_message}"
        self.redis.publish(f"logs:{self.job_id}", log_line)
        self.redis.rpush(f"log_history:{self.job_id}", log_line)

    def set_job_args(self, args: dict):
        arg_data = {k: str(v) for k, v in args.items() if v is not None}
        arg_data["created_at"] = self._current_utc_iso()
        self.redis.hset(self.key, mapping=arg_data)

    def set_all(self, status: str, progress: str, error: Optional[str] = None):
        mapping = {
            "status": status,
            "progress": progress,
            "status_updated_at": self._current_utc_iso(),
            "progress_updated_at": self._current_utc_iso(),
        }
        if error:
            mapping["error"] = error
            mapping["error_updated_at"] = self._current_utc_iso()
        self.redis.hset(self.key, mapping=mapping)

    def get_status(self) -> Optional[str]:
        return self.redis.hget(self.key, "status")

    def get_progress(self) -> Optional[str]:
        return self.redis.hget(self.key, "progress")

    def set_task_id(self, task_id: str):
        self.redis.hset(self.key, "task_id", task_id)

    def get_task_id(self) -> Optional[str]:
        task_id = self.redis.hget(self.key, "task_id")
        return task_id.decode() if isinstance(task_id, bytes) else task_id

    def get_error(self) -> Optional[str]:
        return self.redis.hget(self.key, "error")

    def get_job_info(self) -> dict:
        data = self.redis.hgetall(self.key)
        return {k.decode(): v.decode() for k, v in data.items()} if data else {}

    def set_storage_upload_folder(self, path: str):
        self.redis.hset(self.key, "storage_upload_folder", path)

    def get_storage_upload_folder(self) -> Optional[str]:
        folder = self.redis.hget(self.key, "storage_upload_folder")
        if not folder:
            return None
        return folder.decode() if isinstance(folder, bytes) else folder

    def set_storage_filename(self, file_type: str, filename: str):
        if file_type not in {"logs", "metrics", "zip", "results", "topics"}:
            raise ValueError("Invalid file_type. Must be one of: 'logs', 'metrics', 'zip', 'results', 'topics'.")

        key = f"storage_{file_type}_filename"
        self.redis.hset(self.key, key, filename)

    def get_storage_file_path(self, file_type: str) -> Optional[str]:
        if file_type not in {"logs", "metrics", "zip", "results", "topics"}:
            raise ValueError("Invalid file_type. Must be one of: 'logs', 'metrics', 'zip', 'results', 'topics'.")

        folder = self.redis.hget(self.key, "storage_upload_folder")
        filename = self.redis.hget(self.key, f"storage_{file_type}_filename")

        if folder and filename:
            folder_str = folder.decode() if isinstance(folder, bytes) else folder
            filename_str = filename.decode() if isinstance(filename, bytes) else filename
            return f"{folder_str}/{filename_str}"

        return None

    def clear_logs(self):
        self.redis.delete(f"log_history:{self.job_id}")

    def clear_metrics(self):
        self.redis.delete(f"metrics_history:{self.job_id}")

    def clear(self):
        self.redis.delete(self.key)
