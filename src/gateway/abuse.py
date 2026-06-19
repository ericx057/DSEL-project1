from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping, Optional

from fastapi import HTTPException
from fastapi.responses import JSONResponse


def _positive_int_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    value = int(raw)
    if value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


@dataclass(frozen=True)
class AbuseProtectionSettings:
    max_request_bytes: int = 65536
    max_query_chars: int = 8000

    @classmethod
    def from_env(cls) -> "AbuseProtectionSettings":
        return cls(
            max_request_bytes=_positive_int_env("CIS_MAX_REQUEST_BYTES", cls.max_request_bytes),
            max_query_chars=_positive_int_env("CIS_QUERY_MAX_CHARS", cls.max_query_chars),
        )


class AbuseProtector:
    def __init__(self, settings: AbuseProtectionSettings):
        self.settings = settings

    @classmethod
    def from_env(cls) -> "AbuseProtector":
        return cls(AbuseProtectionSettings.from_env())

    def reject_request_body(self, headers: Mapping[str, str]) -> Optional[JSONResponse]:
        content_length = headers.get("content-length")
        if not content_length:
            return None
        try:
            body_bytes = int(content_length)
        except ValueError:
            return JSONResponse({"detail": "Invalid Content-Length"}, status_code=400)
        if body_bytes > self.settings.max_request_bytes:
            return JSONResponse({"detail": "Request body too large"}, status_code=413)
        return None

    def ensure_query_allowed(self, query: str) -> None:
        if len(query) > self.settings.max_query_chars:
            raise HTTPException(status_code=413, detail="Query too large")
