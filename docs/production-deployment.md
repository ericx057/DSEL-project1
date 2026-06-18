# Production Deployment

This service is a retrieval-backed code intelligence gateway. The production path is:

1. `src.gateway.bootstrap:app` builds the FastAPI gateway from environment configuration.
2. `/query` authenticates the caller, resolves repository scope, rate limits, audits, and delegates to `HarnessService`.
3. `HarnessService` retrieves summarized context, checks versioned cache entries, calls the model adapter when useful, applies `ResponsePolicy`, records a trace, and returns only shaped text.
4. `SQLiteUnifiedStore` stores indexed artifacts and graph edges. Redis stores response cache entries and request coalescing locks.
5. `SQLiteTraceRecorder`, `SQLiteAuditRepository`, and `SQLiteUserHistoryRepository` write traceability data under `CIS_DATA_DIR`.

## Live Components

| Component | Production role | Required for readiness |
| --- | --- | --- |
| Gateway | Auth, RBAC scope, rate limits, audit, harness delegation, HTTP surface | yes |
| Harness | Retrieval, cache decisions, model calls, response policy, trace recording | yes |
| SQLite index | Ranked source artifacts and graph edges | yes, must contain artifacts |
| Redis | Shared cache and coalescing across gateway replicas | yes for multi-replica production |
| OpenRouter | Hosted model provider behind `ModelHook` | degraded mode can still return retrieval fallback |
| Prometheus | Scrapes `/metrics` using `CIS_METRICS_TOKEN` | no |

## CI Protocol

GitHub Actions runs on `main` and `master` pushes and pull requests. The CI/CD runbook is [docs/ci-cd.md](ci-cd.md).

Required gates before deploy:

- Full test suite passes.
- Harness eval has 100 percent policy/cache safety.
- Harness eval multilingual concrete-answer rate is at least 95 percent.
- Docker image builds from `requirements-prod.txt`.
- Built image passes `scripts/ci_container_smoke.py` before any push.
- No deployment proceeds from a dirty release branch or without a rollback target image.

## CD Protocol

Use the two-stage promotion path in [docs/ci-cd.md](ci-cd.md):

1. Build and tag image: `ghcr.io/<owner>/<repo>:<git-sha>`.
2. Deploy to staging with production-like Redis, SQLite volume, and OpenRouter credentials.
3. Run the smoke checks from the runbook.
4. Promote the exact same image digest to production after approval.
5. Keep the previous production image and data volume snapshot available for rollback.

Preferred rollout is canary, then rolling:

- Start with 1 replica or 5 percent traffic.
- Watch p95 latency, 5xx rate, cache hit rate, circuit breaker state, and response quality traces.
- Increase traffic only if `/ready` is stable and traces show policy-clean answers.

## Runtime Configuration

Required:

| Variable | Purpose |
| --- | --- |
| `CIS_DATA_DIR` | Directory for `index.db`, `access.db`, `audit.db`, `history.db`, and `traces.db` |
| `CIS_JWT_SECRET` | HS256 JWT signing secret |
| `CIS_JWT_ISSUER` | Expected JWT issuer |
| `CIS_JWT_AUDIENCE` | Expected JWT audience |
| `CIS_METRICS_TOKEN` | Token for `/metrics` |
| `CIS_REDIS_URL` | Redis URL for shared cache and coalescing |
| `CIS_INFERENCE_PROVIDER` | `openrouter` for hosted inference |
| `CIS_OPENROUTER_API_KEY` | OpenRouter API key used by `ModelHook` |
| `CIS_OPENROUTER_MODEL` | OpenRouter model slug, default `~openai/gpt-latest` |
| `CIS_OPENROUTER_BASE_URL` | OpenRouter API base URL, default `https://openrouter.ai/api/v1` |

Indexing:

| Variable | Purpose |
| --- | --- |
| `CIS_REPOSITORY_PATH` | Repository path mounted into the indexer |
| `CIS_REPOSITORY_NAME` | Scope name stored on artifacts |
| `CIS_EMBEDDING_BACKEND` | `nomic`, `sentence_transformers`, `minilm`, or `hashing` |
| `CIS_EMBEDDING_MODEL` | Embedding model name |
| `CIS_EMBEDDING_TRUST_REMOTE_CODE` | Whether transformer loading can use remote model code |

