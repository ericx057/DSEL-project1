from __future__ import annotations

import os
from pathlib import Path

from fastapi.responses import FileResponse

from src.retrieval.database import SQLiteUnifiedStore
from src.retrieval.embedding_config import build_embedding_provider
from src.gateway.main import create_app
from src.gateway.models import AccessTier
from src.gateway.repositories import (
    SQLiteAccessMatrixRepository,
    SQLiteAuditRepository,
    SQLiteScopeRepository,
    SQLiteUserHistoryRepository,
)
from src.gateway.security import HS256JWTVerifier
from src.gateway.services import (
    RedisSemanticCacheRepository,
    RedisTokenBucketRateLimitRepository,
    SQLiteSemanticCacheRepository,
    TokenBucketRateLimitRepository,
)
from src.harness.trace import SQLiteTraceRecorder


def _int_env(name: str, default: int, *, min_value: int = 1) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    value = int(raw)
    if value < min_value:
        raise ValueError(f"{name} must be at least {min_value}")
    return value


def _float_env(name: str, default: float, *, min_value: float = 0.0) -> float:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    value = float(raw)
    if value < min_value:
        raise ValueError(f"{name} must be at least {min_value}")
    return value


def build_app():
    data_dir = Path(os.environ.get("CIS_DATA_DIR", "/data")).resolve()
    data_dir.mkdir(parents=True, exist_ok=True)

    repository_name = os.environ.get("CIS_REPOSITORY_NAME", "default")
    jwt_secret = os.environ["CIS_JWT_SECRET"]
    issuer = os.environ.get("CIS_JWT_ISSUER")
    audience = os.environ.get("CIS_JWT_AUDIENCE")
    metrics_token = os.environ["CIS_METRICS_TOKEN"]

    store = SQLiteUnifiedStore(data_dir / "index.db", build_embedding_provider())

    access = SQLiteAccessMatrixRepository(data_dir / "access.db")
    default_user = os.environ.get("CIS_BOOTSTRAP_USER")
    if default_user:
        access.set_user_tier(default_user, AccessTier(os.environ.get("CIS_BOOTSTRAP_TIER", AccessTier.T1.value)))

    scope = SQLiteScopeRepository(data_dir / "access.db")
    bootstrap_group = os.environ.get("CIS_BOOTSTRAP_GROUP")
    if bootstrap_group:
        scope.grant_group_scope(bootstrap_group, repository_name)

    redis_url = os.environ.get("CIS_REDIS_URL")
    cache_repo = (
        RedisSemanticCacheRepository(redis_url)
        if redis_url
        else SQLiteSemanticCacheRepository(data_dir / "semantic_cache.db")
    )
    rate_limit_settings = {
        "capacity": _int_env("CIS_RATE_LIMIT_CAPACITY", 20),
        "refill_per_minute": _int_env("CIS_RATE_LIMIT_REFILL_PER_MINUTE", 20, min_value=0),
        "base_backoff_seconds": _float_env("CIS_RATE_LIMIT_BASE_BACKOFF_SECONDS", 2.0, min_value=0.001),
        "max_backoff_seconds": _float_env("CIS_RATE_LIMIT_MAX_BACKOFF_SECONDS", 60.0, min_value=0.001),
    }
    rate_limit_repo = (
        RedisTokenBucketRateLimitRepository(redis_url, **rate_limit_settings)
        if redis_url
        else TokenBucketRateLimitRepository(**rate_limit_settings)
    )

    app = create_app(
        access_matrix_repo=access,
        scope_repo=scope,
        cache_repo=cache_repo,
        rate_limit_repo=rate_limit_repo,
        audit_repo=SQLiteAuditRepository(data_dir / "audit.db"),
        history_repo=SQLiteUserHistoryRepository(data_dir / "history.db"),
        retrieval_store=store,
        jwt_verifier=HS256JWTVerifier(jwt_secret, issuer=issuer, audience=audience),
        metrics_token=metrics_token,
        trace_recorder=SQLiteTraceRecorder(data_dir / "traces.db"),
    )

    frontend_path = Path(os.environ.get("CIS_FRONTEND_PATH", "/app/src/frontend/index.html")).resolve()

    @app.get("/")
    async def serve_frontend():
        return FileResponse(frontend_path)

    return app


app = build_app()
