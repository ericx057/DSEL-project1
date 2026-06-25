from __future__ import annotations

import math
import threading
from collections import Counter, defaultdict
from typing import Iterable


class GatewayMetrics:
    _BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)
    _FALLBACK_FLAGS = {"fallback_used", "no_retrieval_context", "clarification_requested"}

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._http_requests: Counter[tuple[str, str, str]] = Counter()
        self._http_duration_buckets: dict[tuple[str, str], list[int]] = defaultdict(
            lambda: [0 for _ in (*self._BUCKETS, math.inf)]
        )
        self._http_duration_sum: Counter[tuple[str, str]] = Counter()
        self._http_duration_count: Counter[tuple[str, str]] = Counter()
        self._query_cache: Counter[str] = Counter()
        self._query_fallback: Counter[str] = Counter()

    def observe_http_request(self, method: str, path: str, status: int, duration_seconds: float) -> None:
        labels = (method.upper(), path, str(status))
        duration_key = (method.upper(), path)
        with self._lock:
            self._http_requests[labels] += 1
            self._http_duration_sum[duration_key] += max(0.0, duration_seconds)
            self._http_duration_count[duration_key] += 1
            for index, bucket in enumerate((*self._BUCKETS, math.inf)):
                if duration_seconds <= bucket:
                    self._http_duration_buckets[duration_key][index] += 1

    def record_query(self, cache_status: str, quality_flags: Iterable[str]) -> None:
        with self._lock:
            self._query_cache[cache_status] += 1
            for flag in quality_flags:
                if flag in self._FALLBACK_FLAGS:
                    self._query_fallback[flag] += 1

    def render_prometheus(self) -> str:
        with self._lock:
            lines = [
                "# HELP cis_http_requests_total HTTP requests by method, path, and status.",
                "# TYPE cis_http_requests_total counter",
            ]
            for (method, path, status), value in sorted(self._http_requests.items()):
                lines.append(
                    f'cis_http_requests_total{{method="{self._label(method)}",path="{self._label(path)}",status="{self._label(status)}"}} {value}'
                )

            lines.extend(
                [
                    "# HELP cis_http_request_duration_seconds HTTP request duration in seconds.",
                    "# TYPE cis_http_request_duration_seconds histogram",
                ]
            )
            for method, path in sorted(self._http_duration_count):
                counts = self._http_duration_buckets[(method, path)]
                for bucket, value in zip((*self._BUCKETS, math.inf), counts):
                    le = "+Inf" if math.isinf(bucket) else f"{bucket:g}"
                    lines.append(
                        f'cis_http_request_duration_seconds_bucket{{method="{self._label(method)}",path="{self._label(path)}",le="{le}"}} {value}'
                    )
                lines.append(
                    f'cis_http_request_duration_seconds_sum{{method="{self._label(method)}",path="{self._label(path)}"}} {self._http_duration_sum[(method, path)]:.6f}'
                )
                lines.append(
                    f'cis_http_request_duration_seconds_count{{method="{self._label(method)}",path="{self._label(path)}"}} {self._http_duration_count[(method, path)]}'
                )

            lines.extend(
                [
                    "# HELP cis_query_cache_total Query results by cache status.",
                    "# TYPE cis_query_cache_total counter",
                ]
            )
            for status, value in sorted(self._query_cache.items()):
                lines.append(f'cis_query_cache_total{{status="{self._label(status)}"}} {value}')

            lines.extend(
                [
                    "# HELP cis_query_fallback_total Query fallback responses by policy reason.",
                    "# TYPE cis_query_fallback_total counter",
                ]
            )
            for reason, value in sorted(self._query_fallback.items()):
                lines.append(f'cis_query_fallback_total{{reason="{self._label(reason)}"}} {value}')

            return "\n".join(lines)

    @staticmethod
    def _label(value: str) -> str:
        return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')
