from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional

from src.gateway.services import CircuitBreaker
from src.retrieval.database import UnifiedStore


@dataclass(frozen=True)
class DependencyStatus:
    ok: bool
    detail: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "detail": self.detail, "metadata": dict(self.metadata)}


@dataclass(frozen=True)
class ReadinessReport:
    ok: bool
    checks: Mapping[str, DependencyStatus]

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": "ready" if self.ok else "not_ready",
            "checks": {name: status.to_dict() for name, status in self.checks.items()},
        }


class ReadinessProbe:
    def __init__(
        self,
        *,
        store: Optional[UnifiedStore],
        cache: Any,
        trace_recorder: Any,
        circuit_breaker: CircuitBreaker,
        require_indexed_store: bool = True,
    ):
        self.store = store
        self.cache = cache
        self.trace_recorder = trace_recorder
        self.circuit_breaker = circuit_breaker
        self.require_indexed_store = require_indexed_store

    async def check(self) -> ReadinessReport:
        checks = {
            "retrieval_store": self._check_store(),
            "cache": await self._check_optional_ping(self.cache, "cache backend is reachable"),
            "trace": await self._check_optional_ping(self.trace_recorder, "trace recorder is reachable"),
            "circuit_breaker": self._check_circuit_breaker(),
        }
        return ReadinessReport(ok=all(status.ok for status in checks.values()), checks=checks)

    def _check_store(self) -> DependencyStatus:
        if self.store is None:
            return DependencyStatus(False, "retrieval store is not configured")
        try:
            stats = dict(self.store.index_stats())
            fingerprint = self.store.index_fingerprint()
        except Exception as exc:
            return DependencyStatus(False, "retrieval store is unavailable", {"error": type(exc).__name__})

        artifact_count = int(stats.get("artifact_count") or 0)
        metadata = {**stats, "index_fingerprint": fingerprint}
        if not fingerprint or fingerprint == "unknown-index":
            return DependencyStatus(False, "retrieval store does not expose a usable index fingerprint", metadata)
        if self.require_indexed_store and artifact_count <= 0:
            return DependencyStatus(False, "retrieval store has no indexed artifacts", metadata)
        return DependencyStatus(True, "retrieval store is indexed", metadata)

    async def _check_optional_ping(self, dependency: Any, ok_detail: str) -> DependencyStatus:
        if dependency is None:
            return DependencyStatus(False, "dependency is not configured")
        ping = getattr(dependency, "ping", None) or getattr(dependency, "health_check", None)
        if ping is None:
            return DependencyStatus(True, "dependency has no explicit ping; object is configured")
        try:
            result = ping()
            if inspect.isawaitable(result):
                result = await result
        except Exception as exc:
            return DependencyStatus(False, "dependency ping failed", {"error": type(exc).__name__})
        if result is False:
            return DependencyStatus(False, "dependency ping returned false")
        return DependencyStatus(True, ok_detail)

    def _check_circuit_breaker(self) -> DependencyStatus:
        state = self.circuit_breaker.state
        metadata = {"state": state, "failure_count": self.circuit_breaker.failure_count}
        if state == "OPEN":
            return DependencyStatus(False, "inference circuit breaker is open", metadata)
        return DependencyStatus(True, "inference circuit breaker accepts traffic", metadata)
