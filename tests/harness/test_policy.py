from src.harness.models import RetrievalPacket, TaskSpec
from src.harness.policy import ResponsePolicy
from src.gateway.models import AccessTier


def _task(query: str = "How does checkout authorization work?") -> TaskSpec:
    return TaskSpec(
        query=query,
        user_id="user-1",
        access_tier=AccessTier.T1,
        repo_scopes=["repo-a"],
        model_id="test-model",
    )


def _packet(*summaries: str) -> RetrievalPacket:
    return RetrievalPacket(
        artifacts=[
            {
                "id": f"artifact-{index}",
                "repository": "repo-a",
                "file_path": f"src/example{index}.ts",
                "language": "typescript",
                "kind": "class",
                "symbol_name": "CheckoutService",
                "text": "class CheckoutService { authorize() { return validate(); } }",
                "tier": 1,
            }
            for index, _ in enumerate(summaries, start=1)
        ],
        summaries=list(summaries),
        timings_ms={"search": 1.0, "rerank": 1.0},
        index_fingerprint="fp-1",
        policy_version="response-policy-v3",
    )


def test_policy_replaces_path_list_answer_with_concrete_fallback():
    packet = _packet(
        "[1] CheckoutService (class, typescript, lines 1-5) - Mentions CheckoutService, authorize, validate."
    )

    decision = ResponsePolicy().apply(
        "Relevant files:\n- src/services/checkout.ts\n- tests/test_checkout.ts",
        _task(),
        packet,
    )

    assert decision.accepted is False
    assert decision.source == "fallback"
    assert "CheckoutService is a TypeScript class tied to authorize and validate." in decision.response
    assert "src/services/checkout.ts" not in decision.response
    assert "Relevant files" not in decision.response


def test_policy_replaces_abstract_answer_when_evidence_has_behavioral_terms():
    packet = _packet(
        "[1] CheckoutService (class, typescript, lines 1-5) - Mentions CheckoutService, authorize, validate."
    )

    decision = ResponsePolicy().apply("CheckoutService is a class in TypeScript.", _task(), packet)

    assert decision.accepted is False
    assert "authorize and validate" in decision.response
    assert "is a class in TypeScript." not in decision.response


def test_policy_explains_thin_declaration_only_evidence():
    packet = _packet("[1] RepositoryIndexer (class, python, lines 1-2) - Mentions RepositoryIndexer.")

    decision = ResponsePolicy().apply("", _task("What does RepositoryIndexer do?"), packet)

    assert decision.source == "fallback"
    assert "indexed context is too thin for a behavioral answer" in decision.response
    assert "RepositoryIndexer is a Python class." in decision.response
    assert "does not show methods or behavior" in decision.response


def test_policy_no_hits_avoids_speculation():
    decision = ResponsePolicy().apply("", _task("Where is payment handled?"), RetrievalPacket.empty("fp-0"))

    assert decision.source == "fallback"
    assert decision.response == "No indexed context matched `Where is payment handled?`."
