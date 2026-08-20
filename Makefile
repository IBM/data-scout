# Constants
CELERY_APP=src.api.celery_worker.celery_app
API_MODULE=src.api.main:app
HOST=0.0.0.0
PORT=8000

.PHONY: backend redis celery api stop build frontend clean

# Start all backend services (Redis, Celery, FastAPI)
backend: redis celery api
	@echo "All services started."

redis:
	@echo "Starting Redis server..."
	redis-server --daemonize yes

celery:
	@echo "Starting Celery worker..."
	celery -A $(CELERY_APP) worker --loglevel=info --pool=prefork &

api:
	@echo "Starting FastAPI app with Uvicorn..."
	uvicorn $(API_MODULE) --host $(HOST) --port $(PORT) &

stop:
	@echo "Stopping services..."
	@pkill -f "celery -A" || true
	@pkill -f "uvicorn" || true
	@redis-cli shutdown || true

build:
	cd frontend && npm install && npm run build

frontend:
	cd frontend && npm start

clean:
	@echo "Cleaning up..."
	@pkill -f 'celery' || true
	@pkill -f 'uvicorn' || true
	@redis-cli shutdown || true
