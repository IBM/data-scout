# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- Document extraction runs in a child process instead of a thread pool. A parser
  crash now costs the one document rather than the whole run, and extraction is
  roughly ten times faster at scale because separate processes parallelise the
  CPU-bound parsing the GIL was serialising.

### Fixed

- Jobs no longer report `running` forever when a worker dies mid-task. The
  outcome is recorded from the Celery task's `on_failure`, which runs in the main
  process and so survives a killed child.
- `POST /jobs/{id}/interrupt` no longer returns 200 without doing anything once
  the task has reached a terminal state; it reconciles the stale job status.
- `GoogleSearchClient` raised `UnboundLocalError` on any network error, and
  parsed a 4xx body as an empty result page, so a bad API key looked like "no
  results".
- The per-job Google API call budget is now thread-safe; it was a shared counter
  that concurrent threads overwrote.
- Redis connections are built with redis-py's URL parser, so credentials and
  `rediss://` are no longer silently dropped.
- `STORAGE_BUCKET` is read instead of being ignored in favour of the first path
  segment.
- A query-generation step that got no LLM response reports the cause instead of
  raising `AttributeError` on `NoneType`.
- Crawl-policy classification keeps the batches that returned when an earlier one
  came back empty.
- The log and metrics WebSockets no longer reconnect after the component
  unmounts, and they explain close code 1008 rather than retrying forever.
- Docker deployment: job submission, extraction, and result access; non-root
  containers, healthchecks, an nginx SPA fallback, and a named Redis volume.

### Documentation

- `REACT_APP_API_KEY` is documented as not being a secret: Create React App
  inlines it into the public JS bundle.
- Added `CODE_OF_CONDUCT.md`, `NOTICE`, `MAINTAINERS.md`, and this changelog.
- Corrected stale claims: extraction no longer falls back to a thread pool, the
  crawl-policy allow/deny lists are not shipped, the test suite does not require
  Redis, and unauthenticated requests return 401 rather than 403.
- `frontend/README.md` replaced the Create React App boilerplate with
  project-specific setup, configuration, and known pitfalls.

## [0.1.0] - 2026-08-24

Initial open-source release: LLM-guided taxonomy expansion and seed retrieval,
a FastAPI job API with a Celery worker, a React dashboard, local and S3 storage
backends, Google and Tavily search providers, and Docker Compose deployment.
