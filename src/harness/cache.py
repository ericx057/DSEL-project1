from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass(frozen=True)
class HarnessCacheKey:
    normalized_query: str
    access_tier: str
    repo_scopes: Tuple[str, ...]
    response_mode: str
    model_id: str
    index_fingerprint: str
    policy_version: str

    def digest(self) -> str:
        payload = {
            "access_tier": self.access_tier,
            "index_fingerprint": self.index_fingerprint,
            "model_id": self.model_id,
            "normalized_query": self.normalized_query,
            "policy_version": self.policy_version,
            "repo_scopes": list(self.repo_scopes),
            "response_mode": self.response_mode,
        }
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CachedResponse:
    response: str
    policy_version: str
    model_id: str
    index_fingerprint: str
    quality_flags: List[str] = field(default_factory=list)
    schema: str = "harness.cached_response"
    version: int = 1

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_json(cls, text: Optional[str]) -> Optional["CachedResponse"]:
        if not text:
            return None
        try:
            payload: Dict[str, Any] = json.loads(text)
        except (TypeError, json.JSONDecodeError):
            return None
        if payload.get("schema") != "harness.cached_response" or payload.get("version") != 1:
            return None
        response = payload.get("response")
        policy_version = payload.get("policy_version")
        model_id = payload.get("model_id")
        index_fingerprint = payload.get("index_fingerprint")
        if not all(isinstance(value, str) for value in (response, policy_version, model_id, index_fingerprint)):
            return None
        flags = payload.get("quality_flags", [])
        if not isinstance(flags, list):
            flags = []
        return cls(
            response=response,
            policy_version=policy_version,
            model_id=model_id,
            index_fingerprint=index_fingerprint,
            quality_flags=[str(flag) for flag in flags],
        )
