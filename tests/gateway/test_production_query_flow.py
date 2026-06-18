import base64
import hashlib
import hmac
import json
import time
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from src.gateway.main import create_app, global_circuit_breaker
from src.gateway.models import AccessTier, QueryRequest
from src.gateway.repositories import (
    AuditRepository,
    SQLiteAccessMatrixRepository,
    SQLiteAuditRepository,
    SQLiteScopeRepository,
    SQLiteUserHistoryRepository,
    UserHistoryRepository,
)
from src.gateway.security import HS256JWTVerifier
from src.gateway.services import InMemorySemanticCacheRepository, TokenBucketRateLimitRepository
from src.gateway.model_hook import ModelHook
from retrieval.database import ArtifactRecord, HashingEmbeddingProvider, SQLiteUnifiedStore


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _token(payload: dict, secret: str = "secret") -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    signing_input = f"{_b64url(json.dumps(header, separators=(',', ':')).encode())}.{_b64url(json.dumps(payload, separators=(',', ':')).encode())}"
    signature = hmac.new(secret.encode(), signing_input.encode(), hashlib.sha256).digest()
    return f"{signing_input}.{_b64url(signature)}"


class RecordingModelHook(ModelHook):
    def __init__(self):
        self.inference_engine_id = "recording-engine"
        self.prompts = []

    async def generate_stream(self, prompt: str):
        self.prompts.append(prompt)
        yield "answer"


class FailingAuditRepository(AuditRepository):
    async def log_event(self, event):
        raise RuntimeError("audit store unavailable")


class FailingHistoryRepository(UserHistoryRepository):
    async def add_record(self, record):
        raise RuntimeError("history store unavailable")

    def list_for_user(self, user_id: str, limit: int = 50):
        return []


def _production_query_app(tmp_path: Path, *, audit_repo, history_repo=None):
    store = SQLiteUnifiedStore(tmp_path / "index.db", HashingEmbeddingProvider(dimensions=16))
    store.upsert_artifacts(
        [
            ArtifactRecord("repo-a:api", "repo-a", "app.py", "python", "def public_api()", 1, "L-1", "public_api"),
        ]
    )
    access = SQLiteAccessMatrixRepository(tmp_path / "access.db")
    access.set_user_tier("user-1", AccessTier.T1)
    scopes = SQLiteScopeRepository(tmp_path / "access.db")
    scopes.grant_group_scope("platform", "repo-a")
    return create_app(
        access_matrix_repo=access,
        scope_repo=scopes,
        cache_repo=InMemorySemanticCacheRepository(),
        rate_limit_repo=TokenBucketRateLimitRepository(capacity=20, refill_per_minute=20),
        audit_repo=audit_repo,
        history_repo=history_repo,
        retrieval_store=store,
        model_hook=RecordingModelHook(),
        jwt_verifier=HS256JWTVerifier("secret", issuer="cis", audience="developers"),
    )


def _production_token() -> str:
    return _token(
        {
            "sub": "user-1",
            "groups": ["platform"],
            "iss": "cis",
            "aud": "developers",
            "exp": int(time.time()) + 60,
        }
    )


@pytest.mark.asyncio
async def test_production_query_flow_retrieves_before_inference_and_logs(tmp_path: Path):
    store = SQLiteUnifiedStore(tmp_path / "index.db", HashingEmbeddingProvider(dimensions=16))
    store.upsert_artifacts(
        [
            ArtifactRecord("repo-a:api", "repo-a", "app.py", "python", "def public_api()", 1, "L-1", "public_api"),
            ArtifactRecord("repo-a:impl", "repo-a", "app.py", "python", "secret implementation detail", 3, "L-1", "secret_impl"),
        ]
    )
    access = SQLiteAccessMatrixRepository(tmp_path / "access.db")
    access.set_user_tier("user-1", AccessTier.T1)
    scopes = SQLiteScopeRepository(tmp_path / "access.db")
    scopes.grant_group_scope("platform", "repo-a")
    audit = SQLiteAuditRepository(tmp_path / "audit.db")
    history = SQLiteUserHistoryRepository(tmp_path / "history.db")
    model_hook = RecordingModelHook()

    app = create_app(
        access_matrix_repo=access,
        scope_repo=scopes,
        cache_repo=InMemorySemanticCacheRepository(),
        rate_limit_repo=TokenBucketRateLimitRepository(capacity=20, refill_per_minute=20),
        audit_repo=audit,
        history_repo=history,
        retrieval_store=store,
        model_hook=model_hook,
        jwt_verifier=HS256JWTVerifier("secret", issuer="cis", audience="developers"),
    )
    token = _token(
        {
            "sub": "user-1",
            "groups": ["platform"],
            "iss": "cis",
            "aud": "developers",
            "exp": int(time.time()) + 60,
        }
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/query",
            json={"query": "public api secret", "response_mode": "deep"},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    assert response.text == "answer"
    assert "Retrieved summaries:" in model_hook.prompts[0]
    assert "Query: public api secret" in model_hook.prompts[0]
    assert "Give a detailed explanation" in model_hook.prompts[0]
    assert "public_api" in model_hook.prompts[0]
    assert "Do not answer by listing file paths" in model_hook.prompts[0]
    assert "def public_api()" not in model_hook.prompts[0]
    assert "app.py" not in model_hook.prompts[0]
    assert "secret implementation detail" not in model_hook.prompts[0]
    assert audit.list_events()[0].cache_hit is False
    assert audit.list_events()[0].inference_engine_used == "recording-engine"
    assert history.list_for_user("user-1")[0].response == "answer"
    assert history.list_for_user("user-1")[0].inference_engine_used == "recording-engine"


@pytest.mark.asyncio
async def test_successful_query_response_survives_history_write_failure(tmp_path: Path):
    audit = SQLiteAuditRepository(tmp_path / "audit.db")
    app = _production_query_app(tmp_path, audit_repo=audit, history_repo=FailingHistoryRepository())

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/query",
            json={"query": "public api"},
            headers={"Authorization": f"Bearer {_production_token()}"},
        )

    assert response.status_code == 200
    assert response.text == "answer"
    assert audit.list_events()[0].cache_hit is False


