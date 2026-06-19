import pytest
import time
from fastapi import HTTPException

from src.gateway.services import (
    CircuitBreaker,
    RateLimitService,
    RedisTokenBucketRateLimitRepository,
    SQLiteSemanticCacheRepository,
    TokenBucketRateLimitRepository,
)

def test_circuit_breaker_success():
    cb = CircuitBreaker(failure_threshold=2)
    assert cb.is_allowed() is True
    cb.record_success()
    assert cb.state == "CLOSED"

def test_circuit_breaker_failure_and_recovery():
    cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.1)
    
    cb.record_failure()
    assert cb.state == "CLOSED"
    assert cb.is_allowed() is True
    
    cb.record_failure()
    assert cb.state == "OPEN"
    assert cb.is_allowed() is False
    
    # Wait for recovery
    time.sleep(0.15)
    assert cb.is_allowed() is True # Transitions to HALF_OPEN
    assert cb.state == "HALF_OPEN"
    
    # In HALF_OPEN, it's allowed
    assert cb.is_allowed() is True

def test_circuit_breaker_half_open_failure():
    cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.1)
    cb.record_failure()
    assert cb.state == "OPEN"
    time.sleep(0.15)
    assert cb.is_allowed() is True
    cb.record_failure()
    assert cb.state == "OPEN"


@pytest.mark.asyncio
async def test_sqlite_semantic_cache_coordinates_locks_across_instances(tmp_path):
    first = SQLiteSemanticCacheRepository(tmp_path / "cache.db", poll_interval_seconds=0.01)
    second = SQLiteSemanticCacheRepository(tmp_path / "cache.db", poll_interval_seconds=0.01)

    assert await first.acquire_lock("request-key")
    assert not await second.acquire_lock("request-key")

    await first.set("request-key", "final payload", ttl_seconds=60)
    await first.release_lock("request-key")

    chunks = []
    async for chunk in second.subscribe("request-key"):
        chunks.append(chunk)

    assert chunks == ["final payload"]
    assert await second.acquire_lock("request-key")


@pytest.mark.asyncio
async def test_token_bucket_rate_limit_applies_exponential_backoff():
    now = [100.0]
    repo = TokenBucketRateLimitRepository(
        capacity=1,
        refill_per_minute=0,
        base_backoff_seconds=2,
        max_backoff_seconds=10,
        monotonic=lambda: now[0],
    )

    assert await repo.check_and_consume("user-1")
    assert not await repo.check_and_consume("user-1")
    assert repo.retry_after("user-1") == 2

    now[0] += 2.1
    assert not await repo.check_and_consume("user-1")
    assert repo.retry_after("user-1") == 4


@pytest.mark.asyncio
async def test_rate_limit_service_exposes_retry_after_header():
    now = [100.0]
    repo = TokenBucketRateLimitRepository(
        capacity=1,
        refill_per_minute=0,
        base_backoff_seconds=3,
        max_backoff_seconds=30,
        monotonic=lambda: now[0],
    )
    service = RateLimitService(repo, CircuitBreaker())

    await service.check_rate_limit("user-1")
    with pytest.raises(HTTPException) as exc:
        await service.check_rate_limit("user-1")

    assert exc.value.status_code == 429
    assert exc.value.headers == {"Retry-After": "3"}


@pytest.mark.asyncio
async def test_redis_rate_limit_repository_uses_atomic_script():
    class RecordingRedisClient:
        def __init__(self):
            self.calls = []

        async def eval(self, script, numkeys, *keys_and_args):
            self.calls.append((script, numkeys, keys_and_args))
            return [0, 5]

    client = RecordingRedisClient()
    repo = RedisTokenBucketRateLimitRepository.from_client(
        client,
        capacity=20,
        refill_per_minute=20,
        base_backoff_seconds=2,
        max_backoff_seconds=60,
        time_source=lambda: 100.0,
    )

    assert not await repo.check_and_consume("user-1")
    assert repo.retry_after("user-1") == 5
    assert len(client.calls) == 1
    script, numkeys, keys_and_args = client.calls[0]
    assert numkeys == 1
    assert keys_and_args[0] == "cis:rate:user-1"
    assert "redis.call('HMGET'" in script
    assert "redis.call('HSET'" in script
