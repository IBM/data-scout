from celery import Celery
import os

# Fall back to REDIS_URL before the localhost default: every deployment that
# sets REDIS_URL (Docker Compose, Kubernetes) means "the broker lives there
# too". Hardcoding localhost made the API silently point at nothing and fail
# job submission with a 500 while the worker, which does get the CELERY_* vars,
# looked perfectly healthy.
_redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "pipeline_worker",
    broker=os.getenv("CELERY_BROKER_URL", _redis_url),
    backend=os.getenv("CELERY_RESULT_BACKEND", _redis_url)
)

from src.api import tasks
