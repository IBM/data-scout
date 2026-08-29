# Copyright 2025-2026 IBM Corporation
# SPDX-License-Identifier: Apache-2.0

# --- Dependency build stage ---
# The compiler toolchain lives here and is never copied forward, so it does not
# ship inside the runtime images. Dependencies go into a self-contained venv
# that the runtime stage copies wholesale.
FROM python:3.11-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    POETRY_NO_INTERACTION=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Pinned: an unpinned build tool means the image silently changes underneath you,
# and a Poetry release that alters install semantics is hard to diagnose from a
# failed build. Bump deliberately.
ARG POETRY_VERSION=2.4.1
RUN pip install --no-cache-dir "poetry==${POETRY_VERSION}" && \
    python -m venv "$VIRTUAL_ENV"

# Dependencies before source, so editing src/ does not reinstall the world.
COPY pyproject.toml poetry.lock* README.md ./
RUN poetry config virtualenvs.create false && \
    poetry install --no-ansi --without dev --no-root

COPY src/ ./src/
COPY run.py ./
RUN poetry install --no-ansi --only-root

# --- Runtime base ---
FROM python:3.11-slim AS base

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Unprivileged: nothing here needs root, and the ports bound are above 1024.
RUN useradd --create-home --uid 1000 appuser

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY --chown=appuser:appuser src/ ./src/
COPY --chown=appuser:appuser run.py ./

# results/ must exist and be owned by appuser *in the image*: a fresh named
# volume inherits the ownership of the directory it shadows, so without this it
# comes up root-owned and the worker cannot write run output into it.
RUN mkdir -p /app/results && chown -R appuser:appuser /app

USER appuser

# --- API server ---
FROM base AS api
EXPOSE 8000
CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]

# --- Celery worker ---
FROM base AS worker
CMD ["celery", "-A", "src.api.celery_worker.celery_app", "worker", "--loglevel=info", "--pool=prefork"]

# --- Frontend ---
FROM node:18-alpine AS frontend-build
WORKDIR /app
COPY frontend/package.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build

FROM nginx:alpine AS frontend
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=frontend-build /app/build /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
