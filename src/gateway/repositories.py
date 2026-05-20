from abc import ABC, abstractmethod
from typing import List, Optional, AsyncGenerator
from src.gateway.models import AccessTier, AuditEvent

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
