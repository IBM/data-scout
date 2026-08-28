# Constants
CELERY_APP=src.api.celery_worker.celery_app
API_MODULE=src.api.main:app
HOST=0.0.0.0
PORT=8000
# Written only when this Makefile is the thing that started Redis, so teardown
# never shuts down a Redis it does not own (yours may hold other data).
REDIS_MARKER=.dev-redis-started

.PHONY: dev backend redis celery api stop stop-redis build frontend clean

# Run the backend in the foreground: one Ctrl+C stops everything it started.
# Prefer this over `make backend`, which leaves processes running behind you.
dev: redis
	@echo "Celery worker + API on $(HOST):$(PORT). Ctrl+C stops both."
	@trap 'echo; echo "Stopping..."; kill $$CELERY_PID $$API_PID 2>/dev/null; \
	       if [ -f $(REDIS_MARKER) ]; then \
	         echo "Shutting down the Redis started by make..."; \
	         redis-cli shutdown 2>/dev/null || true; rm -f $(REDIS_MARKER); \
	       else echo "Leaving Redis running: it was not started by make."; fi; \
	       exit 0' INT TERM; \
	celery -A $(CELERY_APP) worker --loglevel=info --pool=prefork & CELERY_PID=$$!; \
	uvicorn $(API_MODULE) --host $(HOST) --port $(PORT) & API_PID=$$!; \
	wait $$CELERY_PID $$API_PID

# Start all backend services in the background. `make stop` cleans up.
backend: redis celery api
	@echo "All services started. Use 'make stop' to shut them down."

redis:
	@if redis-cli ping >/dev/null 2>&1; then \
		echo "Reusing the Redis already running on this machine."; \
	else \
		echo "Starting Redis server..."; \
		redis-server --daemonize yes && touch $(REDIS_MARKER); \
	fi

celery:
	@echo "Starting Celery worker..."
	celery -A $(CELERY_APP) worker --loglevel=info --pool=prefork &

api:
	@echo "Starting FastAPI app with Uvicorn..."
	uvicorn $(API_MODULE) --host $(HOST) --port $(PORT) &

# Patterns are specific to this project's processes: a bare `pkill -f uvicorn`
# would also kill unrelated servers on the machine.
stop:
	@echo "Stopping services..."
	@pkill -f "celery -A $(CELERY_APP)" || true
	@pkill -f "uvicorn $(API_MODULE)" || true
	@$(MAKE) --no-print-directory stop-redis

stop-redis:
	@if [ -f $(REDIS_MARKER) ]; then \
		echo "Shutting down the Redis started by make..."; \
		redis-cli shutdown 2>/dev/null || true; \
		rm -f $(REDIS_MARKER); \
	else \
		echo "Leaving Redis running: it was not started by make."; \
	fi

build:
	cd frontend && npm install && npm run build

frontend:
	cd frontend && npm start

clean: stop
