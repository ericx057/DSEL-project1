from __future__ import annotations

import os
from pathlib import Path

from fastapi.responses import FileResponse

from src.retrieval.database import HashingEmbeddingProvider, SQLiteUnifiedStore
from src.retrieval.embeddings import LocalTransformersEmbeddingProvider
from src.gateway.main import create_app
from src.gateway.models import AccessTier
from src.gateway.repositories import (
    SQLiteAccessMatrixRepository,
    SQLiteAuditRepository,
    SQLiteScopeRepository,
    SQLiteUserHistoryRepository,
)
from src.gateway.security import HS256JWTVerifier
from src.gateway.services import InMemorySemanticCacheRepository, TokenBucketRateLimitRepository
from src.gateway.services import RedisSemanticCacheRepository


def build_app():
    data_dir = Path(os.environ.get("CIS_DATA_DIR", "/data")).resolve()
    data_dir.mkdir(parents=True, exist_ok=True)

    repository_name = os.environ.get("CIS_REPOSITORY_NAME", "default")
    jwt_secret = os.environ["CIS_JWT_SECRET"]
    issuer = os.environ.get("CIS_JWT_ISSUER")
    audience = os.environ.get("CIS_JWT_AUDIENCE")
    metrics_token = os.environ["CIS_METRICS_TOKEN"]

    embedding_backend = os.environ.get("CIS_EMBEDDING_BACKEND", "nomic").lower()
    embedding_provider = (
        HashingEmbeddingProvider()
        if embedding_backend == "hashing"
        else LocalTransformersEmbeddingProvider(
            os.environ.get("CIS_EMBEDDING_MODEL", "nomic-ai/nomic-embed-text-v1.5"),
            trust_remote_code=os.environ.get("CIS_EMBEDDING_TRUST_REMOTE_CODE", "false").lower() == "true",
        )
    )

    store = SQLiteUnifiedStore(data_dir / "index.db", embedding_provider)

    access = SQLiteAccessMatrixRepository(data_dir / "access.db")
    default_user = os.environ.get("CIS_BOOTSTRAP_USER")
    if default_user:
        access.set_user_tier(default_user, AccessTier(os.environ.get("CIS_BOOTSTRAP_TIER", AccessTier.T1.value)))

    scope = SQLiteScopeRepository(data_dir / "access.db")
    bootstrap_group = os.environ.get("CIS_BOOTSTRAP_GROUP")
    if bootstrap_group:
        scope.grant_group_scope(bootstrap_group, repository_name)

    redis_url = os.environ.get("CIS_REDIS_URL")
    cache_repo = RedisSemanticCacheRepository(redis_url) if redis_url else InMemorySemanticCacheRepository()

    app = create_app(
        access_matrix_repo=access,
        scope_repo=scope,
        cache_repo=cache_repo,
        rate_limit_repo=TokenBucketRateLimitRepository(),
        audit_repo=SQLiteAuditRepository(data_dir / "audit.db"),
        history_repo=SQLiteUserHistoryRepository(data_dir / "history.db"),
        retrieval_store=store,
        jwt_verifier=HS256JWTVerifier(jwt_secret, issuer=issuer, audience=audience),
        metrics_token=metrics_token,
    )

    frontend_path = Path(os.environ.get("CIS_FRONTEND_PATH", "/app/src/frontend/index.html")).resolve()

    @app.get("/")
    async def serve_frontend():
        return FileResponse(frontend_path)

    return app


app = build_app()
