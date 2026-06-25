import time
import hashlib
import asyncio
import inspect
import math
import sqlite3
import threading
from pathlib import Path
from typing import AsyncGenerator, Callable, Dict, List, Optional
from fastapi import HTTPException

from src.gateway.models import AccessTier, User, AuditEvent
from src.gateway.repositories import (
    AccessMatrixRepository,
    ScopeRepository,
    CacheRepository,
    RateLimitRepository,
    AuditRepository
)
from src.gateway.security import HS256JWTVerifier


RESPONSE_CACHE_POLICY_VERSION = "response-policy-v4"

class CircuitBreaker:
    def __init__(self, failure_threshold: int = 3, recovery_timeout: int = 30):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = 0
        self.state = "CLOSED"

    def record_failure(self):
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.failure_count >= self.failure_threshold:
            self.state = "OPEN"

    def record_success(self):
        self.failure_count = 0
        self.state = "CLOSED"

    def is_allowed(self) -> bool:
        if self.state == "CLOSED":
            return True
        if self.state == "OPEN":
            if time.time() - self.last_failure_time > self.recovery_timeout:
                self.state = "HALF_OPEN"
                return True
            return False
        if self.state == "HALF_OPEN":
            return True
        return False

class IAMService:
    def __init__(self, repository: AccessMatrixRepository, jwt_verifier: Optional[HS256JWTVerifier] = None):
        self.repository = repository
        self.jwt_verifier = jwt_verifier

    def decode_token(self, token: str) -> User:
        if self.jwt_verifier:
            return self.jwt_verifier.verify(token)
        raise HTTPException(status_code=500, detail="JWT verifier is not configured")

    async def get_tier(self, user_id: str) -> AccessTier:
        return await self.repository.get_user_tier(user_id)

class ScopingService:
    def __init__(self, repository: ScopeRepository):
        self.repository = repository

    async def resolve_scope(self, user: User, query: str) -> List[str]:
        return await self.repository.get_allowed_scopes(user.groups, query)

class CacheService:
    def __init__(self, repository: CacheRepository):
        self.repository = repository

    def _generate_key(
        self,
        query: str,
        tier: AccessTier,
        scopes: List[str],
        response_mode: str = "answer",
        model_id: str = "default-model",
        index_fingerprint: str = "legacy-index",
        policy_version: str = RESPONSE_CACHE_POLICY_VERSION,
    ) -> str:
        normalized_query = " ".join(query.strip().lower().split())
        raw_key = ":".join(
            [
                policy_version,
                normalized_query,
                tier.value,
                ",".join(sorted(scopes)),
                response_mode,
                model_id,
                index_fingerprint,
            ]
        )
        return hashlib.sha256(raw_key.encode()).hexdigest()

    async def get_cached_response(
        self,
        query: str,
        tier: AccessTier,
        scopes: List[str],
        response_mode: str = "answer",
        model_id: str = "default-model",
        index_fingerprint: str = "legacy-index",
    ) -> Optional[str]:
        key = self._generate_key(query, tier, scopes, response_mode, model_id, index_fingerprint)
        return await self.repository.get(key)

    async def set_cached_response(
        self,
        query: str,
        tier: AccessTier,
        scopes: List[str],
        response: str,
        response_mode: str = "answer",
        model_id: str = "default-model",
        index_fingerprint: str = "legacy-index",
    ) -> None:
        key = self._generate_key(query, tier, scopes, response_mode, model_id, index_fingerprint)
        ttl = 3600 if tier == AccessTier.T3 else 14400
        await self.repository.set(key, response, ttl)

    async def acquire_lock(
        self,
        query: str,
        tier: AccessTier,
        scopes: List[str],
        response_mode: str = "answer",
        model_id: str = "default-model",
        index_fingerprint: str = "legacy-index",
    ) -> bool:
        key = self._generate_key(query, tier, scopes, response_mode, model_id, index_fingerprint)
        return await self.repository.acquire_lock(key)

    async def subscribe(
        self,
        query: str,
        tier: AccessTier,
        scopes: List[str],
        response_mode: str = "answer",
        model_id: str = "default-model",
        index_fingerprint: str = "legacy-index",
    ) -> AsyncGenerator[str, None]:
        key = self._generate_key(query, tier, scopes, response_mode, model_id, index_fingerprint)
        async for chunk in self.repository.subscribe(key):
            yield chunk

    async def publish(
        self,
        query: str,
        tier: AccessTier,
        scopes: List[str],
        chunk: str,
        response_mode: str = "answer",
        model_id: str = "default-model",
        index_fingerprint: str = "legacy-index",
    ) -> None:
        key = self._generate_key(query, tier, scopes, response_mode, model_id, index_fingerprint)
        await self.repository.publish(key, chunk)

    async def release_lock(
        self,
        query: str,
        tier: AccessTier,
        scopes: List[str],
        response_mode: str = "answer",
        model_id: str = "default-model",
        index_fingerprint: str = "legacy-index",
    ) -> None:
        key = self._generate_key(query, tier, scopes, response_mode, model_id, index_fingerprint)
        await self.repository.release_lock(key)

