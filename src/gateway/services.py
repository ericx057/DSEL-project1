import time
import hashlib
import asyncio
from typing import AsyncGenerator, Dict, List, Optional
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


RESPONSE_CACHE_POLICY_VERSION = "response-policy-v3"

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
            raise HTTPException(status_code=429, detail="Rate limit exceeded")

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


class TokenBucketRateLimitRepository(RateLimitRepository):
    def __init__(self, capacity: int = 20, refill_per_minute: int = 20):
        self.capacity = float(capacity)
        self.refill_per_second = float(refill_per_minute) / 60.0
        self._buckets: Dict[str, tuple[float, float]] = {}
        self._lock = asyncio.Lock()

    async def check_and_consume(self, user_id: str) -> bool:
        async with self._lock:
            now = time.monotonic()
            tokens, last_seen = self._buckets.get(user_id, (self.capacity, now))
            elapsed = max(0.0, now - last_seen)
            tokens = min(self.capacity, tokens + elapsed * self.refill_per_second)
            if tokens < 1.0:
                self._buckets[user_id] = (tokens, now)
                return False
            self._buckets[user_id] = (tokens - 1.0, now)
            return True


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
