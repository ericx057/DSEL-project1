from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from typing import Any


DEFAULT_HOST_PORT = 18080
JWT_SECRET = "ci-smoke-secret"
JWT_ISSUER = "cis"
JWT_AUDIENCE = "developers"
METRICS_TOKEN = "ci-smoke-metrics-token"
SMOKE_USER = "ci-user"
SMOKE_GROUP = "ci-group"
SMOKE_REPOSITORY = "project1"


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def create_hs256_token(
    *,
    subject: str,
    groups: list[str],
    secret: str,
    issuer: str,
    audience: str,
    lifetime_seconds: int,
) -> str:
    now = int(time.time())
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": subject,
        "groups": groups,
        "iss": issuer,
        "aud": audience,
        "iat": now,
        "exp": now + lifetime_seconds,
    }
    signing_input = ".".join(
        [
            _b64url(json.dumps(header, separators=(",", ":"), sort_keys=True).encode()),
            _b64url(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()),
        ]
    )
    signature = hmac.new(secret.encode(), signing_input.encode(), hashlib.sha256).digest()
    return f"{signing_input}.{_b64url(signature)}"


def decode_unverified_payload(token: str) -> dict[str, Any]:
    payload = token.split(".")[1]
    padding = "=" * (-len(payload) % 4)
    return json.loads(base64.urlsafe_b64decode((payload + padding).encode()))


class SmokeHarness:
    def __init__(self, *, image: str, host_port: int = DEFAULT_HOST_PORT) -> None:
        self.image = image
        self.host_port = host_port
        self.container_name = f"cis-smoke-{uuid.uuid4().hex[:12]}"

    def docker_run_command(self, volume_name: str) -> list[str]:
        return [
            "docker",
            "run",
            "-d",
            "--name",
            self.container_name,
            "-p",
            f"{self.host_port}:8000",
            "-v",
            f"{volume_name}:/data",
            "-e",
            "CIS_DATA_DIR=/data",
            "-e",
            f"CIS_REPOSITORY_NAME={SMOKE_REPOSITORY}",
            "-e",
            f"CIS_JWT_SECRET={JWT_SECRET}",
            "-e",
            f"CIS_JWT_ISSUER={JWT_ISSUER}",
            "-e",
            f"CIS_JWT_AUDIENCE={JWT_AUDIENCE}",
            "-e",
            f"CIS_METRICS_TOKEN={METRICS_TOKEN}",
            "-e",
            "CIS_INFERENCE_PROVIDER=openrouter",
            "-e",
            "CIS_OPENROUTER_API_KEY=",
            "-e",
            "CIS_OPENROUTER_MODEL=~openai/gpt-latest",
            "-e",
            "CIS_OPENROUTER_BASE_URL=https://openrouter.ai/api/v1",
            "-e",
            "CIS_EMBEDDING_BACKEND=hashing",
            "-e",
            f"CIS_BOOTSTRAP_USER={SMOKE_USER}",
            "-e",
            f"CIS_BOOTSTRAP_GROUP={SMOKE_GROUP}",
            "-e",
            "CIS_BOOTSTRAP_TIER=T-3",
            self.image,
        ]

    def run(self) -> None:
        volume_name = f"cis-smoke-data-{uuid.uuid4().hex[:12]}"
        container_started = False
        try:
            run(["docker", "volume", "create", volume_name])
            self.seed_index(volume_name)
            run(self.docker_run_command(volume_name))
            container_started = True
            self.wait_for_json("/health", expected_status=200, timeout_seconds=60)
            ready = self.wait_for_json("/ready", expected_status=200, timeout_seconds=60)
            if ready.get("status") != "ready":
                raise RuntimeError(f"Readiness did not report ready: {ready}")
            metrics_text = self.request_text(
                "/metrics",
                headers={"Authorization": f"Bearer {METRICS_TOKEN}"},
                expected_status=200,
            )
            require_text(metrics_text, "cis_circuit_breaker_open")
            query_text = self.request_text(
                "/query",
                method="POST",
                headers={
                    "Authorization": f"Bearer {self.jwt()}",
                    "Content-Type": "application/json",
                },
                body=json.dumps({"query": "What does SmokeEntry do?", "response_mode": "summary"}).encode(),
                expected_status=200,
            )
            require_text(query_text, "SmokeEntry")
            reject_text(query_text, "Inference Error")
            reject_text(query_text, "OpenRouter")
        finally:
            if container_started:
                run(["docker", "rm", "-f", self.container_name], check=False)
            run(["docker", "volume", "rm", "-f", volume_name], check=False)

    def seed_index(self, volume_name: str) -> None:
        code = (
            "from pathlib import Path\n"
            "from src.retrieval.database import ArtifactRecord, HashingEmbeddingProvider, SQLiteUnifiedStore\n"
            "store = SQLiteUnifiedStore(Path('/data/index.db'), HashingEmbeddingProvider(dimensions=16))\n"
            "store.upsert_artifacts([ArtifactRecord("
            "'project1:smoke-entry', 'project1', 'smoke.py', 'python', "
            "'class SmokeEntry run_smoke load_config publish_result', "
            "3, 'L-1', 'SmokeEntry', kind='class-implementation')])\n"
        )
        run(["docker", "run", "--rm", "-v", f"{volume_name}:/data", self.image, "python", "-c", code])

    def wait_for_json(self, path: str, *, expected_status: int, timeout_seconds: int) -> dict[str, Any]:
        deadline = time.monotonic() + timeout_seconds
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            try:
                return json.loads(self.request_text(path, expected_status=expected_status))
            except Exception as exc:
                last_error = exc
                time.sleep(1)
        raise RuntimeError(f"Timed out waiting for {path}: {last_error}") from last_error

    def request_text(
        self,
        path: str,
        *,
        method: str = "GET",
        headers: dict[str, str] | None = None,
        body: bytes | None = None,
        expected_status: int,
    ) -> str:
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.host_port}{path}",
            data=body,
            headers=headers or {},
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                text = response.read().decode("utf-8")
                if response.status != expected_status:
                    raise RuntimeError(f"{path} returned {response.status}: {text}")
                return text
        except urllib.error.HTTPError as exc:
            text = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"{path} returned {exc.code}: {text}") from exc

    def jwt(self) -> str:
        return create_hs256_token(
            subject=SMOKE_USER,
            groups=[SMOKE_GROUP],
            secret=JWT_SECRET,
            issuer=JWT_ISSUER,
            audience=JWT_AUDIENCE,
            lifetime_seconds=300,
        )


def require_text(text: str, expected: str) -> None:
    if expected not in text:
        raise RuntimeError(f"Expected response to contain {expected!r}, got: {text}")


def reject_text(text: str, rejected: str) -> None:
    if rejected in text:
        raise RuntimeError(f"Response unexpectedly contained {rejected!r}: {text}")


def run(command: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if check and result.returncode != 0:
        raise RuntimeError(
            f"Command failed with exit code {result.returncode}: {' '.join(command)}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )
    return result


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smoke test a built CIS production container.")
    parser.add_argument("--image", required=True, help="Docker image tag to smoke test.")
    parser.add_argument("--host-port", type=int, default=DEFAULT_HOST_PORT, help="Host port mapped to container 8000.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    SmokeHarness(image=args.image, host_port=args.host_port).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
