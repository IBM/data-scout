#!/bin/bash

cd "$(dirname "$0")" # Ensure we're in the script's directory

echo "Starting Redis server..."
redis-server --daemonize yes

echo "Starting Celery worker..."
cd src
PYTHONPATH=src poetry run celery -A api.celery_worker.celery_app worker --loglevel=info --pool=prefork &
CELERY_PID=$!
cd ..

echo "Starting FastAPI API (uvicorn)..."
poetry run uvicorn api.main:app --app-dir src --host 0.0.0.0 --port 8000 &
API_PID=$!

function cleanup {
    echo "Stopping services..."
    kill $CELERY_PID
    kill $API_PID
    redis-cli shutdown
    exit 0
}

trap cleanup SIGINT SIGTERM

echo "All services started. Press Ctrl+C to stop."
wait $CELERY_PID $API_PID