@pytest.mark.asyncio
async def test_successful_query_response_survives_audit_write_failure(tmp_path: Path):
    app = _production_query_app(
        tmp_path,
        audit_repo=FailingAuditRepository(),
        history_repo=SQLiteUserHistoryRepository(tmp_path / "history.db"),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/query",
            json={"query": "public api"},
            headers={"Authorization": f"Bearer {_production_token()}"},
        )

    assert response.status_code == 200
    assert response.text == "answer"


def test_query_request_rejects_model_override():
    try:
        QueryRequest(query="public api", override_model="attacker-controlled-name")
        assert False
    except ValueError as exc:
        assert "override_model" in str(exc)


def test_query_request_rejects_unknown_response_mode():
    try:
        QueryRequest(query="public api", response_mode="benchmark-special")
        assert False
    except ValueError as exc:
        assert "response_mode" in str(exc)


@pytest.mark.asyncio
async def test_metrics_endpoint_requires_configured_token(tmp_path: Path):
    app = create_app(
        access_matrix_repo=SQLiteAccessMatrixRepository(tmp_path / "access.db"),
        scope_repo=SQLiteScopeRepository(tmp_path / "access.db"),
        cache_repo=InMemorySemanticCacheRepository(),
        rate_limit_repo=TokenBucketRateLimitRepository(),
        audit_repo=SQLiteAuditRepository(tmp_path / "audit.db"),
        metrics_token="metrics-secret",
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        denied = await client.get("/metrics")
        allowed = await client.get("/metrics", headers={"Authorization": "Bearer metrics-secret"})

    assert denied.status_code == 404
    assert allowed.status_code == 200
    assert "cis_circuit_breaker_open" in allowed.text


@pytest.mark.asyncio
async def test_query_without_authorized_scope_is_blocked_and_audited(tmp_path: Path):
    store = SQLiteUnifiedStore(tmp_path / "index.db", HashingEmbeddingProvider(dimensions=16))
    access = SQLiteAccessMatrixRepository(tmp_path / "access.db")
    access.set_user_tier("user-1", AccessTier.T3)
    scopes = SQLiteScopeRepository(tmp_path / "access.db")
    audit = SQLiteAuditRepository(tmp_path / "audit.db")
    token = _token(
        {
            "sub": "user-1",
            "groups": ["no-scope"],
            "iss": "cis",
            "aud": "developers",
            "exp": int(time.time()) + 60,
        }
    )
    app = create_app(
        access_matrix_repo=access,
        scope_repo=scopes,
        cache_repo=InMemorySemanticCacheRepository(),
        rate_limit_repo=TokenBucketRateLimitRepository(),
        audit_repo=audit,
        retrieval_store=store,
        model_hook=RecordingModelHook(),
        jwt_verifier=HS256JWTVerifier("secret", issuer="cis", audience="developers"),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/query", json={"query": "anything"}, headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 403
    assert audit.list_events()[0].rbac_blocked is True


@pytest.mark.asyncio
async def test_query_uses_retrieval_fallback_when_circuit_breaker_is_open(tmp_path: Path):
    store = SQLiteUnifiedStore(tmp_path / "index.db", HashingEmbeddingProvider(dimensions=16))
    store.upsert_artifacts(
        [
            ArtifactRecord(
                "repo-a:indexer",
                "repo-a",
                "indexer.py",
                "python",
                "class RepositoryIndexer index_repository _iter_files _index_file upsert_artifacts",
                3,
                "L-1",
                "RepositoryIndexer",
                kind="class-implementation",
            )
        ]
    )
    access = SQLiteAccessMatrixRepository(tmp_path / "access.db")
    access.set_user_tier("user-1", AccessTier.T3)
    scopes = SQLiteScopeRepository(tmp_path / "access.db")
    scopes.grant_group_scope("platform", "repo-a")
    audit = SQLiteAuditRepository(tmp_path / "audit.db")

    class UnavailableModelHook(ModelHook):
        def __init__(self):
            self.inference_engine_id = "unavailable-engine"

        async def generate_stream(self, prompt: str):
            yield "\n[Inference Error: local inference engine unavailable]"

    token = _token(
        {
            "sub": "user-1",
            "groups": ["platform"],
            "iss": "cis",
            "aud": "developers",
            "exp": int(time.time()) + 60,
        }
    )
    app = create_app(
        access_matrix_repo=access,
        scope_repo=scopes,
        cache_repo=InMemorySemanticCacheRepository(),
        rate_limit_repo=TokenBucketRateLimitRepository(),
        audit_repo=audit,
        retrieval_store=store,
        model_hook=UnavailableModelHook(),
        jwt_verifier=HS256JWTVerifier("secret", issuer="cis", audience="developers"),
    )
    global_circuit_breaker.state = "OPEN"
    global_circuit_breaker.failure_count = 3

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/query",
                json={"query": "What does RepositoryIndexer do?"},
                headers={"Authorization": f"Bearer {token}"},
            )
    finally:
        global_circuit_breaker.state = "CLOSED"
        global_circuit_breaker.failure_count = 0

    assert response.status_code == 200
    assert "RepositoryIndexer's retrieved implementation indexes repositories" in response.text
    assert "Inference Error" not in response.text
    assert audit.list_events()[0].cache_hit is False
