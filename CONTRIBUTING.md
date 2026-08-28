# Contributing to Data Scout

## Development Setup

1. **Clone and install**:
   ```bash
   git clone https://github.com/IBM/data-scout.git
   cd data-scout
   pip install -e ".[dev]"
   ```

2. **Configure environment**:
   ```bash
   cp .env.example .env
   # Fill in at minimum: LLM_API_KEY, LLM_BASE_URL, LLM_MODEL_NAME
   ```

3. **Start Redis** (needed to run the API and worker; the test suite does not
   require it — every test stubs Redis out):
   ```bash
   redis-server
   ```

4. **Frontend setup**:
   ```bash
   cd frontend
   npm install
   ```

## Running Tests

All tests must pass before submitting a PR.

```bash
# Backend (from repo root)
pytest --tb=short

# Frontend
cd frontend && npx react-scripts test --watchAll=false
```

## Code Style

- Python: follow existing patterns in the codebase. No strict formatter enforced yet.
- TypeScript/React: follow existing component patterns. Use functional components with hooks.
- Imports: use `from src.x import y` for all Python imports (not relative `from .x`).
- No `print()` in `src/` — use the logging module or `notify_fn` callbacks.

## Pull Request Process

1. Create a feature branch from `main`
2. Make your changes with clear, focused commits
3. Ensure all tests pass (backend + frontend)
4. Open a PR with a description of what changed and why
5. Address review feedback

## Architecture Guidelines

- **SearchPipeline** is a thin orchestrator — business logic belongs in composed classes (`QueryGenerator`, `DocumentDownloader`, `ResultHandler`)
- New processing utilities go in the appropriate module under `src/processing/` (not in `utils.py`)
- Keep `utils.py` as a re-export facade only — do not add new functions there
- External integrations (LLM, search, storage) are injected via settings, not hardcoded

## Adding a New Search Provider

1. Create `src/search/your_provider.py` implementing a `perform_search(queries, max_results)` method
2. Add config fields to `src/config.py`
3. Add the provider option to `SearchPipeline.__init__` in `pipeline.py`
4. Add tests in `tests/test_search_clients.py`

## Adding a New Storage Backend

1. Create `src/storage/your_backend.py` implementing the `StorageBackend` ABC
2. Register it in `src/storage/__init__.py`'s `create_storage_backend` factory
3. Add config fields to `src/config.py`
4. Add tests