class RateLimitService:
    def __init__(self, repository: RateLimitRepository, circuit_breaker: CircuitBreaker):
        self.repository = repository
        self.circuit_breaker = circuit_breaker

    async def check_rate_limit(self, user_id: str) -> None:
        allowed = await self.repository.check_and_consume(user_id)
        if not allowed:
            retry_after = await self._retry_after(user_id)
            headers = {"Retry-After": str(retry_after)} if retry_after is not None and retry_after > 0 else None
            raise HTTPException(status_code=429, detail="Rate limit exceeded", headers=headers)

    async def _retry_after(self, user_id: str) -> Optional[int]:
        retry_after = getattr(self.repository, "retry_after", None)
        if not callable(retry_after):
            return None
        value = retry_after(user_id)
        if inspect.isawaitable(value):
            value = await value
        if value is None:
            return None
        return max(0, math.ceil(float(value)))

    def check_circuit_breaker(self) -> None:
        if not self.circuit_breaker.is_allowed():
            raise HTTPException(status_code=503, detail="Service Unavailable: Inference engine down")

class AuditService:
    def __init__(self, repository: AuditRepository):
        self.repository = repository

    async def log(self, event: AuditEvent) -> None:
        await self.repository.log_event(event)


class InMemorySemanticCacheRepository(CacheRepository):
    def __init__(self):
        self._cache: Dict[str, tuple[str, float]] = {}
        self._locks: set[str] = set()
        self._streams: Dict[str, List[asyncio.Queue]] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Optional[str]:
        item = self._cache.get(key)
        if not item:
            return None
        value, expires_at = item
        if expires_at < time.time():
            self._cache.pop(key, None)
            return None
        return value

    async def set(self, key: str, value: str, ttl_seconds: int) -> None:
        self._cache[key] = (value, time.time() + ttl_seconds)

    async def acquire_lock(self, key: str) -> bool:
        async with self._lock:
            if key in self._locks:
                return False
            self._locks.add(key)
            self._streams[key] = []
            return True

    async def subscribe(self, key: str) -> AsyncGenerator[str, None]:
        queue: asyncio.Queue = asyncio.Queue()
        async with self._lock:
            self._streams.setdefault(key, []).append(queue)
        while True:
            chunk = await queue.get()
            if chunk is None:
                break
            yield chunk

    async def publish(self, key: str, chunk: str) -> None:
        for queue in self._streams.get(key, []):
            await queue.put(chunk)

    async def release_lock(self, key: str) -> None:
        async with self._lock:
            self._locks.discard(key)
            queues = self._streams.pop(key, [])
        for queue in queues:
            await queue.put(None)

    async def ping(self) -> bool:
        return True


