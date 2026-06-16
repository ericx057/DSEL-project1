from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from src.gateway.main import create_app, global_circuit_breaker
from src.gateway.repositories import SQLiteAccessMatrixRepository, SQLiteAuditRepository, SQLiteScopeRepository
from src.gateway.services import InMemorySemanticCacheRepository, TokenBucketRateLimitRepository
from src.harness.trace import SQLiteTraceRecorder
from src.retrieval.database import ArtifactRecord, HashingEmbeddingProvider, SQLiteUnifiedStore


def _app_with_store(tmp_path: Path, store: SQLiteUnifiedStore):
    return create_app(
        access_matrix_repo=SQLiteAccessMatrixRepository(tmp_path / "access.db"),
        scope_repo=SQLiteScopeRepository(tmp_path / "access.db"),
        cache_repo=InMemorySemanticCacheRepository(),
        rate_limit_repo=TokenBucketRateLimitRepository(),
        audit_repo=SQLiteAuditRepository(tmp_path / "audit.db"),
        retrieval_store=store,
        trace_recorder=SQLiteTraceRecorder(tmp_path / "traces.db"),
    )


@pytest.mark.asyncio
async def test_ready_endpoint_rejects_empty_index(tmp_path: Path):
    store = SQLiteUnifiedStore(tmp_path / "index.db", HashingEmbeddingProvider(dimensions=16))
    app = _app_with_store(tmp_path, store)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/ready")

    body = response.json()
    assert response.status_code == 503
    assert body["status"] == "not_ready"
    assert body["checks"]["retrieval_store"]["ok"] is False
    assert body["checks"]["retrieval_store"]["metadata"]["artifact_count"] == 0


@pytest.mark.asyncio
async def test_ready_endpoint_accepts_indexed_store(tmp_path: Path):
    store = SQLiteUnifiedStore(tmp_path / "index.db", HashingEmbeddingProvider(dimensions=16))
    store.upsert_artifacts(
        [
            ArtifactRecord(
                "repo-a:service",
                "repo-a",
                "service.py",
                "python",
                "def handle_request(): pass",
                1,
                "L-1",
                "handle_request",
            )
        ]
    )
    app = _app_with_store(tmp_path, store)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/ready")

    body = response.json()
    assert response.status_code == 200
    assert body["status"] == "ready"
    assert body["checks"]["retrieval_store"]["ok"] is True
    assert body["checks"]["retrieval_store"]["metadata"]["artifact_count"] == 1
    assert body["checks"]["cache"]["ok"] is True
    assert body["checks"]["trace"]["ok"] is True


@pytest.mark.asyncio
async def test_ready_endpoint_fails_when_circuit_breaker_is_open(tmp_path: Path):
    store = SQLiteUnifiedStore(tmp_path / "index.db", HashingEmbeddingProvider(dimensions=16))
    store.upsert_artifacts(
        [ArtifactRecord("repo-a:service", "repo-a", "service.py", "python", "def service(): pass", 1, "L-1")]
    )
    app = _app_with_store(tmp_path, store)
    global_circuit_breaker.state = "OPEN"
    global_circuit_breaker.failure_count = 3

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/ready")
    finally:
        global_circuit_breaker.state = "CLOSED"
        global_circuit_breaker.failure_count = 0

    body = response.json()
    assert response.status_code == 503
    assert body["checks"]["circuit_breaker"]["ok"] is False
