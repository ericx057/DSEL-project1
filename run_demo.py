from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import socket
import time
from pathlib import Path

import uvicorn
from fastapi.responses import FileResponse

ROOT = Path(__file__).resolve().parent

from src.ingestion.indexer import RepositoryIndexer
from src.retrieval.database import HashingEmbeddingProvider, SQLiteUnifiedStore
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

def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def create_dev_token(secret: str, user_id: str = "dev-user", tier: AccessTier = AccessTier.T1) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": user_id,
        "groups": ["engineering"],
        "iss": "cis-local",
        "aud": "developers",
        "exp": int(time.time()) + 8 * 60 * 60,
        "tier": tier.value,
    }
    signing_input = (
        f"{_b64url(json.dumps(header, separators=(',', ':')).encode())}."
        f"{_b64url(json.dumps(payload, separators=(',', ':')).encode())}"
    )
    signature = hmac.new(secret.encode(), signing_input.encode(), hashlib.sha256).digest()
    return f"{signing_input}.{_b64url(signature)}"


def is_port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        return sock.connect_ex((host, port)) == 0


def get_free_port(start_port: int = 8000, max_port: int = 8020, host: str = "127.0.0.1") -> int:
    for port in range(start_port, max_port + 1):
        if not is_port_in_use(port, host):
            return port
    raise RuntimeError(f"All localhost ports between {start_port} and {max_port} are in use.")


def build_app():
    root = ROOT
    data_dir = root / ".cis"
    data_dir.mkdir(exist_ok=True)
    secret = os.environ.get("CIS_LOCAL_JWT_SECRET")
    if not secret:
        raise RuntimeError("Set CIS_LOCAL_JWT_SECRET before starting the local development server.")
    user_id = os.environ.get("CIS_LOCAL_USER", "dev-user")
    tier = AccessTier(os.environ.get("CIS_LOCAL_TIER", AccessTier.T1.value))

    store = SQLiteUnifiedStore(data_dir / "index.db", HashingEmbeddingProvider())
    RepositoryIndexer(store).index_repository("project1", root)

    access = SQLiteAccessMatrixRepository(data_dir / "access.db")
    access.set_user_tier(user_id, tier)
    scope = SQLiteScopeRepository(data_dir / "access.db")
    scope.grant_group_scope("engineering", "project1")

    app = create_app(
        access_matrix_repo=access,
        scope_repo=scope,
        cache_repo=InMemorySemanticCacheRepository(),
        rate_limit_repo=TokenBucketRateLimitRepository(),
        audit_repo=SQLiteAuditRepository(data_dir / "audit.db"),
        history_repo=SQLiteUserHistoryRepository(data_dir / "history.db"),
        retrieval_store=store,
        jwt_verifier=HS256JWTVerifier(secret, issuer="cis-local", audience="developers"),
    )

    @app.get("/")
    async def serve_frontend():
        return FileResponse(root / "src" / "frontend" / "index.html")

    return app


if __name__ == "__main__":
    host = "127.0.0.1"
    port = get_free_port(host=host)
    secret = os.environ.get("CIS_LOCAL_JWT_SECRET")
    if not secret:
        raise RuntimeError("Set CIS_LOCAL_JWT_SECRET before starting the local development server.")
    token = create_dev_token(
        secret,
        user_id=os.environ.get("CIS_LOCAL_USER", "dev-user"),
        tier=AccessTier(os.environ.get("CIS_LOCAL_TIER", AccessTier.T1.value)),
    )
    print("Codebase Intelligence local server")
    print(f"URL: http://{host}:{port}/")
    print(f"Bearer token: {token}")
    uvicorn.run(build_app(), host=host, port=port, log_level="info")
