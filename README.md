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
python -m evaluation.harness_eval --out-dir cache/harness-eval-local
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
- `CIS_OPENROUTER_MODEL` defaults to `~openai/gpt-latest` and can be set to any OpenRouter model slug

The gateway exposes:

- `GET /health` for liveness
- `GET /ready` for traffic readiness
- `GET /metrics` for Prometheus, protected by `CIS_METRICS_TOKEN`
- `POST /query` for authenticated retrieval-backed answers

## Indexing

Index any repository mounted at `CIS_REPOSITORY_PATH`:

```bash
CIS_DATA_DIR=./.cis \
CIS_REPOSITORY_PATH=/path/to/repo \
CIS_REPOSITORY_NAME=my-repo \
CIS_EMBEDDING_BACKEND=hashing \
    python -m src.ingestion.cli
```

`CIS_REPOSITORY_NAME` becomes the repository scope used by access control and retrieval.

## CI

GitHub Actions runs the full pytest suite, the harness eval gate, a production Docker build, and a container smoke test on `main` and `master`. See [docs/ci-cd.md](docs/ci-cd.md) for image tags, promotion, smoke checks, rollback, and troubleshooting. Generated eval outputs belong under `cache/` or `results/harness-eval-*` and are ignored by git.