class SQLiteSemanticCacheRepository(CacheRepository):
    def __init__(
        self,
        db_path: str | Path,
        lock_ttl_seconds: int = 300,
        poll_interval_seconds: float = 0.2,
    ):
        self.db_path = Path(db_path)
        self.lock_ttl_seconds = lock_ttl_seconds
        self.poll_interval_seconds = poll_interval_seconds
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(self.db_path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA busy_timeout = 5000")
        self._connection.execute("PRAGMA journal_mode = WAL")
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
                CREATE TABLE IF NOT EXISTS semantic_cache (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    expires_at REAL NOT NULL
                )
                """
            )
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS semantic_locks (
                    key TEXT PRIMARY KEY,
                    expires_at REAL NOT NULL
                )
                """
            )

    async def get(self, key: str) -> Optional[str]:
        now = time.time()
        with self._lock, self._connection:
            self._connection.execute("DELETE FROM semantic_cache WHERE expires_at <= ?", (now,))
            row = self._connection.execute(
                "SELECT value FROM semantic_cache WHERE key = ?",
                (key,),
            ).fetchone()
            return str(row["value"]) if row else None

    async def set(self, key: str, value: str, ttl_seconds: int) -> None:
        expires_at = time.time() + ttl_seconds
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO semantic_cache(key, value, expires_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value=excluded.value,
                    expires_at=excluded.expires_at
                """,
                (key, value, expires_at),
            )

    async def acquire_lock(self, key: str) -> bool:
        now = time.time()
        expires_at = now + self.lock_ttl_seconds
        with self._lock, self._connection:
            self._connection.execute("DELETE FROM semantic_locks WHERE expires_at <= ?", (now,))
            try:
                self._connection.execute(
                    "INSERT INTO semantic_locks(key, expires_at) VALUES (?, ?)",
                    (key, expires_at),
                )
            except sqlite3.IntegrityError:
                return False
            return True

    async def subscribe(self, key: str) -> AsyncGenerator[str, None]:
        deadline = time.monotonic() + self.lock_ttl_seconds + 5
        while time.monotonic() < deadline:
            cached = await self.get(key)
            if cached is not None:
                yield cached
                return
            if not await self._is_locked(key):
                return
            await asyncio.sleep(self.poll_interval_seconds)

    async def publish(self, key: str, chunk: str) -> None:
        return None

    async def release_lock(self, key: str) -> None:
        with self._lock, self._connection:
            self._connection.execute("DELETE FROM semantic_locks WHERE key = ?", (key,))

    async def ping(self) -> bool:
        with self._lock:
            row = self._connection.execute("SELECT 1 AS ok").fetchone()
            return bool(row and row["ok"] == 1)

    async def _is_locked(self, key: str) -> bool:
        now = time.time()
        with self._lock, self._connection:
            self._connection.execute("DELETE FROM semantic_locks WHERE expires_at <= ?", (now,))
            row = self._connection.execute(
                "SELECT 1 AS locked FROM semantic_locks WHERE key = ?",
                (key,),
            ).fetchone()
            return row is not None


class TokenBucketRateLimitRepository(RateLimitRepository):
    def __init__(
        self,
        capacity: int = 20,
        refill_per_minute: int = 20,
        base_backoff_seconds: float = 2.0,
        max_backoff_seconds: float = 60.0,
        monotonic: Optional[Callable[[], float]] = None,
    ):
        if capacity < 1:
            raise ValueError("capacity must be at least 1")
        if refill_per_minute < 0:
            raise ValueError("refill_per_minute must be non-negative")
        if base_backoff_seconds <= 0:
            raise ValueError("base_backoff_seconds must be positive")
        if max_backoff_seconds < base_backoff_seconds:
            raise ValueError("max_backoff_seconds must be greater than or equal to base_backoff_seconds")
        self.capacity = float(capacity)
        self.refill_per_second = float(refill_per_minute) / 60.0
        self.base_backoff_seconds = float(base_backoff_seconds)
        self.max_backoff_seconds = float(max_backoff_seconds)
        self._monotonic = monotonic or time.monotonic
        self._buckets: Dict[str, tuple[float, float]] = {}
        self._blocked_until: Dict[str, float] = {}
        self._violations: Dict[str, int] = {}
        self._lock = asyncio.Lock()

    async def check_and_consume(self, user_id: str) -> bool:
        async with self._lock:
            now = self._monotonic()
            blocked_until = self._blocked_until.get(user_id)
            if blocked_until is not None and blocked_until > now:
                return False
            self._blocked_until.pop(user_id, None)

            tokens, last_seen = self._buckets.get(user_id, (self.capacity, now))
            elapsed = max(0.0, now - last_seen)
            tokens = min(self.capacity, tokens + elapsed * self.refill_per_second)
            if tokens < 1.0:
                self._violations[user_id] = self._violations.get(user_id, 0) + 1
                self._blocked_until[user_id] = now + self._backoff_seconds(self._violations[user_id])
                self._buckets[user_id] = (tokens, now)
                return False
            self._violations[user_id] = 0
            self._buckets[user_id] = (tokens - 1.0, now)
            return True

    def retry_after(self, user_id: str) -> int:
        blocked_until = self._blocked_until.get(user_id)
        if blocked_until is None:
            return 0
        return max(0, math.ceil(blocked_until - self._monotonic()))

    def _backoff_seconds(self, violations: int) -> float:
        return min(self.max_backoff_seconds, self.base_backoff_seconds * (2 ** max(0, violations - 1)))


class RedisTokenBucketRateLimitRepository(RateLimitRepository):
    LUA_SCRIPT = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local capacity = tonumber(ARGV[2])
local refill_per_second = tonumber(ARGV[3])
local base_backoff = tonumber(ARGV[4])
local max_backoff = tonumber(ARGV[5])
local ttl = math.ceil(math.max(3600, max_backoff * 2))

local state = redis.call('HMGET', key, 'tokens', 'last_seen', 'blocked_until', 'violations')
local tokens = tonumber(state[1]) or capacity
local last_seen = tonumber(state[2]) or now
local blocked_until = tonumber(state[3]) or 0
local violations = tonumber(state[4]) or 0

if blocked_until > now then
    return {0, math.ceil(blocked_until - now)}
end

local elapsed = math.max(0, now - last_seen)
tokens = math.min(capacity, tokens + elapsed * refill_per_second)

if tokens < 1 then
    violations = violations + 1
    local delay = math.min(max_backoff, base_backoff * math.pow(2, math.max(0, violations - 1)))
    blocked_until = now + delay
    redis.call('HSET', key, 'tokens', tokens, 'last_seen', now, 'blocked_until', blocked_until, 'violations', violations)
    redis.call('EXPIRE', key, ttl)
    return {0, math.ceil(delay)}
end

tokens = tokens - 1
redis.call('HSET', key, 'tokens', tokens, 'last_seen', now, 'blocked_until', 0, 'violations', 0)
redis.call('EXPIRE', key, ttl)
return {1, 0}
"""

    def __init__(
        self,
        redis_url: str,
        capacity: int = 20,
        refill_per_minute: int = 20,
        base_backoff_seconds: float = 2.0,
        max_backoff_seconds: float = 60.0,
        time_source: Optional[Callable[[], float]] = None,
    ):
        try:
            import redis.asyncio as redis
        except ImportError as exc:
            raise RuntimeError("redis package is required for RedisTokenBucketRateLimitRepository") from exc
        self._configure(
            redis.from_url(redis_url, decode_responses=True),
            capacity,
            refill_per_minute,
            base_backoff_seconds,
            max_backoff_seconds,
            time_source,
        )

    @classmethod
    def from_client(
        cls,
        client,
        capacity: int = 20,
        refill_per_minute: int = 20,
        base_backoff_seconds: float = 2.0,
        max_backoff_seconds: float = 60.0,
        time_source: Optional[Callable[[], float]] = None,
    ) -> "RedisTokenBucketRateLimitRepository":
        instance = cls.__new__(cls)
        instance._configure(
            client,
            capacity,
            refill_per_minute,
            base_backoff_seconds,
            max_backoff_seconds,
            time_source,
        )
        return instance

    def _configure(
        self,
        client,
        capacity: int,
        refill_per_minute: int,
        base_backoff_seconds: float,
        max_backoff_seconds: float,
        time_source: Optional[Callable[[], float]],
    ) -> None:
        if capacity < 1:
            raise ValueError("capacity must be at least 1")
        if refill_per_minute < 0:
            raise ValueError("refill_per_minute must be non-negative")
        if base_backoff_seconds <= 0:
            raise ValueError("base_backoff_seconds must be positive")
        if max_backoff_seconds < base_backoff_seconds:
            raise ValueError("max_backoff_seconds must be greater than or equal to base_backoff_seconds")
        self.client = client
        self.capacity = int(capacity)
        self.refill_per_second = float(refill_per_minute) / 60.0
        self.base_backoff_seconds = float(base_backoff_seconds)
        self.max_backoff_seconds = float(max_backoff_seconds)
        self._time_source = time_source or time.time
        self._last_retry_after: Dict[str, int] = {}

    async def check_and_consume(self, user_id: str) -> bool:
        result = await self.client.eval(
            self.LUA_SCRIPT,
            1,
            self._key(user_id),
            self._time_source(),
            self.capacity,
            self.refill_per_second,
            self.base_backoff_seconds,
            self.max_backoff_seconds,
        )
        allowed = bool(int(result[0]))
        retry_after = math.ceil(float(result[1]))
        self._last_retry_after[user_id] = max(0, retry_after)
        return allowed

    def retry_after(self, user_id: str) -> int:
        return self._last_retry_after.get(user_id, 0)

    @staticmethod
    def _key(user_id: str) -> str:
        return f"cis:rate:{user_id}"


class RedisSemanticCacheRepository(CacheRepository):
    def __init__(self, redis_url: str, lock_ttl_seconds: int = 300):
        try:
            import redis.asyncio as redis
        except ImportError as exc:
            raise RuntimeError("redis package is required for RedisSemanticCacheRepository") from exc
        self.client = redis.from_url(redis_url, decode_responses=True)
        self.lock_ttl_seconds = lock_ttl_seconds

    async def get(self, key: str) -> Optional[str]:
        return await self.client.get(self._cache_key(key))

    async def set(self, key: str, value: str, ttl_seconds: int) -> None:
        await self.client.set(self._cache_key(key), value, ex=ttl_seconds)

    async def acquire_lock(self, key: str) -> bool:
        return bool(await self.client.set(self._lock_key(key), "1", ex=self.lock_ttl_seconds, nx=True))

    async def subscribe(self, key: str) -> AsyncGenerator[str, None]:
        pubsub = self.client.pubsub()
        channel = self._channel_key(key)
        await pubsub.subscribe(channel)
        try:
            async for message in pubsub.listen():
                if message.get("type") != "message":
                    continue
                data = message.get("data")
                if data == "__END__":
                    break
                yield data
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.aclose()

    async def publish(self, key: str, chunk: str) -> None:
        await self.client.publish(self._channel_key(key), chunk)

    async def release_lock(self, key: str) -> None:
        await self.client.publish(self._channel_key(key), "__END__")
        await self.client.delete(self._lock_key(key))

    async def ping(self) -> bool:
        return bool(await self.client.ping())

    @staticmethod
    def _cache_key(key: str) -> str:
        return f"cis:cache:{key}"

    @staticmethod
    def _lock_key(key: str) -> str:
        return f"cis:lock:{key}"

    @staticmethod
    def _channel_key(key: str) -> str:
        return f"cis:stream:{key}"


def tier_rank(tier: AccessTier) -> int:
    return {
        AccessTier.T1: 1,
        AccessTier.T2: 2,
        AccessTier.T3: 3,
    }[tier]
