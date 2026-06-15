from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import socket
import time
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncGenerator, Optional

import uvicorn
from fastapi.responses import FileResponse

ROOT = Path(__file__).resolve().parent

from src.ingestion.indexer import RepositoryIndexer
from src.retrieval.database import HashingEmbeddingProvider, SQLiteUnifiedStore
from src.gateway.main import create_app, global_circuit_breaker
from src.gateway.models import AccessTier
from src.gateway.repositories import (
    SQLiteAccessMatrixRepository,
    SQLiteAuditRepository,
    SQLiteScopeRepository,
    SQLiteUserHistoryRepository,
)
from src.gateway.security import HS256JWTVerifier
from src.gateway.services import InMemorySemanticCacheRepository, TokenBucketRateLimitRepository
from src.retrieval.context_summary import RetrievedContextSummarizer


@dataclass(frozen=True)
class DemoContextBlock:
    summary: str


class LocalDemoCompletionClient:
    CONTEXT_BLOCK_PATTERN = re.compile(
        r"^--- File: (?P<file>.*?) \| Language: (?P<language>.*?) \| Tier: (?P<tier>\d+) ---\n"
        r"(?P<text>.*?)(?=^--- File: |^Query: |\Z)",
        re.MULTILINE | re.DOTALL,
    )
    SUMMARY_PATTERN = re.compile(r"^\[\d+\]\s+(?P<summary>.+)$", re.MULTILINE)

    def __init__(self, max_context_files: int = 5, max_preview_lines: int = 3, chunk_size: int = 96):
        self.max_context_files = max_context_files
        self.max_preview_lines = max_preview_lines
        self.chunk_size = chunk_size

    async def text_generation(
        self,
        prompt: str,
        max_new_tokens: int = 512,
        stream: bool = True,
        details: bool = False,
    ) -> AsyncGenerator[str, None]:
        response = self.create_response(prompt)
        for chunk in self._chunks(response):
            yield chunk

    def create_response(self, prompt: str) -> str:
        query = self._extract_query(prompt)
        context_blocks = self._extract_context_blocks(prompt)
        lines = [
            "Local demo response",
            "",
            f"Query: {query}",
            "",
        ]
        if context_blocks:
            lines.append("Retrieved summaries:")
            for block in context_blocks:
                lines.append(f"- {block.summary}")
        else:
            lines.append("No indexed context matched this query.")
        lines.extend(
            [
                "",
                "Generated locally from indexed retrieval context so the demo does not require an external inference server.",
            ]
        )
        return "\n".join(lines)

    @staticmethod
    def _extract_query(prompt: str) -> str:
        matches = re.findall(r"^Query:\s*(.*)$", prompt, re.MULTILINE)
        return matches[-1] if matches else "unknown query"

    def _extract_context_blocks(self, prompt: str) -> list[DemoContextBlock]:
        blocks: list[DemoContextBlock] = []
        for match in self.SUMMARY_PATTERN.finditer(prompt):
            blocks.append(DemoContextBlock(summary=match.group("summary").strip()))
            if len(blocks) >= self.max_context_files:
                return blocks

        seen: set[str] = set()
        summarizer = RetrievedContextSummarizer()
        for match in self.CONTEXT_BLOCK_PATTERN.finditer(prompt):
            file_path = match.group("file")
            if file_path in seen:
                continue
            seen.add(file_path)
            summary = summarizer.summarize_chunk(
                {
                    "symbol_name": Path(file_path).stem,
                    "language": match.group("language"),
                    "tier": match.group("tier"),
                    "text": match.group("text"),
                    "kind": "artifact",
                },
                len(blocks) + 1,
            )
            blocks.append(
                DemoContextBlock(
                    summary=summary,
                )
            )
            if len(blocks) >= self.max_context_files:
                break
        return blocks

    def _preview_lines(self, text: str) -> list[str]:
        lines = []
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            lines.append(line[:140])
            if len(lines) >= self.max_preview_lines:
                break
        return lines

    def _chunks(self, response: str) -> list[str]:
        return [response[index:index + self.chunk_size] for index in range(0, len(response), self.chunk_size)]


class LocalDemoModelHook:
    inference_engine_id = "local-demo"

    def __init__(self, client: Optional[LocalDemoCompletionClient] = None, circuit_breaker=None):
        self.client = client or LocalDemoCompletionClient()
        self.circuit_breaker = circuit_breaker

    async def generate_stream(self, prompt: str) -> AsyncGenerator[str, None]:
        try:
            async for chunk in self.client.text_generation(prompt):
                yield chunk
            if self.circuit_breaker:
                self.circuit_breaker.record_success()
        except Exception:
            if self.circuit_breaker:
                self.circuit_breaker.record_failure()
            raise


def should_use_local_demo_inference() -> bool:
    value = os.environ.get("CIS_LOCAL_USE_LLAMA_CPP", "").strip().lower()
    return value not in {"1", "true", "yes", "on"}


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
    model_hook = LocalDemoModelHook(circuit_breaker=global_circuit_breaker) if should_use_local_demo_inference() else None

    app = create_app(
        access_matrix_repo=access,
        scope_repo=scope,
        cache_repo=InMemorySemanticCacheRepository(),
        rate_limit_repo=TokenBucketRateLimitRepository(),
        audit_repo=SQLiteAuditRepository(data_dir / "audit.db"),
        history_repo=SQLiteUserHistoryRepository(data_dir / "history.db"),
        retrieval_store=store,
        jwt_verifier=HS256JWTVerifier(secret, issuer="cis-local", audience="developers"),
        model_hook=model_hook,
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
    print(f"Inference: {'local-demo' if should_use_local_demo_inference() else 'llama.cpp'}")
    uvicorn.run(build_app(), host=host, port=port, log_level="info")
