import asyncio
from pathlib import Path

import pytest

from src.gateway.models import AccessTier
from src.gateway.services import CacheService, InMemorySemanticCacheRepository
from src.harness.cache import CachedResponse, HarnessCacheKey
from src.harness.models import TaskSpec
from src.harness.service import HarnessService
from src.harness.trace import InMemoryTraceRecorder
from src.retrieval.database import ArtifactRecord, HashingEmbeddingProvider, SQLiteUnifiedStore


class FakeModelAdapter:
    def __init__(self, chunks: list[str], model_id: str = "fake-model"):
        self.model_id = model_id
        self.chunks = chunks
        self.prompts: list[str] = []

    async def generate_stream(self, prompt: str):
        self.prompts.append(prompt)
        for chunk in self.chunks:
            await asyncio.sleep(0)
            yield chunk


def _store(tmp_path: Path, artifacts: list[ArtifactRecord] | None = None) -> SQLiteUnifiedStore:
    store = SQLiteUnifiedStore(tmp_path / "index.db", HashingEmbeddingProvider(dimensions=16))
    if artifacts:
        store.upsert_artifacts(artifacts)
    return store


def _task() -> TaskSpec:
    return TaskSpec(
        query="How does checkout authorization work?",
        user_id="user-1",
        access_tier=AccessTier.T1,
        repo_scopes=["repo-a"],
        model_id="fake-model",
    )


def _checkout_artifact() -> ArtifactRecord:
    return ArtifactRecord(
        artifact_id="repo-a:checkout",
        repository="repo-a",
        file_path="src/services/checkout.ts",
        language="typescript",
        text="class CheckoutService { authorize() { return validate(); } }",
        tier=1,
        fidelity="L-1",
        symbol_name="CheckoutService",
        line_start=1,
        line_end=5,
        kind="class",
    )


@pytest.mark.asyncio
async def test_harness_cache_key_includes_policy_model_scope_tier_mode_and_index(tmp_path: Path):
    store = _store(tmp_path, [_checkout_artifact()])
    cache = CacheService(InMemorySemanticCacheRepository())
    trace = InMemoryTraceRecorder()
    model = FakeModelAdapter(["CheckoutService validates checkout authorization."])
    harness = HarnessService(store=store, cache=cache, model=model, trace_recorder=trace)
    task = _task()

    key = harness.cache_key_for(task)

    assert key.normalized_query == "how does checkout authorization work?"
    assert key.access_tier == AccessTier.T1.value
    assert key.repo_scopes == ("repo-a",)
    assert key.response_mode == "answer"
    assert key.model_id == "fake-model"
    assert key.index_fingerprint == store.index_fingerprint(["repo-a"])
    assert key.policy_version.startswith("response-policy-")


@pytest.mark.asyncio
async def test_harness_shapes_legacy_cache_payloads_and_records_trace(tmp_path: Path):
    store = _store(tmp_path, [_checkout_artifact()])
    repo = InMemorySemanticCacheRepository()
    cache = CacheService(repo)
    trace = InMemoryTraceRecorder()
    model = FakeModelAdapter(["model should not run"])
    harness = HarnessService(store=store, cache=cache, model=model, trace_recorder=trace)
    task = _task()
    await repo.set(
        cache._generate_key(
            task.query,
            task.access_tier,
            task.repo_scopes,
            response_mode=task.response_mode,
            model_id=task.model_id,
            index_fingerprint=store.index_fingerprint(task.repo_scopes),
        ),
        "\n".join(
            [
                "--- File: src/services/checkout.ts | Language: typescript | Tier: 1 ---",
                "class CheckoutService {",
                "  authorize() { return validate(); }",
                "}",
            ]
        ),
        3600,
    )

    result = await harness.execute(task)

    assert result.cache_status == "hit"
    assert "CheckoutService is a TypeScript class tied to authorize and validate." in result.response
    assert "src/services/checkout.ts" not in result.response
    assert model.prompts == []
    assert trace.records[0].cache_status == "hit"
    assert trace.records[0].trace_id == result.trace_id


@pytest.mark.asyncio
async def test_harness_misses_invalid_legacy_cache_and_uses_model_then_policy(tmp_path: Path):
    store = _store(tmp_path, [_checkout_artifact()])
    repo = InMemorySemanticCacheRepository()
    cache = CacheService(repo)
    trace = InMemoryTraceRecorder()
    model = FakeModelAdapter(["Relevant files:\n- src/services/checkout.ts"])
    harness = HarnessService(store=store, cache=cache, model=model, trace_recorder=trace)
    task = _task()
    key = cache._generate_key(
        task.query,
        task.access_tier,
        task.repo_scopes,
        response_mode=task.response_mode,
        model_id=task.model_id,
        index_fingerprint=store.index_fingerprint(task.repo_scopes),
    )
    await repo.set(key, "Relevant files:\n- src/services/checkout.ts", 3600)

    result = await harness.execute(task)

    assert result.cache_status == "miss"
    assert len(model.prompts) == 1
    assert "CheckoutService is a TypeScript class tied to authorize and validate." in result.response
    assert "src/services/checkout.ts" not in result.response
    cached = CachedResponse.from_json(await repo.get(key))
    assert cached is not None
    assert cached.response == result.response


@pytest.mark.asyncio
async def test_harness_coalesced_request_receives_final_shaped_response(tmp_path: Path):
    store = _store(tmp_path, [_checkout_artifact()])
    cache = CacheService(InMemorySemanticCacheRepository())
    trace = InMemoryTraceRecorder()
    model = FakeModelAdapter(["Relevant files:\n", "- src/services/checkout.ts"])
    harness = HarnessService(store=store, cache=cache, model=model, trace_recorder=trace)
    task = _task()

    first, second = await asyncio.gather(harness.execute(task), harness.execute(task))

    assert first.response == second.response
    assert "CheckoutService is a TypeScript class tied to authorize and validate." in first.response
    assert "src/services/checkout.ts" not in second.response
    assert sorted(record.cache_status for record in trace.records) == ["coalesced", "miss"]
    assert len(model.prompts) == 1


def test_harness_cache_key_value_changes_for_core_dimensions():
    base = HarnessCacheKey(
        normalized_query="q",
        access_tier="T-1",
        repo_scopes=("repo-a",),
        response_mode="answer",
        model_id="model-a",
        index_fingerprint="fp-a",
        policy_version="response-policy-v3",
    )

    assert base.digest() != HarnessCacheKey(**{**base.__dict__, "model_id": "model-b"}).digest()
    assert base.digest() != HarnessCacheKey(**{**base.__dict__, "access_tier": "T-2"}).digest()
    assert base.digest() != HarnessCacheKey(**{**base.__dict__, "repo_scopes": ("repo-b",)}).digest()
    assert base.digest() != HarnessCacheKey(**{**base.__dict__, "response_mode": "debug"}).digest()
    assert base.digest() != HarnessCacheKey(**{**base.__dict__, "index_fingerprint": "fp-b"}).digest()
    assert base.digest() != HarnessCacheKey(**{**base.__dict__, "policy_version": "response-policy-v4"}).digest()
