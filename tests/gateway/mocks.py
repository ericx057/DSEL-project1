import asyncio
from typing import Dict, List, Optional, AsyncGenerator
from src.gateway.models import AccessTier, AuditEvent
from src.gateway.repositories import (
    AccessMatrixRepository,
    ScopeRepository,
    CacheRepository,
    RateLimitRepository,
    AuditRepository
)

class InMemoryAccessMatrixRepository(AccessMatrixRepository):
    def __init__(self, user_tiers: Dict[str, AccessTier] = None):
        self.user_tiers = user_tiers or {}

    async def get_user_tier(self, user_id: str) -> AccessTier:
        return self.user_tiers.get(user_id, AccessTier.T1)

class InMemoryScopeRepository(ScopeRepository):
    def __init__(self, group_scopes: Dict[str, List[str]] = None):
        self.group_scopes = group_scopes or {}

    async def get_allowed_scopes(self, groups: List[str], query: str) -> List[str]:
        scopes = set()
        for group in groups:
            scopes.update(self.group_scopes.get(group, []))
        return list(scopes)

class InMemoryCacheRepository(CacheRepository):
    def __init__(self):
        self._cache: Dict[str, str] = {}
        self._locks: set = set()
        # For pub/sub simulation
        self._streams: Dict[str, List[asyncio.Queue]] = {}

    async def get(self, key: str) -> Optional[str]:
        return self._cache.get(key)

    async def set(self, key: str, value: str, ttl_seconds: int) -> None:
        self._cache[key] = value

    async def acquire_lock(self, key: str) -> bool:
        if key in self._locks:
            return False
        self._locks.add(key)
        self._streams[key] = []
        return True

    async def subscribe(self, key: str) -> AsyncGenerator[str, None]:
        queue = asyncio.Queue()
        if key not in self._streams:
            self._streams[key] = []
        self._streams[key].append(queue)
        
        while True:
            chunk = await queue.get()
            if chunk is None:  # Sentinel value for end of stream
                break
            yield chunk

    async def publish(self, key: str, chunk: str) -> None:
        if key in self._streams:
            for queue in self._streams[key]:
                await queue.put(chunk)

    async def release_lock(self, key: str) -> None:
        self._locks.discard(key)
        # Send sentinel to close all subscribed queues
        if key in self._streams:
            for queue in self._streams[key]:
                await queue.put(None)
            del self._streams[key]

class InMemoryRateLimitRepository(RateLimitRepository):
    def __init__(self, limits: Dict[str, int] = None):
        self.limits = limits or {}
        self.usage: Dict[str, int] = {}

    async def check_and_consume(self, user_id: str) -> bool:
        limit = self.limits.get(user_id, 20)
        current = self.usage.get(user_id, 0)
        if current >= limit:
            return False
        self.usage[user_id] = current + 1
        return True

class InMemoryAuditRepository(AuditRepository):
    def __init__(self):
        self.events: List[AuditEvent] = []

    async def log_event(self, event: AuditEvent) -> None:
        self.events.append(event)
