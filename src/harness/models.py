from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

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
class ClarificationRequest:
    reason: str
    question: str
    suggestions: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "reason": self.reason,
            "question": self.question,
            "suggestions": list(self.suggestions),
        }

    @classmethod
    def from_dict(cls, payload: Any) -> Optional["ClarificationRequest"]:
        if not isinstance(payload, dict):
            return None
        reason = payload.get("reason")
        question = payload.get("question")
        suggestions = payload.get("suggestions", [])
        if not isinstance(reason, str) or not isinstance(question, str):
            return None
        if not isinstance(suggestions, list):
            suggestions = []
        return cls(
            reason=reason,
            question=question,
            suggestions=[str(suggestion) for suggestion in suggestions],
        )


@dataclass(frozen=True)
class HarnessResult:
    response: str
    cache_status: str
    trace_id: str
    timings_ms: Dict[str, float]
    quality_flags: List[str]
    inference_engine_used: str
    clarification: Optional[ClarificationRequest] = None
