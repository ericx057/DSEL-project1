from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from src.gateway.models import AccessTier


@dataclass(frozen=True)
class TaskSpec:
    query: str
    user_id: str
    access_tier: AccessTier
    repo_scopes: List[str]
    model_id: str
    response_mode: str = "answer"
    stream: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RetrievalPacket:
    artifacts: List[Dict[str, Any]]
    summaries: List[str]
    timings_ms: Dict[str, float]
    index_fingerprint: str
    policy_version: str

    @classmethod
    def empty(cls, index_fingerprint: str, policy_version: str = "") -> "RetrievalPacket":
        return cls(
            artifacts=[],
            summaries=[],
            timings_ms={},
            index_fingerprint=index_fingerprint,
            policy_version=policy_version,
        )


@dataclass(frozen=True)
class HarnessResult:
    response: str
    cache_status: str
    trace_id: str
    timings_ms: Dict[str, float]
    quality_flags: List[str]
    inference_engine_used: str
