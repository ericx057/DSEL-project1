import time
import asyncio
from typing import AsyncGenerator
from fastapi import FastAPI, Depends, Header, HTTPException, Request
from fastapi.responses import StreamingResponse

from src.gateway.models import QueryRequest, AuditEvent, AccessTier, User
from src.gateway.repositories import (
    AccessMatrixRepository,
    ScopeRepository,
    CacheRepository,
    RateLimitRepository,
    AuditRepository
)
from src.gateway.services import (
    IAMService,
    ScopingService,
    CacheService,
    RateLimitService,
    AuditService,
    CircuitBreaker
)
from src.gateway.model_hook import ModelHook

app = FastAPI(title="Codebase Intelligence System - Gateway")

# --- Dependency Injection Setup ---
# In a real app, these would be initialized with real DB connections.
# For our testing architecture, we can override these dependencies in pytest.

def get_access_matrix_repo() -> AccessMatrixRepository:
    raise NotImplementedError("Dependency overridden in tests")

def get_scope_repo() -> ScopeRepository:
    raise NotImplementedError("Dependency overridden in tests")

def get_cache_repo() -> CacheRepository:
    raise NotImplementedError("Dependency overridden in tests")

def get_rate_limit_repo() -> RateLimitRepository:
    raise NotImplementedError("Dependency overridden in tests")

def get_audit_repo() -> AuditRepository:
    raise NotImplementedError("Dependency overridden in tests")

# Global circuit breaker instance
global_circuit_breaker = CircuitBreaker()

def get_iam_service(repo: AccessMatrixRepository = Depends(get_access_matrix_repo)) -> IAMService:
    return IAMService(repo)

def get_scoping_service(repo: ScopeRepository = Depends(get_scope_repo)) -> ScopingService:
    return ScopingService(repo)

def get_cache_service(repo: CacheRepository = Depends(get_cache_repo)) -> CacheService:
    return CacheService(repo)

def get_rate_limit_service(repo: RateLimitRepository = Depends(get_rate_limit_repo)) -> RateLimitService:
    return RateLimitService(repo, global_circuit_breaker)

def get_audit_service(repo: AuditRepository = Depends(get_audit_repo)) -> AuditService:
    return AuditService(repo)

def get_model_hook() -> ModelHook:
    return ModelHook(circuit_breaker=global_circuit_breaker)


# --- Routes ---

@app.post("/query")
async def handle_query(
    request: QueryRequest,
    authorization: str = Header(...),
    iam: IAMService = Depends(get_iam_service),
    scoping: ScopingService = Depends(get_scoping_service),
    cache: CacheService = Depends(get_cache_service),
    rate_limit: RateLimitService = Depends(get_rate_limit_service),
    audit: AuditService = Depends(get_audit_service),
    model_hook: ModelHook = Depends(get_model_hook)
):
    start_time = time.time()
    user = iam.decode_token(authorization)
    
    # 1. Rate Limiting & Circuit Breaker Check
    rate_limit.check_circuit_breaker()
    await rate_limit.check_rate_limit(user.id)
    
    # 2. Access Tier Resolution
    tier = await iam.get_tier(user.id)
    
    # 3. Scope Resolution
    scopes = await scoping.resolve_scope(user, request.query)
    
    # 4. Cache Check & Coalescing
    cached_response = await cache.get_cached_response(request.query, tier, scopes)
    if cached_response:
        # Log Audit Event for cache hit
        await audit.log(AuditEvent(
            user_id=user.id,
            access_tier=tier,
            query_hash=cache._generate_key(request.query, tier, scopes),
            repo_scope=scopes,
            model_used="cache",
            latency_ms=(time.time() - start_time) * 1000,
            cache_hit=True,
            rbac_blocked=False
        ))
        return {"response": cached_response, "cached": True}

    # Try to acquire lock for coalescing
    acquired = await cache.acquire_lock(request.query, tier, scopes)
    if not acquired:
        # Redundant miss: subscribe to the existing stream
        async def subscriber_stream() -> AsyncGenerator[str, None]:
            async for chunk in cache.subscribe(request.query, tier, scopes):
                yield chunk
        return StreamingResponse(subscriber_stream(), media_type="text/event-stream")

    # 5. Inference Execution (Lock Acquired)
    async def inference_stream() -> AsyncGenerator[str, None]:
        full_response = []
        try:
            async for chunk in model_hook.generate_stream(request.query):
                full_response.append(chunk)
                # Publish to other subscribers
                await cache.publish(request.query, tier, scopes, chunk)
                yield chunk
            
            # Save the fully built response
            final_text = "".join(full_response)
            await cache.set_cached_response(request.query, tier, scopes, final_text)
            
            # Log Audit Event for successful inference
            await audit.log(AuditEvent(
                user_id=user.id,
                access_tier=tier,
                query_hash=cache._generate_key(request.query, tier, scopes),
                repo_scope=scopes,
                model_used=request.override_model or "default",
                latency_ms=(time.time() - start_time) * 1000,
                cache_hit=False,
                rbac_blocked=False
            ))
            
        finally:
            await cache.release_lock(request.query, tier, scopes)

    return StreamingResponse(inference_stream(), media_type="text/event-stream")
