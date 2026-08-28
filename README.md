# Data Scout

LLM-guided web corpus builder. Generates search queries from a topic description, retrieves results, downloads and extracts text, and annotates relevance — producing a curated dataset ready for downstream training or analysis.

## Features

- **Multiple input modes**: query, topic (with recursive expansion), keyword, or pre-built search file
- **LLM-powered query generation**: uses any OpenAI-compatible endpoint to expand topics into diverse search queries
- **Pluggable search**: Google Custom Search or Tavily
- **Concurrent download & extraction**: parallel HTTP fetches + text extraction (HTML via trafilatura, PDF via pypdf)
- **Annotations**: relevancy classification, crawl-policy checking, domain analysis
- **Filtering**: keep only results passing annotation criteria
- **Storage**: local or S3-compatible upload of run outputs
- **API + Web UI**: FastAPI backend with Celery workers, React frontend with real-time WebSocket logs
- **CLI**: run pipelines directly from the command line

> **Note:** This release implements the taxonomy expansion and seed retrieval stages of the Data Scout pipeline. The subdomain probe screening and targeted deep crawl stages described in the paper are not yet included.

## Architecture

```
src/
├── pipeline/          # Core orchestration
│   ├── pipeline.py    # SearchPipeline (orchestrator)
│   ├── query_generator.py
│   ├── downloader.py
│   └── result_handler.py
├── llm/               # LLM client (OpenAI-compatible)
├── search/            # Google & Tavily search clients
├── processing/        # Text extraction, parsing, annotations, filtering
├── storage/           # Pluggable storage (local / S3)
├── api/               # FastAPI + Celery task layer
└── job_tracking/      # Redis-backed job state

frontend/              # React UI (Material-UI)
```

## Quick Start

### Prerequisites

- Python 3.11+
- Redis (for API/job tracking mode)
- Node.js 18+ (for frontend)

### 1. Install

```bash
git clone https://github.com/IBM/data-scout.git
cd data-scout
pip install -e .
```

### 2. Configure

```bash
cp .env.example .env
# Edit .env with your LLM and search API keys
```

### 3. Run (CLI)

```bash
# Generate queries from a topic (no search)
python run.py --mode topic --input "quantum computing applications"

# Full pipeline: generate queries + search + download + annotate
python run.py --mode query --input "machine learning for drug discovery" \
  --perform_search --annotations relevancy donotcrawl --filter_results
```

### 4. Run (API + UI)

