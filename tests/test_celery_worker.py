# Copyright 2025-2026 IBM Corporation
# SPDX-License-Identifier: Apache-2.0

"""Celery broker/backend resolution, which happens at import time.

Hardcoding localhost here made the API point at nothing under Compose: job
submission failed with a 500 while the worker, which does get the CELERY_* vars,
looked perfectly healthy. Every deployment that sets REDIS_URL means the broker
lives there too, so REDIS_URL is the fallback before the localhost default.

Each case runs in a subprocess. Reloading the module in-process replaces the
classes other test modules have already imported -- an earlier version of this
file did exactly that and broke tests/test_task_failure_status.py.
"""
import os
import subprocess
import sys

import pytest

PROBE = (
    "from src.api.celery_worker import celery_app;"
    "print(celery_app.conf.broker_url);"
    "print(celery_app.conf.result_backend)"
)

CELERY_VARS = ("REDIS_URL", "CELERY_BROKER_URL", "CELERY_RESULT_BACKEND")


def _resolve(**overrides):
    env = {k: v for k, v in os.environ.items() if k not in CELERY_VARS}
    env.update(overrides)
    # .env would otherwise supply values and mask what is being tested
    env["PYTHONPATH"] = os.getcwd()
    result = subprocess.run(
        [sys.executable, "-c", PROBE],
        capture_output=True, text=True, cwd=os.getcwd(), env=env, timeout=120,
    )
    assert result.returncode == 0, result.stderr
    broker, backend = result.stdout.strip().splitlines()[:2]
    return broker, backend


class TestBrokerResolution:
    def test_redis_url_is_used_when_celery_vars_are_absent(self):
        broker, backend = _resolve(REDIS_URL="redis://redis:6379/0")

        assert broker == "redis://redis:6379/0"
        assert backend == "redis://redis:6379/0"

    def test_explicit_celery_vars_win(self):
        broker, backend = _resolve(
            REDIS_URL="redis://ignored:6379/0",
            CELERY_BROKER_URL="redis://broker:6379/1",
            CELERY_RESULT_BACKEND="redis://backend:6379/2",
        )

        assert broker == "redis://broker:6379/1"
        assert backend == "redis://backend:6379/2"

    def test_falls_back_to_localhost_with_nothing_set(self):
        broker, _ = _resolve()

        assert broker == "redis://localhost:6379/0"


class TestTaskRegistration:
    def test_the_pipeline_task_is_registered(self):
        """A worker with no registered task accepts jobs and silently does nothing."""
        from src.api.celery_worker import celery_app
        import src.api.tasks  # noqa: F401 - registers the task

        assert "src.api.tasks.run_pipeline_task" in celery_app.tasks
