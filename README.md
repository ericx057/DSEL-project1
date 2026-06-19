# Codebase Intelligence System

Production retrieval-backed code intelligence gateway for indexed repositories.

The canonical answer path is the harness:

```text
HTTP /query
  -> gateway auth, scope, rate limit, audit
  -> HarnessService
  -> retrieval summaries and index fingerprint
  -> versioned cache lookup
  -> model adapter when useful
  -> ResponsePolicy
  -> trace, audit, history, response
```

Normal responses are human-language summaries. They should not be raw file paths, copied source, or abstract labels like "X is a class" when better evidence exists.

## Production Surface

- Desktop Spotlight app: `python -m src.desktop`
- Desktop hotkey: `Ctrl+Alt` toggles `DSEL Code Search`
- Gateway: `src.gateway.bootstrap:app`
- Local app factory: `src.gateway.main:create_app`
- Harness boundary: `src/harness/`
- Retrieval/index store: `src/retrieval/database.py`
- Indexer entrypoint: `python -m src.ingestion.cli`
- Harness eval: `python -m evaluation.harness_eval`
- Deployment runbook: [docs/production-deployment.md](docs/production-deployment.md)
- CI/CD runbook: [docs/ci-cd.md](docs/ci-cd.md)

## Local Verification

```bash
python -m pytest
python -m src.desktop --help
python -m evaluation.harness_eval --out-dir cache/harness-eval-local
```

To run the desktop app normally, start `python -m src.desktop` and press `Ctrl+Alt`.
Use `python -m src.desktop --show` to open it immediately while developing.

## Environment Configuration

Use `.env.example` as the template for local and Docker Compose configuration. For Compose, put the actual values in a root `.env` file or export them in the shell before `docker compose up`. In production, set the same names in the deployment secret manager or service environment.

Direct PowerShell local run:

```powershell
$env:CIS_OPENROUTER_API_KEY="<your-openrouter-key>"
$env:CIS_OPENROUTER_MODEL="qwen/qwen3.6-27b"
$env:CIS_JWT_SECRET="<long-random-secret>"
$env:CIS_METRICS_TOKEN="<metrics-token>"
$env:CIS_MAX_REQUEST_BYTES="65536"
$env:CIS_QUERY_MAX_CHARS="8000"
$env:CIS_RATE_LIMIT_CAPACITY="20"
$env:CIS_RATE_LIMIT_REFILL_PER_MINUTE="20"
$env:CIS_RATE_LIMIT_BASE_BACKOFF_SECONDS="2"
$env:CIS_RATE_LIMIT_MAX_BACKOFF_SECONDS="60"
```

## Container Stack

```bash
docker compose --profile indexing run --rm indexer
docker compose up gateway redis prometheus
```

Required environment for the compose path:

- `CIS_JWT_SECRET`
- `CIS_METRICS_TOKEN`
- `CIS_OPENROUTER_API_KEY`
- `CIS_OPENROUTER_MODEL` defaults to `qwen/qwen3.6-27b` and can be set to any OpenRouter model slug
- `CIS_REDIS_URL` enables shared cache, request coalescing, and atomic rate limiting across gateway replicas
- `CIS_MAX_REQUEST_BYTES` caps HTTP request bodies, default `65536`
- `CIS_QUERY_MAX_CHARS` caps `/query` prompt size, default `8000`
- `CIS_RATE_LIMIT_CAPACITY` and `CIS_RATE_LIMIT_REFILL_PER_MINUTE` control per-user token bucket limits
- `CIS_RATE_LIMIT_BASE_BACKOFF_SECONDS` and `CIS_RATE_LIMIT_MAX_BACKOFF_SECONDS` control exponential backoff after repeated throttling

For Qwen3.6 27B on OpenRouter:

```bash
CIS_OPENROUTER_API_KEY=<your-openrouter-key>
CIS_OPENROUTER_MODEL=qwen/qwen3.6-27b
```

The gateway exposes:

- `GET /health` for liveness
- `GET /ready` for traffic readiness
- `GET /metrics` for Prometheus, protected by `CIS_METRICS_TOKEN`
- `POST /query` for authenticated retrieval-backed answers

## Indexing

Index any repository mounted at `CIS_REPOSITORY_PATH`; the index is persisted in `CIS_DATA_DIR/index.db` and retrieval is filtered by the stored `repository` scope:

```bash
CIS_DATA_DIR=./.cis \
CIS_REPOSITORY_PATH=/path/to/repo \
CIS_REPOSITORY_NAME=my-repo \
CIS_EMBEDDING_BACKEND=hashing \
    python -m src.ingestion.cli
```

`CIS_REPOSITORY_NAME` becomes the repository scope used by access control and retrieval.
For Docker Compose, set `CIS_REPOSITORY_HOST_PATH=/path/to/repo` and `CIS_REPOSITORY_NAME=my-repo`, then run `docker compose --profile indexing run --rm indexer`.
Re-indexing a repository is atomic: the previous index remains queryable until the replacement has been fully parsed, embedded, and committed.

## CI

GitHub Actions runs the full pytest suite, the harness eval gate, a production Docker build, and a container smoke test on `main` and `master`. See [docs/ci-cd.md](docs/ci-cd.md) for image tags, promotion, smoke checks, rollback, and troubleshooting. Generated eval outputs belong under `cache/` or `results/harness-eval-*` and are ignored by git.
