import base64
import hashlib
import hmac
import json
import time

import pytest
from fastapi import HTTPException

from src.gateway.security import HS256JWTVerifier


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _token(payload: dict, secret: str = "secret") -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    signing_input = f"{_b64url(json.dumps(header, separators=(',', ':')).encode())}.{_b64url(json.dumps(payload, separators=(',', ':')).encode())}"
    signature = hmac.new(secret.encode(), signing_input.encode(), hashlib.sha256).digest()
    return f"{signing_input}.{_b64url(signature)}"


def test_hs256_jwt_verifier_returns_authenticated_user():
    verifier = HS256JWTVerifier(secret="secret", issuer="cis", audience="developers")
    token = _token(
        {
            "sub": "user-1",
            "groups": ["platform"],
            "iss": "cis",
            "aud": "developers",
            "exp": int(time.time()) + 60,
        }
    )

    user = verifier.verify(f"Bearer {token}")

    assert user.id == "user-1"
    assert user.groups == ["platform"]


def test_hs256_jwt_verifier_rejects_tampered_token():
    verifier = HS256JWTVerifier(secret="secret", issuer="cis", audience="developers")
    token = _token(
        {
            "sub": "user-1",
            "groups": ["platform"],
            "iss": "cis",
            "aud": "developers",
            "exp": int(time.time()) + 60,
        }
    )
    header, payload, signature = token.split(".")
    tampered_payload = _b64url(
        json.dumps(
            {
                "sub": "user-2",
                "groups": ["platform"],
                "iss": "cis",
                "aud": "developers",
                "exp": int(time.time()) + 60,
            },
            separators=(",", ":"),
        ).encode()
    )
    tampered = f"{header}.{tampered_payload}.{signature}"

    with pytest.raises(HTTPException) as exc:
        verifier.verify(f"Bearer {tampered}")

    assert exc.value.status_code == 401


def test_hs256_jwt_verifier_rejects_expired_token():
    verifier = HS256JWTVerifier(secret="secret", issuer="cis", audience="developers")
    token = _token(
        {
            "sub": "user-1",
            "groups": ["platform"],
            "iss": "cis",
            "aud": "developers",
            "exp": int(time.time()) - 1,
        }
    )

    with pytest.raises(HTTPException) as exc:
        verifier.verify(f"Bearer {token}")

    assert exc.value.status_code == 401
