import asyncio
import pytest
from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI
from src.gateway.main import (
    app, get_access_matrix_repo, get_scope_repo, 
    get_cache_repo, get_rate_limit_repo, get_audit_repo,
    get_model_hook, global_circuit_breaker
)
from src.gateway.models import AccessTier
from tests.gateway.mocks import (
    InMemoryAccessMatrixRepository,
    InMemoryScopeRepository,
    InMemoryCacheRepository,
    InMemoryRateLimitRepository,
    InMemoryAuditRepository
)
from src.gateway.model_hook import ModelHook

# --- Mock the Model Hook to avoid real HuggingFace API calls during tests ---
class MockModelHook(ModelHook):
    def __init__(self, circuit_breaker=None):
        super().__init__(model_id="mock", circuit_breaker=circuit_breaker)
        
    async def generate_stream(self, prompt: str):
        await asyncio.sleep(0.01)
        yield "Hello "
        await asyncio.sleep(0.01)
        yield "World"
        if self.circuit_breaker:
            self.circuit_breaker.record_success()

# --- Setup App Overrides ---
@pytest.fixture
def test_app():
    # Reset circuit breaker
    global_circuit_breaker.state = "CLOSED"
    global_circuit_breaker.failure_count = 0
    
    am_repo = InMemoryAccessMatrixRepository({"user1": AccessTier.T3})
    scope_repo = InMemoryScopeRepository({"dev": ["repo-a"]})
    cache_repo = InMemoryCacheRepository()
    rl_repo = InMemoryRateLimitRepository({"user1": 2}) # very low limit for testing
    audit_repo = InMemoryAuditRepository()
    
    app.dependency_overrides[get_access_matrix_repo] = lambda: am_repo
    app.dependency_overrides[get_scope_repo] = lambda: scope_repo
    app.dependency_overrides[get_cache_repo] = lambda: cache_repo
    app.dependency_overrides[get_rate_limit_repo] = lambda: rl_repo
    app.dependency_overrides[get_audit_repo] = lambda: audit_repo
    app.dependency_overrides[get_model_hook] = lambda: MockModelHook(global_circuit_breaker)
    
    yield app, rl_repo, cache_repo, audit_repo
    app.dependency_overrides.clear()

@pytest.mark.asyncio
async def test_standard_query_flow(test_app):
    fastapi_app, _, _, audit_repo = test_app
    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        response = await ac.post(
            "/query", 
            json={"query": "What is the entrypoint?"},
            headers={"Authorization": "user1"}
        )
        assert response.status_code == 200
        assert response.text == "Hello World"
        
        # Verify audit log
        assert len(audit_repo.events) == 1
        assert audit_repo.events[0].cache_hit is False

@pytest.mark.asyncio
async def test_rate_limiting(test_app):
    fastapi_app, _, _, _ = test_app
    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        # User limit is 2
        r1 = await ac.post("/query", json={"query": "Q1"}, headers={"Authorization": "user1"})
        r2 = await ac.post("/query", json={"query": "Q2"}, headers={"Authorization": "user1"})
        r3 = await ac.post("/query", json={"query": "Q3"}, headers={"Authorization": "user1"})
        
        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r3.status_code == 429 # Rate limited

@pytest.mark.asyncio
async def test_cache_hit(test_app):
    fastapi_app, _, cache_repo, audit_repo = test_app
    
    # Pre-populate cache directly
    from src.gateway.services import CacheService
    cache_svc = CacheService(cache_repo)
    key = cache_svc._generate_key("TestQuery", AccessTier.T3, ["repo-a"])
    await cache_repo.set(key, "Cached Answer", 3600)
    
    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        response = await ac.post(
            "/query", 
            json={"query": "TestQuery"},
            headers={"Authorization": "user1"}
        )
        assert response.status_code == 200
        assert response.json() == {"response": "Cached Answer", "cached": True}
        assert audit_repo.events[0].cache_hit is True

@pytest.mark.asyncio
async def test_request_coalescing(test_app):
    fastapi_app, _, cache_repo, audit_repo = test_app
    
    class SlowMockModelHook(ModelHook):
        def __init__(self):
            super().__init__(model_id="mock")
        async def generate_stream(self, prompt: str):
            await asyncio.sleep(0.1) # Simulate slow inference
            yield "Slow "
            await asyncio.sleep(0.1)
            yield "Response"

    fastapi_app.dependency_overrides[get_model_hook] = lambda: SlowMockModelHook()
    
    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        # Fire two identical queries concurrently
        req1 = ac.post("/query", json={"query": "Concurrent"}, headers={"Authorization": "user1"})
        req2 = ac.post("/query", json={"query": "Concurrent"}, headers={"Authorization": "user1"})
        
        results = await asyncio.gather(req1, req2)
        
        # Both should succeed and return identical data
        assert results[0].status_code == 200
        assert results[1].status_code == 200
        assert results[0].text == "Slow Response"
        assert results[1].text == "Slow Response"
