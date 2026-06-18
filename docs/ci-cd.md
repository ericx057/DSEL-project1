# CI/CD Runbook

This project uses GitHub Actions for CI and image publishing. Deployment is a manual promotion of a verified image digest from staging to production.

## Pipeline

Workflow: `.github/workflows/ci.yml`

Triggers:

- Pull requests to `main` or `master`
- Pushes to `main` or `master`

Jobs:

- `test`: installs Python 3.13 dependencies from `requirements.txt`, runs pytest with workspace-local cache paths, runs the harness evaluation gate, and uploads `cache/harness-eval-ci/` as `harness-eval-report`.
- `docker`: waits for `test`, builds the production image with `Dockerfile`, smoke-tests the built image locally, and pushes to GHCR only on branch pushes after smoke passes.

Published image tags:

- `ghcr.io/<owner>/<repo>:<git-sha>`
- `ghcr.io/<owner>/<repo>:<branch-name>`

Use the SHA tag or immutable digest for staging and production. Do not deploy by branch tag unless you are intentionally accepting a moving target.

## Required Configuration

GitHub Actions uses the built-in `GITHUB_TOKEN` for GHCR publish permissions. Runtime secrets are not needed for CI because tests use fakes and local fixtures.

Deployment environments must provide:

- `CIS_DATA_DIR`
- `CIS_JWT_SECRET`
- `CIS_JWT_ISSUER`
- `CIS_JWT_AUDIENCE`
- `CIS_METRICS_TOKEN`
- `CIS_REDIS_URL`
- `CIS_INFERENCE_PROVIDER=openrouter`
- `CIS_OPENROUTER_API_KEY`
- `CIS_OPENROUTER_MODEL`
- `CIS_OPENROUTER_BASE_URL`

Indexing environments must also provide:

- `CIS_REPOSITORY_PATH`
- `CIS_REPOSITORY_NAME`
- `CIS_EMBEDDING_BACKEND`
- `CIS_EMBEDDING_MODEL`
- `CIS_EMBEDDING_TRUST_REMOTE_CODE`

## Promotion Protocol

1. Confirm the target commit has a passing `test` job and a successful `docker` job.
2. Confirm the `docker` job summary reports the immutable digest for `ghcr.io/<owner>/<repo>:<git-sha>`.
3. Deploy that exact digest to staging with production-like Redis, SQLite volume, metrics token, JWT settings, and OpenRouter credentials.
4. Run the smoke checks below.
5. Promote the same digest to production after approval.
6. Keep the previous production digest and `CIS_DATA_DIR` snapshot available until the new release is stable.

## Smoke Checks

Run these against staging before production promotion and again after production rollout:

```bash
curl -fsS https://<host>/health
curl -fsS https://<host>/ready
curl -fsS -H "Authorization: Bearer <metrics-token>" https://<host>/metrics
curl -fsS \
  -H "Authorization: Bearer <jwt>" \
  -H "Content-Type: application/json" \
  -d '{"query":"What is the main entrypoint?","response_mode":"summary"}' \
  https://<host>/query
```

Acceptance criteria:

- `/health` returns 200.
- `/ready` returns 200 and reports indexed artifacts.
- `/metrics` returns Prometheus text and includes circuit-breaker, request latency, request status, cache status, and fallback metrics.
- `/query` returns a human-language answer, not raw source, path lists, or provider error text.
- A repeated `/query` succeeds and applies the same response policy to cached content.

CI also runs `python scripts/ci_container_smoke.py --image <tag>` against the locally built production image before any push. The smoke harness seeds a one-artifact SQLite index, starts the container with hashing embeddings and no OpenRouter key, then verifies `/health`, `/ready`, `/metrics`, and authenticated `/query`.

## Rollout Metrics

Use these Prometheus series for staging and canary decisions:

- `cis_http_request_duration_seconds_*`: calculate p95 latency by path.
- `cis_http_requests_total`: calculate request volume and 5xx rate by path/status.
- `cis_query_cache_total`: calculate cache hit, miss, and coalescing rates.
- `cis_query_fallback_total`: watch fallback rate by policy reason.
- `cis_circuit_breaker_open` and `cis_circuit_breaker_failures`: watch inference-provider health.

## Rollback

Rollback is image-first and data-safe:

1. Stop promotion and freeze traffic ramp-up.
2. Route traffic back to the previous image digest.
3. Keep the current SQLite volume if no schema migration changed it.
4. If index corruption is suspected, restore the last known-good `CIS_DATA_DIR` snapshot.
5. Re-run `/health`, `/ready`, `/metrics`, and one authenticated `/query` smoke check.

Do not run irreversible data migrations without a tested restore path and a rollback target image.

## Troubleshooting

- Pytest temp permission failures on Windows: run pytest with `--basetemp cache/pytest-local -o cache_dir=cache/pytest-cache-local`.
- Harness eval failure: inspect the uploaded `harness-eval-report` artifact and do not deploy until policy/cache safety gates pass.
- Docker build failure: reproduce with `docker build .` and verify `requirements-prod.txt` contains every runtime dependency used by `src.gateway.bootstrap:app`.
- Container smoke failure: run `python scripts/ci_container_smoke.py --image <local-tag>` and inspect Docker logs for the generated `cis-smoke-*` container.
- `/ready` returns 503: check indexed artifact count, Redis ping, trace recorder ping, and circuit-breaker state in the readiness response.
- OpenRouter outage or bad credentials: `/query` should degrade to retrieval fallback and must not return provider error text; `/ready` may fail while the circuit breaker is open.
- Redis outage: cache/coalescing is bypassed for direct queries; multi-replica production should still treat this as degraded and hold or roll back rollout.
