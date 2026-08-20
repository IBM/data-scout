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

```bash
# Start backend services
make backend

# In another terminal, start the frontend
make frontend
```

Visit http://localhost:3000 for the UI, http://localhost:8000/docs for the API.

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

## API

The FastAPI server exposes:

- `POST /jobs/` — Submit a pipeline job
- `GET /jobs/` — List all jobs
- `GET /jobs/{id}` — Job details
- `GET /jobs/{id}/progress` — Current status/progress
- `POST /jobs/{id}/interrupt` — Stop a running job
- `GET /jobs/{id}/logs/redis` — Live logs (cached)
- `GET /jobs/{id}/logs/storage` — Final logs from storage
- `WS /ws/jobs/{id}/logs` — WebSocket live log stream
- `GET /jobs/{id}/metrics/redis` — Live metrics
- `GET /jobs/{id}/download-zip` — Presigned URL for results ZIP
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
- `REACT_APP_API_KEY` — Optional API key if backend auth is enabled

## Testing

```bash
# Backend tests (206 tests)
pytest --tb=short

# Frontend tests (42 tests)
cd frontend && npx react-scripts test --watchAll=false
```

## Docker

```bash
docker-compose up -d
```

Services: Redis, API server, Celery worker, Frontend (nginx). See `docker-compose.yml`.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, code style, and PR process.

## License

Apache License 2.0. See [LICENSE](LICENSE).
