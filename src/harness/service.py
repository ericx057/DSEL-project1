from __future__ import annotations

import logging
import time
from typing import AsyncGenerator, Protocol

from src.gateway.services import CacheService, tier_rank
from src.harness.cache import CachedResponse, HarnessCacheKey
from src.harness.models import HarnessResult, RetrievalPacket, TaskSpec
from src.harness.policy import RESPONSE_POLICY_VERSION, PolicyDecision, ResponsePolicy
from src.harness.trace import InMemoryTraceRecorder, TraceRecord, TraceRecorder
from src.retrieval.assembler import PromptAssembler
from src.retrieval.context_summary import RetrievedContextSummarizer, ResponseShaper
from src.retrieval.database import UnifiedStore
from src.retrieval.hybrid import HybridSearcher
from src.retrieval.reranker import LexicalReranker


logger = logging.getLogger(__name__)


class ModelAdapter(Protocol):
    model_id: str

    async def generate_stream(self, prompt: str) -> AsyncGenerator[str, None]:
        ...


class HarnessService:
    def __init__(
        self,
        *,
        store: UnifiedStore,
        cache: CacheService,
        model: ModelAdapter,
        trace_recorder: TraceRecorder | None = None,
        policy: ResponsePolicy | None = None,
        summarizer: RetrievedContextSummarizer | None = None,
    ):
        self.store = store
        self.cache = cache
        self.model = model
        self.trace_recorder = trace_recorder or InMemoryTraceRecorder()
        self.policy = policy or ResponsePolicy()
        self.summarizer = summarizer or RetrievedContextSummarizer()

    def cache_key_for(self, task: TaskSpec) -> HarnessCacheKey:
        return HarnessCacheKey(
            normalized_query=self._normalize_query(task.query),
            access_tier=task.access_tier.value,
            repo_scopes=tuple(sorted(task.repo_scopes)),
            response_mode=task.response_mode,
            model_id=task.model_id,
            index_fingerprint=self._index_fingerprint(task.repo_scopes),
            policy_version=self.policy.version,
        )

    async def execute(self, task: TaskSpec) -> HarnessResult:
        started = time.perf_counter()
        trace_id = self.trace_recorder.new_trace_id()
        key = self.cache_key_for(task)
        cache_available = True
        lock_acquired = False

        try:
            cached_payload = await self._get_cached_payload(task, key)
        except Exception:
            logger.exception("Cache lookup failed; bypassing cache for query")
            cached_payload = None
            cache_available = False

        cached_decision = self._cached_decision(cached_payload)
        if cached_decision is not None:
            return self._result_from_decision(task, trace_id, "hit", cached_decision, [], "", started)

        if cache_available:
            try:
                lock_acquired = await self._acquire_lock(task, key)
            except Exception:
                logger.exception("Cache lock acquisition failed; bypassing cache for query")
                cache_available = False

        if cache_available and not lock_acquired:
            try:
                response_text = await self._collect_coalesced_response(task, key)
                decision = self.policy.sanitize_cached(response_text) or PolicyDecision(
                    response=ResponseShaper().shape(response_text),
                    accepted=False,
                    source="coalesced",
                    flags=["coalesced_unstructured"],
                )
                return self._result_from_decision(task, trace_id, "coalesced", decision, [], "", started)
            except Exception:
                logger.exception("Coalesced cache subscription failed; running query directly")
                cache_available = False

        packet = RetrievalPacket.empty(key.index_fingerprint, self.policy.version)
        prompt = ""
        try:
            packet = self._retrieve(task, key.index_fingerprint)
            prompt = self._build_prompt(task, packet)
            model_text = await self._generate(prompt)
            decision = self.policy.apply(model_text, task, packet)
            result = self._result_from_decision(
                task,
                trace_id,
                "miss",
                decision,
                [str(artifact.get("id", "")) for artifact in packet.artifacts],
                self._prompt_summary(packet),
                started,
                packet.timings_ms,
            )
            payload = CachedResponse(
                response=result.response,
                policy_version=self.policy.version,
                model_id=task.model_id,
                index_fingerprint=key.index_fingerprint,
                quality_flags=result.quality_flags,
            ).to_json()
            if cache_available:
                await self._store_cache_payload(task, key, payload)
            return result
        finally:
            if cache_available and lock_acquired:
                await self._safe_release_lock(task, key)

    def _retrieve(self, task: TaskSpec, index_fingerprint: str) -> RetrievalPacket:
        searcher = HybridSearcher(self.store)
        reranker = LexicalReranker()
        search_started = time.perf_counter()
        candidates = searcher.search(task.query, tier_rank(task.access_tier), repo_scope=task.repo_scopes)
        search_ms = (time.perf_counter() - search_started) * 1000
        rerank_started = time.perf_counter()
        ranked = reranker.rerank(task.query, candidates, top_m=8)
        rerank_ms = (time.perf_counter() - rerank_started) * 1000
        summaries_text = self.summarizer.summarize_chunks(ranked) if ranked else ""
        summaries = [line for line in summaries_text.splitlines() if line.strip()]
        return RetrievalPacket(
            artifacts=ranked,
            summaries=summaries,
            timings_ms={"search": search_ms, "rerank": rerank_ms},
            index_fingerprint=index_fingerprint,
            policy_version=self.policy.version,
        )

    def _build_prompt(self, task: TaskSpec, packet: RetrievalPacket) -> str:
        system_rule = (
            "You are a read-only codebase intelligence assistant. "
            f"The authenticated user's access tier is {task.access_tier.value}. "
            "Use only the provided retrieved summaries and do not infer inaccessible implementation details. "
            "Do not answer by listing file paths, raw filenames, or copied source. "
            "Summarize behavior in terms of symbols, responsibilities, and call relationships. "
            f"{self._response_mode_instruction(task.response_mode)}"
        )
        return PromptAssembler(system_rule, self.summarizer).assemble(task.query, packet.artifacts)

    async def _generate(self, prompt: str) -> str:
        chunks = []
        async for chunk in self.model.generate_stream(prompt):
            chunks.append(chunk)
        return "".join(chunks)

    async def _get_cached_payload(self, task: TaskSpec, key: HarnessCacheKey) -> str | None:
        payload = await self.cache.get_cached_response(
            task.query,
            task.access_tier,
            task.repo_scopes,
            response_mode=task.response_mode,
            model_id=task.model_id,
            index_fingerprint=key.index_fingerprint,
        )
        if payload is not None:
            return payload
        return await self.cache.get_cached_response(task.query, task.access_tier, task.repo_scopes)

    async def _set_cached_payload(self, task: TaskSpec, key: HarnessCacheKey, payload: str) -> None:
        await self.cache.set_cached_response(
            task.query,
            task.access_tier,
            task.repo_scopes,
            payload,
            response_mode=task.response_mode,
            model_id=task.model_id,
            index_fingerprint=key.index_fingerprint,
        )

    async def _acquire_lock(self, task: TaskSpec, key: HarnessCacheKey) -> bool:
        return await self.cache.acquire_lock(
            task.query,
            task.access_tier,
            task.repo_scopes,
            response_mode=task.response_mode,
            model_id=task.model_id,
            index_fingerprint=key.index_fingerprint,
        )

    async def _collect_coalesced_response(self, task: TaskSpec, key: HarnessCacheKey) -> str:
        chunks = []
        async for chunk in self.cache.subscribe(
            task.query,
            task.access_tier,
            task.repo_scopes,
            response_mode=task.response_mode,
            model_id=task.model_id,
            index_fingerprint=key.index_fingerprint,
        ):
            chunks.append(chunk)
        payload = "".join(chunks)
        cached = CachedResponse.from_json(payload)
        return cached.response if cached is not None else payload

    async def _publish(self, task: TaskSpec, key: HarnessCacheKey, payload: str) -> None:
        await self.cache.publish(
            task.query,
            task.access_tier,
            task.repo_scopes,
            payload,
            response_mode=task.response_mode,
            model_id=task.model_id,
            index_fingerprint=key.index_fingerprint,
        )

    async def _store_cache_payload(self, task: TaskSpec, key: HarnessCacheKey, payload: str) -> None:
        try:
            await self._set_cached_payload(task, key, payload)
        except Exception:
            logger.exception("Cache write failed; continuing without storing response")
        try:
            await self._publish(task, key, payload)
        except Exception:
            logger.exception("Cache publish failed; continuing without notifying coalesced subscribers")

    async def _safe_release_lock(self, task: TaskSpec, key: HarnessCacheKey) -> None:
        try:
            await self._release_lock(task, key)
        except Exception:
            logger.exception("Cache lock release failed after query completion")

    async def _release_lock(self, task: TaskSpec, key: HarnessCacheKey) -> None:
        await self.cache.release_lock(
            task.query,
            task.access_tier,
            task.repo_scopes,
            response_mode=task.response_mode,
            model_id=task.model_id,
            index_fingerprint=key.index_fingerprint,
        )

    def _cached_decision(self, payload: str | None) -> PolicyDecision | None:
        if payload is None:
            return None
        cached = CachedResponse.from_json(payload)
        text = cached.response if cached is not None else payload
        return self.policy.sanitize_cached(text)

    def _result_from_decision(
        self,
        task: TaskSpec,
        trace_id: str,
        cache_status: str,
        decision: PolicyDecision,
        retrieval_ids: list[str],
        prompt_summary: str,
        started: float,
        retrieval_timings: dict[str, float] | None = None,
    ) -> HarnessResult:
        timings = dict(retrieval_timings or {})
        timings["total"] = (time.perf_counter() - started) * 1000
        record = TraceRecord(
            trace_id=trace_id,
            user_id=task.user_id,
            query=task.query,
            repo_scopes=task.repo_scopes,
            access_tier=task.access_tier.value,
            model_id=task.model_id,
            cache_status=cache_status,
            retrieval_ids=[item for item in retrieval_ids if item],
            prompt_summary=prompt_summary,
            response=decision.response,
            quality_flags=decision.flags,
            timings_ms=timings,
        )
        self.trace_recorder.record(record)
        return HarnessResult(
            response=decision.response,
            cache_status=cache_status,
            trace_id=trace_id,
            timings_ms=timings,
            quality_flags=decision.flags,
            inference_engine_used=task.model_id,
        )

    def _prompt_summary(self, packet: RetrievalPacket) -> str:
        return "\n".join(packet.summaries[:8])

    def _index_fingerprint(self, repo_scopes: list[str]) -> str:
        if hasattr(self.store, "index_fingerprint"):
            return str(self.store.index_fingerprint(repo_scopes))
        return "unknown-index"

    @staticmethod
    def _normalize_query(query: str) -> str:
        return " ".join(query.strip().lower().split())

    @staticmethod
    def _response_mode_instruction(response_mode: str) -> str:
        if response_mode == "deep":
            return "Give a detailed explanation with the main evidence and caveats."
        if response_mode == "paragraph":
            return "Answer in one or two concise paragraphs."
        return "Answer in a short, direct summary."
