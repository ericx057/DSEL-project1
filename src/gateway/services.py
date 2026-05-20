import time
import hashlib
from typing import List, Optional, AsyncGenerator, Callable
from fastapi import HTTPException

from src.gateway.models import AccessTier, User, AuditEvent
from src.gateway.repositories import (
    AccessMatrixRepository,
    ScopeRepository,
    CacheRepository,
    RateLimitRepository,
    AuditRepository
)

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
    def __init__(self, repository: AccessMatrixRepository):
        self.repository = repository

    def decode_token(self, token: str) -> User:
        # In a real system, this would decode and verify a JWT.
        # For now, we assume the token is the user_id (mock).
        # We will mock the groups for simplicity.
        return User(id=token, groups=["dev", "engineering"])

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

    def _generate_key(self, query: str, tier: AccessTier, scopes: List[str]) -> str:
        raw_key = f"{query}:{tier}:{','.join(sorted(scopes))}"
        return hashlib.sha256(raw_key.encode()).hexdigest()

    async def get_cached_response(self, query: str, tier: AccessTier, scopes: List[str]) -> Optional[str]:
        key = self._generate_key(query, tier, scopes)
        return await self.repository.get(key)

    async def set_cached_response(self, query: str, tier: AccessTier, scopes: List[str], response: str) -> None:
        key = self._generate_key(query, tier, scopes)
        ttl = 3600 if tier == AccessTier.T3 else 14400
        await self.repository.set(key, response, ttl)

    async def acquire_lock(self, query: str, tier: AccessTier, scopes: List[str]) -> bool:
        key = self._generate_key(query, tier, scopes)
        return await self.repository.acquire_lock(key)

    async def subscribe(self, query: str, tier: AccessTier, scopes: List[str]) -> AsyncGenerator[str, None]:
        key = self._generate_key(query, tier, scopes)
        async for chunk in self.repository.subscribe(key):
            yield chunk

    async def publish(self, query: str, tier: AccessTier, scopes: List[str], chunk: str) -> None:
        key = self._generate_key(query, tier, scopes)
        await self.repository.publish(key, chunk)

    async def release_lock(self, query: str, tier: AccessTier, scopes: List[str]) -> None:
        key = self._generate_key(query, tier, scopes)
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
