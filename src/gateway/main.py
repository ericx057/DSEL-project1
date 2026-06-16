from __future__ import annotations

import time
from typing import AsyncGenerator, Optional

from fastapi import Depends, FastAPI, Header, Query
from fastapi.responses import Response, StreamingResponse

from src.retrieval.assembler import PromptAssembler
from src.retrieval.context_summary import ResponseShaper
from src.retrieval.database import UnifiedStore
from src.retrieval.hybrid import HybridSearcher
from src.retrieval.reranker import LexicalReranker
from src.diagram.service import DiagramService
from src.gateway.model_hook import ModelHook
from src.gateway.models import AuditEvent, HistoryRecord, QueryRequest
from src.gateway.repositories import (
    AccessMatrixRepository,
    AuditRepository,
    CacheRepository,
    RateLimitRepository,
    ScopeRepository,
    UserHistoryRepository,
)
from src.gateway.security import HS256JWTVerifier
from src.gateway.services import (
    AuditService,
    CacheService,
    CircuitBreaker,
    IAMService,
    RateLimitService,
    ScopingService,
    tier_rank,
)


global_circuit_breaker = CircuitBreaker()


def get_access_matrix_repo() -> AccessMatrixRepository:
    raise NotImplementedError("Dependency overridden in tests or create_app")


def get_scope_repo() -> ScopeRepository:
    raise NotImplementedError("Dependency overridden in tests or create_app")


def get_cache_repo() -> CacheRepository:
    raise NotImplementedError("Dependency overridden in tests or create_app")


def get_rate_limit_repo() -> RateLimitRepository:
    raise NotImplementedError("Dependency overridden in tests or create_app")


def get_audit_repo() -> AuditRepository:
    raise NotImplementedError("Dependency overridden in tests or create_app")


def get_history_repo() -> Optional[UserHistoryRepository]:
    return None


def get_retrieval_store() -> Optional[UnifiedStore]:
    return None


def get_jwt_verifier() -> Optional[HS256JWTVerifier]:
    return None


def get_iam_service(
    repo: AccessMatrixRepository = Depends(get_access_matrix_repo),
    jwt_verifier: Optional[HS256JWTVerifier] = Depends(get_jwt_verifier),
) -> IAMService:
    return IAMService(repo, jwt_verifier)


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