Requires a local Redis and Node 18+. Or skip both and use
[Docker](#docker), which needs neither.

```bash
# Redis + Celery worker + API, in the foreground. Ctrl+C stops them.
make dev

# In another terminal, start the frontend
make frontend
```

Visit http://localhost:3000 for the UI, http://localhost:8000/docs for the API.

`make dev` reuses a Redis that is already running and only shuts one down if it
started it, so it will not stop a Redis holding your other data.

### Make targets

| Target | What it does |
|--------|--------------|
| `make dev` | Redis (if needed), Celery worker, and API in the foreground; Ctrl+C stops everything it started |
| `make backend` | The same three in the background. Returns immediately; clean up with `make stop` |
| `make stop` | Stops this project's worker and API, and Redis only if make started it |
| `make frontend` | React dev server on :3000 with hot reload |
| `make build` | `npm install` + production frontend build |
| `make redis`, `make celery`, `make api` | Individual services, if you want them in separate terminals |
| `make clean` | Alias for `make stop` |

Override the port with `make dev PORT=8001`, and the bind address with `HOST=127.0.0.1`.

## Configuration

All configuration is via environment variables (see `.env.example`). Key settings:

| Variable | Description | Default |
|----------|-------------|---------|
| `LLM_API_KEY` | API key for OpenAI-compatible endpoint | (required) |
| `LLM_BASE_URL` | LLM endpoint base URL | (required) |
| `LLM_MODEL_NAME` | Model identifier | (required) |
| `TAVILY_API_KEY` | Tavily search API key | |
| `GOOGLE_API_KEY` | Google Custom Search key | |
| `CX_KEY` | Google Custom Search engine ID | |
| `STORAGE_BACKEND` | `local` or `s3` | `local` |
| `REDIS_URL` | Redis connection URL | `redis://localhost:6379/0` |
| `API_KEY` | API auth key (empty = no auth) | |
| `DEBUG_ERRORS` | Return the underlying exception in API errors. Leave off outside development — error text can include paths, Redis credentials and S3 bodies | `false` |

## CLI Usage

```
python run.py --mode MODE --input INPUT [options]

Modes:
  query    - Direct query generation from input text
  topic    - Recursive topic expansion into subtopics
  keyword  - Keyword-based query generation
  search   - Use pre-generated queries from a file

Options:
  --perform_search          Execute searches (default: generation only)
  --max_results_per_query N Max results per query (default: 20)
  --recursion_depth N       Topic expansion depth (topic mode only, default: 1)
  --output_format FORMAT    jsonl or parquet (default: jsonl)
  --output_folder_name NAME Base name for output directory
  --annotations [LIST]      donotcrawl, relevancy
  --filter_results          Keep only rows passing annotations
  --input_file PATH         Pre-built queries file (search mode only)
```

Output goes to `results/<output_folder_name>/<run_id>/`: `topics.jsonl`, the results file
(`.jsonl` or `.parquet`), `metrics.json`, and `pipeline.log`.

CLI runs need no Redis and are **not recorded as jobs**, so they do not appear in the
dashboard and have no live progress view — progress goes to the console and
`pipeline.log`. Submit through the API or UI if you want job history, live logs, and the
results browser. In exchange, the CLI extracts text across all cores, which the
containerized worker cannot (see [Known limitations](#known-limitations)).

## API

The FastAPI server exposes:

- `GET /health` — Liveness check (no auth, used by the container healthcheck)
- `POST /jobs/` — Submit a pipeline job
- `GET /jobs/` — List all jobs
- `GET /jobs/{id}` — Job details
- `GET /jobs/{id}/progress` — Current status/progress
- `POST /jobs/{id}/interrupt` — Stop a running job
- `GET /jobs/{id}/logs/redis` — Live logs (cached)
- `GET /jobs/{id}/logs/storage` — Final logs from storage
- `WS /ws/jobs/{id}/logs` — WebSocket live log stream
- `GET /jobs/{id}/metrics/redis` — Live metrics
- `GET /jobs/{id}/metrics/storage` — Final metrics from storage
- `WS /ws/jobs/{id}/metrics` — WebSocket live metrics stream
- `GET /jobs/{id}/download-zip` — Download URL for the results ZIP (presigned on S3, a direct route on local storage)
- `GET /jobs/{id}/download-zip/archive` — The ZIP itself, built on demand for local storage
- `GET /jobs/{id}/files` — List available output files
- `GET /jobs/{id}/files/view` — Paginated file content

Full interactive docs at `/docs` (Swagger) or `/redoc`.

## Frontend Development

```bash
cd frontend
npm install
npm start          # Dev server on :3000
npm test           # Run tests
npm run build      # Production build
```

Environment variables (set in `frontend/.env`):
- `REACT_APP_API_URL` — Backend URL (default: `http://localhost:8000`)
- `REACT_APP_API_KEY` — API key for the backend, if `API_KEY` is set. **Not a
  secret: it is compiled into the public JS bundle** — see [Exposure](#exposure)

## Testing

```bash
# Backend tests (278 tests)
pytest --tb=short

# Frontend tests (50 tests)
cd frontend && npx react-scripts test --watchAll=false
```

## Docker

```bash
docker-compose up -d
```

Services: Redis, API server, Celery worker, Frontend (nginx). See `docker-compose.yml`.
The UI is on http://localhost:3000, the API on http://localhost:8000, and
`GET /health` reports whether the API is serving. Job history lives in the
`redis-data` volume and run output in `results`, so both survive
`docker-compose down`. Redis itself is not published to the host; inspect it with
`docker-compose exec redis redis-cli`.

The containers run as an unprivileged user (uid 1000). If you are upgrading from
an image that ran as root, take ownership of the existing volume once, or the
worker will not be able to write new run output into it:

```bash
docker run --rm -v data-scout_results:/v alpine chown -R 1000:1000 /v
```

### Exposure

`API_KEY` is empty by default, which leaves the API unauthenticated, and Compose
publishes port 8000 on all interfaces. On any machine reachable by others, set
`API_KEY` in `.env` before starting, or bind the published ports to localhost
(`"127.0.0.1:8000:8000"`). An open endpoint spends your LLM and search credits.

See [Known limitations](#known-limitations) for what setting `API_KEY` costs you
in the UI.

**`REACT_APP_API_KEY` is not a secret.** Create React App inlines every
`REACT_APP_*` variable at build time, so the value ends up as a literal string in
`frontend/build/static/js/main.*.js`. Anyone who can load the page — or read the
built bundle, or pull the frontend image — can recover it, and it is the same key
that authenticates every API route.

That is acceptable for a local run, where the only person loading the page is
you, and it is the intended use of this tool. It is not a way to protect a shared
or public deployment: guarding the API from a browser needs credentials the
browser never holds, such as a session cookie or a short-lived token minted
server-side. No such mechanism exists here yet, so treat a reachable frontend as
equivalent to publishing `API_KEY`.

### If LLM calls hang inside containers

If your LLM or search endpoint is only reachable over a VPN, a tunnel MTU lower
than the container network's silently breaks large responses: TCP connects, then
every request dies with a read timeout, while the same request from the host
succeeds. Lower the VM's MTU to match the tunnel:

```bash
# podman; does not survive `podman machine stop`
podman machine ssh <machine-name> 'sudo ip link set enp0s1 mtu 1380'
```

For Docker Desktop, set the MTU in Settings → Docker Engine (`"mtu": 1380`).

## Known limitations

**An interrupt during extraction can outlive the job on macOS.** Extraction runs in
child processes so that a parser crash cannot take the worker down. On Linux the
children are given `PR_SET_PDEATHSIG`, so they die with the worker when
`POST /jobs/{id}/interrupt` revokes it with SIGKILL. macOS has no equivalent, so a
child there keeps working until it finishes its current batch. Local development
only; every container target is Linux.

**A document that crashes the parser is skipped, not extracted.** trafilatura
parses via libxml2, and a malformed document can segfault it. That now costs the
one document — logged as `Extraction crashed on <url>` — instead of the whole run,
but the document yields no text. The underlying parser crash is not fixed.

**The frontend image serves IPv4 only.** nginx is configured with `listen 80`, so
an IPv6-only network or an IPv6 service address cannot reach it. This is invisible
behind the published port, which forwards over IPv4. Adding `listen [::]:80;`
enables IPv6 but makes nginx refuse to start on hosts without an IPv6 stack, so it
is left off by default; render the listen directive from a template if you need it.

**`API_KEY` breaks two things in the browser.** Browsers cannot attach headers to a
WebSocket handshake or to a download opened in a new tab, and the UI sends none. So
with a key set, live logs and metrics are rejected and the results ZIP download
returns 401, while the rest of the UI keeps working.

**Fresh checkouts start with an empty crawl policy cache.** The cache under
`src/processing/crawl_policy/` is generated at runtime and deliberately not
committed — it records the domains each run searched. Early runs therefore ask the
LLM to classify more domains than later ones.

## Maintainers

Data Scout is developed and maintained by **Eelaaf Zahid** and **Chirag Garg**, its main
contributors — see [MAINTAINERS.md](MAINTAINERS.md). Please open an issue for bugs
and feature requests, and [SECURITY.md](SECURITY.md) for vulnerabilities.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, code style, and PR
process, and [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) for the standards expected of
participants. Notable changes are recorded in [CHANGELOG.md](CHANGELOG.md).

## License

Apache License 2.0. See [LICENSE](LICENSE).