Optional local llama.cpp profile:

| Variable | Purpose |
| --- | --- |
| `CIS_INFERENCE_PROVIDER` | Set to `llama.cpp` to use the local profile instead of OpenRouter |
| `CIS_LLAMA_CPP_BASE_URL` | llama.cpp server base URL |
| `CIS_LLAMA_CPP_MODEL_PATH` | Default GGUF path |
| `CIS_LLAMA_CPP_MODEL_FP16` | FP16 model path override |
| `CIS_LLAMA_CPP_MODEL_FP8` | FP8 model path override |
| `CIS_LLAMA_CPP_MODEL_FP4` | FP4 model path override |
| `CIS_LLAMA_CPP_PRECISION` | `fp16`, `fp8`, or `fp4` |
| `CIS_LLAMA_CPP_CONTEXT_WINDOW` | Context window |
| `CIS_LLAMA_CPP_N_GPU_LAYERS` | GPU layer placement |

Bootstrap helpers:

| Variable | Purpose |
| --- | --- |
| `CIS_BOOTSTRAP_USER` | Optional user tier bootstrap |
| `CIS_BOOTSTRAP_GROUP` | Optional group scope bootstrap |
| `CIS_BOOTSTRAP_TIER` | Optional tier for bootstrap user |

## Startup Order

1. Provision persistent volume for `CIS_DATA_DIR`.
2. Start Redis.
3. Configure `CIS_OPENROUTER_API_KEY` and `CIS_OPENROUTER_MODEL`.
4. Run the indexer:

```bash
docker compose --profile indexing run --rm indexer
```

5. Start the gateway.
6. Wait for `/health` to pass.
7. Wait for `/ready` to pass. If `/ready` reports zero artifacts, do not route traffic.

## Health And Readiness

`GET /health` is liveness. It only confirms the process can respond.

`GET /ready` is traffic readiness. It returns 200 only when:

- retrieval store is configured,
- index fingerprint is usable,
- indexed artifact count is greater than zero,
- cache backend ping passes,
- trace recorder ping passes,
- inference circuit breaker is not open.

Readiness intentionally fails when the circuit breaker is open, but `/query` still attempts graceful degradation for direct in-flight traffic.

## Graceful Fallbacks

The production response contract is:

- Cache hits still go through `ResponsePolicy`; legacy or poisoned cache strings are treated as untrusted.
- If OpenRouter is unavailable, `ModelHook` avoids known-bad provider calls while the circuit is open.
- Model error text is never returned as the answer. `ResponsePolicy` falls back to deterministic retrieval summaries.
- If retrieval evidence is thin, the response says what can and cannot be confirmed.
- If retrieval finds nothing, the response says no indexed context matched and does not speculate.
- Unauthorized scopes return 403 before retrieval details are recorded.

## RTL Maintenance

For this deployment, RTL means reliability, traceability, and latency.

Reliability:

- `/ready` gates traffic on indexed data, cache, trace storage, and circuit breaker state.
- Redis is required for shared cache/coalescing when more than one gateway replica is running.
- The previous image and data snapshot must remain available for rollback.

Traceability:

- Every harness response records a trace id.
- Traces include retrieval ids, prompt summary, cache status, policy flags, timings, and final response.
- Audit logs record user id, tier, scoped repositories, cache status, latency, and RBAC blocks.

Latency:

- Cache-hit integration path target: p95 under 50 ms.
- Harness overhead target: p95 under 20 ms excluding retrieval/model time.
- Circuit-open model calls short-circuit locally instead of waiting on a failing backend.
- Canary rollout watches `cis_http_request_duration_seconds_*`, `cis_http_requests_total`, `cis_query_cache_total`, `cis_query_fallback_total`, and circuit breaker metrics before increasing traffic.

## Rollback

Rollback is image-first and data-safe:

1. Stop promotion immediately.
2. Route traffic back to the previous image digest.
3. Keep the existing SQLite data volume if no schema change was introduced.
4. If index corruption is suspected, restore the last known-good `CIS_DATA_DIR` snapshot and restart the gateway.
5. Re-run `/ready`, `/metrics`, and one authenticated `/query` smoke test.

Do not deploy irreversible data migrations without a tested restore procedure.