def create_app(
    *,
    access_matrix_repo: Optional[AccessMatrixRepository] = None,
    scope_repo: Optional[ScopeRepository] = None,
    cache_repo: Optional[CacheRepository] = None,
    rate_limit_repo: Optional[RateLimitRepository] = None,
    audit_repo: Optional[AuditRepository] = None,
    history_repo: Optional[UserHistoryRepository] = None,
    retrieval_store: Optional[UnifiedStore] = None,
    model_hook: Optional[ModelHook] = None,
    jwt_verifier: Optional[HS256JWTVerifier] = None,
    metrics_token: Optional[str] = None,
) -> FastAPI:
    api = FastAPI(title="Codebase Intelligence System - Gateway", version="1.0.0")

    @api.middleware("http")
    async def security_headers(request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'",
        )
        return response

    if access_matrix_repo is not None:
        api.dependency_overrides[get_access_matrix_repo] = lambda: access_matrix_repo
    if scope_repo is not None:
        api.dependency_overrides[get_scope_repo] = lambda: scope_repo
    if cache_repo is not None:
        api.dependency_overrides[get_cache_repo] = lambda: cache_repo
    if rate_limit_repo is not None:
        api.dependency_overrides[get_rate_limit_repo] = lambda: rate_limit_repo
    if audit_repo is not None:
        api.dependency_overrides[get_audit_repo] = lambda: audit_repo
    if history_repo is not None:
        api.dependency_overrides[get_history_repo] = lambda: history_repo
    if retrieval_store is not None:
        api.dependency_overrides[get_retrieval_store] = lambda: retrieval_store
    if model_hook is not None:
        api.dependency_overrides[get_model_hook] = lambda: model_hook
    if jwt_verifier is not None:
        api.dependency_overrides[get_jwt_verifier] = lambda: jwt_verifier

    @api.get("/health")
    async def health():
        return {"status": "ok"}

    @api.get("/history")
    async def history_endpoint(
        authorization: str = Header(...),
        limit: int = Query(default=50, ge=1, le=100),
        iam: IAMService = Depends(get_iam_service),
        history: Optional[UserHistoryRepository] = Depends(get_history_repo),
    ):
        user = iam.decode_token(authorization)
        if history is None:
            return {"history": []}
        return {"history": [record.model_dump() for record in history.list_for_user(user.id, limit=limit)]}

    @api.get("/diagram/call-graph")
    async def call_graph_endpoint(
        q: str = Query(..., min_length=1),
        authorization: str = Header(...),
        iam: IAMService = Depends(get_iam_service),
        scoping: ScopingService = Depends(get_scoping_service),
        store: Optional[UnifiedStore] = Depends(get_retrieval_store),
    ):
        if store is None or not hasattr(store, "list_edges"):
            return Response("<svg xmlns=\"http://www.w3.org/2000/svg\"></svg>", media_type="image/svg+xml")
        user = iam.decode_token(authorization)
        tier = await iam.get_tier(user.id)
        scopes = await scoping.resolve_scope(user, q)
        svg = DiagramService(store).render_call_graph_svg(q, user_tier=tier_rank(tier), repo_scope=scopes)
        return Response(svg, media_type="image/svg+xml")

    @api.get("/metrics")
    async def metrics(
        x_metrics_token: Optional[str] = Header(default=None),
        authorization: Optional[str] = Header(default=None),
    ):
        bearer_token = None
        if authorization and authorization.lower().startswith("bearer "):
            bearer_token = authorization.split(" ", 1)[1]
        if metrics_token and x_metrics_token != metrics_token and bearer_token != metrics_token:
            return Response("not found", status_code=404)
        state = 0 if global_circuit_breaker.state == "CLOSED" else 1
        body = "\n".join(
            [
                "# HELP cis_circuit_breaker_open Inference circuit breaker open state.",
                "# TYPE cis_circuit_breaker_open gauge",
                f"cis_circuit_breaker_open {state}",
                "# HELP cis_circuit_breaker_failures Current circuit breaker failure count.",
                "# TYPE cis_circuit_breaker_failures gauge",
                f"cis_circuit_breaker_failures {global_circuit_breaker.failure_count}",
                "",
            ]
        )
        return Response(body, media_type="text/plain; version=0.0.4")

    @api.post("/query")
    async def handle_query(
        request: QueryRequest,
        authorization: str = Header(...),
        iam: IAMService = Depends(get_iam_service),
        scoping: ScopingService = Depends(get_scoping_service),
        cache: CacheService = Depends(get_cache_service),
        rate_limit: RateLimitService = Depends(get_rate_limit_service),
        audit: AuditService = Depends(get_audit_service),
        selected_model_hook: ModelHook = Depends(get_model_hook),
        store: Optional[UnifiedStore] = Depends(get_retrieval_store),
        history: Optional[UserHistoryRepository] = Depends(get_history_repo),
    ):
        start_time = time.time()
        response_shaper = ResponseShaper()
        user = iam.decode_token(authorization)
        rate_limit.check_circuit_breaker()
        await rate_limit.check_rate_limit(user.id)

        tier = await iam.get_tier(user.id)
        scopes = await scoping.resolve_scope(user, request.query)
        query_hash = cache._generate_key(request.query, tier, scopes)
        if not scopes:
            blocked_engine_used = getattr(selected_model_hook, "inference_engine_id", "llama.cpp")
            await audit.log(
                AuditEvent(
                    user_id=user.id,
                    access_tier=tier,
                    query_hash=query_hash,
                    repo_scope=[],
                    inference_engine_used=blocked_engine_used,
                    latency_ms=(time.time() - start_time) * 1000,
                    cache_hit=False,
                    rbac_blocked=True,
                )
            )
            return Response("No authorized repository scope for this query.", status_code=403)

        cached_response = await cache.get_cached_response(request.query, tier, scopes)
        if cached_response:
            shaped_response = response_shaper.shape(cached_response)
            await audit.log(
                AuditEvent(
                    user_id=user.id,
                    access_tier=tier,
                    query_hash=query_hash,
                    repo_scope=scopes,
                    inference_engine_used="cache",
                    latency_ms=(time.time() - start_time) * 1000,
                    cache_hit=True,
                    rbac_blocked=False,
                )
            )
            return {"response": shaped_response, "cached": True}

        acquired = await cache.acquire_lock(request.query, tier, scopes)
        if not acquired:
            async def subscriber_stream() -> AsyncGenerator[str, None]:
                chunks = []
                async for chunk in cache.subscribe(request.query, tier, scopes):
                    chunks.append(chunk)
                yield response_shaper.shape("".join(chunks))
            return StreamingResponse(subscriber_stream(), media_type="text/event-stream")

        prompt = _build_prompt(request.query, tier, scopes, store)
        inference_engine_used = getattr(selected_model_hook, "inference_engine_id", "llama.cpp")

        async def inference_stream() -> AsyncGenerator[str, None]:
            full_response = []
            try:
                async for chunk in selected_model_hook.generate_stream(prompt):
                    full_response.append(chunk)

                final_text = response_shaper.shape("".join(full_response))
                await cache.publish(request.query, tier, scopes, final_text)
                yield final_text
                await cache.set_cached_response(request.query, tier, scopes, final_text)
                if history is not None:
                    await history.add_record(
                        HistoryRecord(
                            user_id=user.id,
                            query=request.query,
                            response=final_text,
                            inference_engine_used=inference_engine_used,
                            repo_scope=scopes,
                            created_at=time.time(),
                        )
                    )
                await audit.log(
                    AuditEvent(
                        user_id=user.id,
                        access_tier=tier,
                        query_hash=query_hash,
                        repo_scope=scopes,
                        inference_engine_used=inference_engine_used,
                        latency_ms=(time.time() - start_time) * 1000,
                        cache_hit=False,
                        rbac_blocked=False,
                    )
                )
            finally:
                await cache.release_lock(request.query, tier, scopes)

        return StreamingResponse(inference_stream(), media_type="text/event-stream")

    return api


def _build_prompt(query: str, tier, scopes: list[str], store: Optional[UnifiedStore]) -> str:
    if store is None:
        raise RuntimeError("Retrieval store is not configured")
    searcher = HybridSearcher(store)
    candidates = searcher.search(query, tier_rank(tier), repo_scope=scopes)
    reranked = LexicalReranker().rerank(query, candidates, top_m=8)
    system_rule = (
        "You are a read-only codebase intelligence assistant. "
        f"The authenticated user's access tier is {tier.value}. "
        "Use only the provided retrieved summaries and do not infer inaccessible implementation details. "
        "Do not answer by listing file paths, raw filenames, or copied source. "
        "Summarize behavior in terms of symbols, responsibilities, and call relationships."
    )
    return PromptAssembler(system_rule).assemble(query, reranked)


app = create_app()
