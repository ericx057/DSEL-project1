from __future__ import annotations

import json
import sqlite3
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Protocol


@dataclass(frozen=True)
class TraceRecord:
    trace_id: str
    user_id: str
    query: str
    repo_scopes: List[str]
    access_tier: str
    model_id: str
    cache_status: str
    retrieval_ids: List[str]
    prompt_summary: str
    response: str
    quality_flags: List[str]
    timings_ms: Dict[str, float]
    created_at: float = field(default_factory=time.time)


class TraceRecorder(Protocol):
    def new_trace_id(self) -> str:
        ...

    def record(self, record: TraceRecord) -> None:
        ...


class InMemoryTraceRecorder:
    def __init__(self):
        self.records: List[TraceRecord] = []

    def new_trace_id(self) -> str:
        return uuid.uuid4().hex

    def record(self, record: TraceRecord) -> None:
        self.records.append(record)


class SQLiteTraceRecorder:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self._connection = sqlite3.connect(self.db_path, check_same_thread=False)
        self._init_schema()

    def new_trace_id(self) -> str:
        return uuid.uuid4().hex

    def record(self, record: TraceRecord) -> None:
        payload = asdict(record)
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO harness_traces(
                    trace_id, user_id, query, repo_scopes, access_tier, model_id,
                    cache_status, retrieval_ids, prompt_summary, response,
                    quality_flags, timings_ms, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.trace_id,
                    record.user_id,
                    record.query,
                    json.dumps(record.repo_scopes, sort_keys=True),
                    record.access_tier,
                    record.model_id,
                    record.cache_status,
                    json.dumps(record.retrieval_ids, sort_keys=True),
                    record.prompt_summary,
                    record.response,
                    json.dumps(record.quality_flags, sort_keys=True),
                    json.dumps(payload["timings_ms"], sort_keys=True),
                    record.created_at,
                ),
            )

    def _init_schema(self) -> None:
        with self._connection:
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS harness_traces (
                    trace_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    query TEXT NOT NULL,
                    repo_scopes TEXT NOT NULL,
                    access_tier TEXT NOT NULL,
                    model_id TEXT NOT NULL,
                    cache_status TEXT NOT NULL,
                    retrieval_ids TEXT NOT NULL,
                    prompt_summary TEXT NOT NULL,
                    response TEXT NOT NULL,
                    quality_flags TEXT NOT NULL,
                    timings_ms TEXT NOT NULL,
                    created_at REAL NOT NULL
                )
                """
            )
