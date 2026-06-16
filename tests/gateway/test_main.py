import asyncio
import hashlib
import pytest
from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI
from src.gateway.main import (
    app, get_access_matrix_repo, get_scope_repo, 
    get_cache_repo, get_rate_limit_repo, get_audit_repo,
    get_model_hook, get_jwt_verifier, get_retrieval_store, global_circuit_breaker
)
from src.gateway.models import AccessTier
from src.gateway.models import User
from tests.gateway.mocks import (
    InMemoryAccessMatrixRepository,
    InMemoryScopeRepository,
    InMemoryCacheRepository,
    InMemoryRateLimitRepository,
    InMemoryAuditRepository
)
from src.gateway.model_hook import ModelHook
from src.retrieval.database import InMemoryUnifiedStore
from src.gateway.services import CacheService, RESPONSE_CACHE_POLICY_VERSION

class StaticVerifier:
    def verify(self, authorization: str) -> User:
        return User(id=authorization, groups=["dev", "engineering"])

# --- Mock the Model Hook to avoid real HuggingFace API calls during tests ---
class MockModelHook(ModelHook):
    def __init__(self, circuit_breaker=None):
        super().__init__(inference_engine_id="mock-engine", circuit_breaker=circuit_breaker, client=None)
        
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
    store = InMemoryUnifiedStore([{"id": "repo-a:1", "text": "entrypoint context", "tier": 3}])
    
    app.dependency_overrides[get_access_matrix_repo] = lambda: am_repo
    app.dependency_overrides[get_scope_repo] = lambda: scope_repo
    app.dependency_overrides[get_cache_repo] = lambda: cache_repo
    app.dependency_overrides[get_rate_limit_repo] = lambda: rl_repo
    app.dependency_overrides[get_audit_repo] = lambda: audit_repo
    app.dependency_overrides[get_model_hook] = lambda: MockModelHook(global_circuit_breaker)
    app.dependency_overrides[get_jwt_verifier] = lambda: StaticVerifier()
    app.dependency_overrides[get_retrieval_store] = lambda: store
    
    yield app, rl_repo, cache_repo, audit_repo
    app.dependency_overrides.clear()

@pytest.mark.asyncio
async def test_models_endpoint_is_not_exposed(test_app):
    fastapi_app, _, _, _ = test_app
    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        response = await ac.get("/models")

    assert response.status_code == 404

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
    await cache_repo.set(
        key,
        "--- File: src/app/service.py | Language: python | Tier: 1 ---\n"
        "def cached_answer():\n"
        "    return 'raw path dump'\n"
        "Cached Answer",
        3600,
    )
    
    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        response = await ac.post(
            "/query", 
            json={"query": "TestQuery"},
            headers={"Authorization": "user1"}
        )
        assert response.status_code == 200
        body = response.json()
        assert body["cached"] is True
        assert "Cached Answer" in body["response"]
        assert "src/app/service.py" not in body["response"]
        assert "def cached_answer" not in body["response"]
        assert audit_repo.events[0].cache_hit is True

@pytest.mark.asyncio
async def test_request_coalescing(test_app):
    fastapi_app, _, cache_repo, audit_repo = test_app
    
    class SlowMockModelHook(ModelHook):
        def __init__(self):
            super().__init__(inference_engine_id="slow-mock-engine", client=None)
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


def test_cache_key_includes_response_policy_version():
    cache_svc = CacheService(InMemoryCacheRepository())

    key = cache_svc._generate_key("TestQuery", AccessTier.T3, ["repo-a"])
    legacy_key = hashlib.sha256("TestQuery:AccessTier.T3:repo-a".encode()).hexdigest()

    assert RESPONSE_CACHE_POLICY_VERSION
    assert key != legacy_key


@pytest.mark.asyncio
async def test_coalesced_subscriber_buffers_before_shaping(test_app):
    fastapi_app, _, _, _ = test_app

    class AlwaysLockedCacheRepository(InMemoryCacheRepository):
        def __init__(self):
            super().__init__()
            self.locked_key = None

        async def acquire_lock(self, key: str) -> bool:
            self.locked_key = key
            self._streams.setdefault(key, [])
            return False

    cache_repo = AlwaysLockedCacheRepository()
    fastapi_app.dependency_overrides[get_cache_repo] = lambda: cache_repo

    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as ac:
        pending = asyncio.create_task(
            ac.post(
                "/query",
                json={"query": "SplitPath"},
                headers={"Authorization": "user1"},
            )
        )
        for _ in range(100):
            if cache_repo.locked_key and cache_repo._streams.get(cache_repo.locked_key):
                break
            await asyncio.sleep(0.01)
        assert cache_repo.locked_key is not None
        assert cache_repo._streams.get(cache_repo.locked_key)
        await cache_repo.publish(cache_repo.locked_key, r"Answer comes from src\gate")
        await cache_repo.publish(cache_repo.locked_key, "way\\main.py\nclass Service:")
        await cache_repo.publish(cache_repo.locked_key, "\n    def handle(self):\n        return value")
        await cache_repo.release_lock(cache_repo.locked_key)
        response = await pending

    assert response.status_code == 200
    assert r"src\gate" not in response.text
    assert "way\\main.py" not in response.text
    assert "class Service:" not in response.text
    assert "def handle" not in response.text
    assert "Answer comes from" in response.text
