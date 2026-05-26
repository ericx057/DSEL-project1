import json
import sqlite3
import threading
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import AsyncGenerator, List, Optional

from src.gateway.models import AccessTier, AuditEvent, HistoryRecord


def _ensure_inference_engine_column(connection: sqlite3.Connection, table: str) -> None:
    columns = {row["name"] for row in connection.execute(f"PRAGMA table_info({table})").fetchall()}
    if "inference_engine_used" in columns:
        return
    if "model_used" in columns:
        connection.execute(f"ALTER TABLE {table} RENAME COLUMN model_used TO inference_engine_used")
        return
    connection.execute(f"ALTER TABLE {table} ADD COLUMN inference_engine_used TEXT NOT NULL DEFAULT 'llama.cpp'")


class AccessMatrixRepository(ABC):
    """Contract for resolving user IDs to access tiers."""
    @abstractmethod
    async def get_user_tier(self, user_id: str) -> AccessTier:
        pass

class ScopeRepository(ABC):
    """Contract for determining allowed repository scopes."""
    @abstractmethod
    async def get_allowed_scopes(self, groups: List[str], query: str) -> List[str]:
        pass

class CacheRepository(ABC):
    """Contract for semantic caching and request coalescing."""
    @abstractmethod
    async def get(self, key: str) -> Optional[str]:
        pass

    @abstractmethod
    async def set(self, key: str, value: str, ttl_seconds: int) -> None:
        pass
        
    @abstractmethod
    async def acquire_lock(self, key: str) -> bool:
        """Attempts to acquire a lock for a pending inference job."""
        pass
        
    @abstractmethod
    async def subscribe(self, key: str) -> AsyncGenerator[str, None]:
        """Subscribes to an ongoing inference job stream."""
        pass
        
    @abstractmethod
    async def publish(self, key: str, chunk: str) -> None:
        """Publishes a stream chunk to waiting subscribers."""
        pass
        
    @abstractmethod
    async def release_lock(self, key: str) -> None:
        """Releases the pending job lock."""
        pass

class RateLimitRepository(ABC):
    """Contract for checking rate limits."""
    @abstractmethod
    async def check_and_consume(self, user_id: str) -> bool:
        pass

class AuditRepository(ABC):
    """Contract for append-only audit logging."""
    @abstractmethod
    async def log_event(self, event: AuditEvent) -> None:
        pass


class UserHistoryRepository(ABC):
    @abstractmethod
    async def add_record(self, record: HistoryRecord) -> None:
        pass

    @abstractmethod
    def list_for_user(self, user_id: str, limit: int = 50) -> List[HistoryRecord]:
        pass


class SQLiteAccessMatrixRepository(AccessMatrixRepository):
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(self.db_path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._init_schema()

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass

    def _init_schema(self) -> None:
        with self._connection:
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS access_matrix (
                    user_id TEXT PRIMARY KEY,
                    tier TEXT NOT NULL
                )
                """
            )

    def set_user_tier(self, user_id: str, tier: AccessTier) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO access_matrix(user_id, tier)
                VALUES (?, ?)
                ON CONFLICT(user_id) DO UPDATE SET tier=excluded.tier
                """,
                (user_id, tier.value),
            )

    async def get_user_tier(self, user_id: str) -> AccessTier:
        row = self._connection.execute(
            "SELECT tier FROM access_matrix WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        return AccessTier(row["tier"]) if row else AccessTier.T1


class SQLiteScopeRepository(ScopeRepository):
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(self.db_path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._init_schema()

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass

    def _init_schema(self) -> None:
        with self._connection:
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS group_scopes (
                    group_name TEXT NOT NULL,
                    repository TEXT NOT NULL,
                    PRIMARY KEY(group_name, repository)
                )
                """
            )

    def grant_group_scope(self, group_name: str, repository: str) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                "INSERT OR IGNORE INTO group_scopes(group_name, repository) VALUES (?, ?)",
                (group_name, repository),
            )

    async def get_allowed_scopes(self, groups: List[str], query: str) -> List[str]:
        if not groups:
            return []
        placeholders = ",".join("?" for _ in groups)
        rows = self._connection.execute(
            f"SELECT DISTINCT repository FROM group_scopes WHERE group_name IN ({placeholders}) ORDER BY repository",
            groups,
        ).fetchall()
        return [row["repository"] for row in rows]


class SQLiteAuditRepository(AuditRepository):
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(self.db_path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._init_schema()

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass

    def _init_schema(self) -> None:
        with self._connection:
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at REAL NOT NULL,
                    user_id TEXT NOT NULL,
                    access_tier TEXT NOT NULL,
                    query_hash TEXT NOT NULL,
                    repo_scope TEXT NOT NULL,
                    inference_engine_used TEXT NOT NULL,
                    latency_ms REAL NOT NULL,
                    cache_hit INTEGER NOT NULL,
                    rbac_blocked INTEGER NOT NULL
                )
                """
            )
            _ensure_inference_engine_column(self._connection, "audit_log")

    async def log_event(self, event: AuditEvent) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO audit_log(
                    created_at, user_id, access_tier, query_hash, repo_scope,
                    inference_engine_used, latency_ms, cache_hit, rbac_blocked
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    time.time(),
                    event.user_id,
                    event.access_tier.value,
                    event.query_hash,
                    json.dumps(event.repo_scope),
                    event.inference_engine_used,
                    event.latency_ms,
                    int(event.cache_hit),
                    int(event.rbac_blocked),
                ),
            )

    def list_events(self) -> List[AuditEvent]:
        rows = self._connection.execute("SELECT * FROM audit_log ORDER BY id ASC").fetchall()
        return [
            AuditEvent(
                user_id=row["user_id"],
                access_tier=AccessTier(row["access_tier"]),
                query_hash=row["query_hash"],
                repo_scope=json.loads(row["repo_scope"]),
                inference_engine_used=row["inference_engine_used"],
                latency_ms=row["latency_ms"],
                cache_hit=bool(row["cache_hit"]),
                rbac_blocked=bool(row["rbac_blocked"]),
            )
            for row in rows
        ]


class SQLiteUserHistoryRepository(UserHistoryRepository):
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(self.db_path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._init_schema()

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass

    def _init_schema(self) -> None:
        with self._connection:
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS user_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    query TEXT NOT NULL,
                    response TEXT NOT NULL,
                    inference_engine_used TEXT NOT NULL,
                    repo_scope TEXT NOT NULL,
                    created_at REAL NOT NULL
                )
                """
            )
            _ensure_inference_engine_column(self._connection, "user_history")
            self._connection.execute("CREATE INDEX IF NOT EXISTS idx_user_history_user ON user_history(user_id)")

    async def add_record(self, record: HistoryRecord) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO user_history(user_id, query, response, inference_engine_used, repo_scope, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    record.user_id,
                    record.query,
                    record.response,
                    record.inference_engine_used,
                    json.dumps(record.repo_scope),
                    record.created_at,
                ),
            )

    def list_for_user(self, user_id: str, limit: int = 50) -> List[HistoryRecord]:
        rows = self._connection.execute(
            "SELECT * FROM user_history WHERE user_id = ? ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
        return [
            HistoryRecord(
                user_id=row["user_id"],
                query=row["query"],
                response=row["response"],
                inference_engine_used=row["inference_engine_used"],
                repo_scope=json.loads(row["repo_scope"]),
                created_at=row["created_at"],
            )
            for row in rows
        ]
