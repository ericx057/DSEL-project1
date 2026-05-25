from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any, Dict, Iterable, Optional

from fastapi import HTTPException

from src.gateway.models import User


class HS256JWTVerifier:
    def __init__(self, secret: str, issuer: Optional[str] = None, audience: Optional[str] = None):
        if not secret:
            raise ValueError("JWT secret must not be empty")
        self.secret = secret.encode("utf-8")
        self.issuer = issuer
        self.audience = audience

    def verify(self, authorization: str) -> User:
        token = self._extract_bearer_token(authorization)
        try:
            header_b64, payload_b64, signature_b64 = token.split(".")
            header = self._decode_json(header_b64)
            payload = self._decode_json(payload_b64)
        except ValueError as exc:
            raise HTTPException(status_code=401, detail="Invalid JWT format") from exc

        if header.get("alg") != "HS256":
            raise HTTPException(status_code=401, detail="Unsupported JWT algorithm")

        signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
        expected = hmac.new(self.secret, signing_input, hashlib.sha256).digest()
        actual = self._decode_segment(signature_b64)
        if not hmac.compare_digest(expected, actual):
            raise HTTPException(status_code=401, detail="Invalid JWT signature")

        self._validate_claims(payload)
        groups = payload.get("groups", [])
        if isinstance(groups, str):
            groups = [groups]
        if not isinstance(groups, list):
            groups = []
        return User(id=str(payload["sub"]), groups=[str(group) for group in groups])

    def _validate_claims(self, payload: Dict[str, Any]) -> None:
        if not payload.get("sub"):
            raise HTTPException(status_code=401, detail="JWT missing subject")
        if "exp" not in payload or int(payload["exp"]) < int(time.time()):
            raise HTTPException(status_code=401, detail="JWT expired")
        if self.issuer and payload.get("iss") != self.issuer:
            raise HTTPException(status_code=401, detail="Invalid JWT issuer")
        if self.audience:
            aud = payload.get("aud")
            audiences: Iterable[str]
            if isinstance(aud, list):
                audiences = [str(item) for item in aud]
            else:
                audiences = [str(aud)]
            if self.audience not in audiences:
                raise HTTPException(status_code=401, detail="Invalid JWT audience")

    @staticmethod
    def _extract_bearer_token(authorization: str) -> str:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise HTTPException(status_code=401, detail="Authorization header must be Bearer JWT")
        return token

    @staticmethod
    def _decode_json(segment: str) -> Dict[str, Any]:
        return json.loads(HS256JWTVerifier._decode_segment(segment).decode("utf-8"))

    @staticmethod
    def _decode_segment(segment: str) -> bytes:
        padding = "=" * (-len(segment) % 4)
        return base64.urlsafe_b64decode(segment + padding)
