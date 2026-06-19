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


def test_policy_replaces_embedded_abstract_evidence_shell():
    packet = RetrievalPacket(
        artifacts=[
            {
                "id": "repo-a:indexer",
                "repository": "repo-a",
                "file_path": "src/ingestion/indexer.py",
                "language": "python",
                "kind": "class-implementation",
                "symbol_name": "RepositoryIndexer",
                "text": "class RepositoryIndexer index_repository _iter_files _index_file upsert_artifacts",
                "tier": 3,
                "metadata": {"qualified_name": "RepositoryIndexer"},
            }
        ],
        summaries=[
            "[1] RepositoryIndexer (class-implementation, python, lines 1-40) - Mentions RepositoryIndexer, index_repository, _iter_files, _index_file, upsert_artifacts."
        ],
        timings_ms={},
        index_fingerprint="fp-1",
        policy_version="response-policy-v3",
    )
    model_output = (
        "I found relevant indexed context for: summary: What does RepositoryIndexer do?\n\n"
        "Most relevant evidence:\n"
        "- RepositoryIndexer is a class in python."
    )

    decision = ResponsePolicy().apply(model_output, _task("What does RepositoryIndexer do?"), packet)

    assert decision.accepted is False
    assert "RepositoryIndexer's retrieved implementation indexes repositories" in decision.response
    assert "iterates files" in decision.response
    assert "RepositoryIndexer is a class in python" not in decision.response


def test_policy_fallback_does_not_dilute_class_implementation_summary():
    packet = RetrievalPacket(
        artifacts=[
            {
                "id": "repo-a:indexer-impl",
                "repository": "repo-a",
                "file_path": "src/ingestion/indexer.py",
                "language": "python",
                "kind": "class-implementation",
                "symbol_name": "RepositoryIndexer",
                "text": "class RepositoryIndexer index_repository _iter_files _is_excluded",
                "tier": 3,
                "metadata": {"qualified_name": "RepositoryIndexer"},
            },
            {
                "id": "repo-a:indexer-class",
                "repository": "repo-a",
                "file_path": "src/ingestion/indexer.py",
                "language": "python",
                "kind": "class",
                "symbol_name": "RepositoryIndexer",
                "text": "class RepositoryIndexer",
                "tier": 1,
                "metadata": {"qualified_name": "RepositoryIndexer"},
            },
        ],
        summaries=[
            "[1] RepositoryIndexer (class-implementation, python, lines 1-40) - Mentions RepositoryIndexer, index_repository, _iter_files, _is_excluded.",
            "[2] RepositoryIndexer (class, python, lines 1-2) - Mentions RepositoryIndexer.",
        ],
        timings_ms={},
        index_fingerprint="fp-1",
        policy_version="response-policy-v3",
    )

    decision = ResponsePolicy().apply("", _task("What does RepositoryIndexer do?"), packet)

    assert "RepositoryIndexer's retrieved implementation indexes repositories" in decision.response
    assert "only identifies the class" not in decision.response


def test_policy_replaces_artifact_label_implementation_answer():
    packet = RetrievalPacket(
        artifacts=[
            {
                "id": "repo-a:indexer-impl",
                "repository": "repo-a",
                "file_path": "src/ingestion/indexer.py",
                "language": "python",
                "kind": "class-implementation",
                "symbol_name": "RepositoryIndexer",
                "text": "class RepositoryIndexer index_repository _iter_files _is_excluded",
                "tier": 3,
                "metadata": {"qualified_name": "RepositoryIndexer"},
            }
        ],
        summaries=[
            "[1] RepositoryIndexer (class-implementation, python, lines 1-40) - Mentions RepositoryIndexer, index_repository, _iter_files, _is_excluded."
        ],
        timings_ms={},
        index_fingerprint="fp-1",
        policy_version="response-policy-v3",
    )

    decision = ResponsePolicy().apply(
        "For `What does RepositoryIndexer do?`, the useful retrieved signals are:\n"
        "- RepositoryIndexer is a Python class-implementation tied to index_repository and _iter_files.",
        _task("What does RepositoryIndexer do?"),
        packet,
    )

    assert decision.accepted is False
    assert "RepositoryIndexer's retrieved implementation indexes repositories" in decision.response
    assert "class-implementation tied to" not in decision.response


def test_policy_replaces_inference_error_with_retrieval_fallback():
    packet = RetrievalPacket(
        artifacts=[
            {
                "id": "repo-a:indexer-impl",
                "repository": "repo-a",
                "file_path": "src/ingestion/indexer.py",
                "language": "python",
                "kind": "class-implementation",
                "symbol_name": "RepositoryIndexer",
                "text": "class RepositoryIndexer index_repository _iter_files _is_excluded",
                "tier": 3,
                "metadata": {"qualified_name": "RepositoryIndexer"},
            }
        ],
        summaries=[
            "[1] RepositoryIndexer (class-implementation, python, lines 1-40) - Mentions RepositoryIndexer, index_repository, _iter_files, _is_excluded."
        ],
        timings_ms={},
        index_fingerprint="fp-1",
        policy_version="response-policy-v3",
    )

    decision = ResponsePolicy().apply(
        "\n[Inference Error: local inference engine unavailable]",
        _task("What does RepositoryIndexer do?"),
        packet,
    )

    assert decision.accepted is False
    assert decision.source == "fallback"
    assert "RepositoryIndexer's retrieved implementation indexes repositories" in decision.response
    assert "Inference Error" not in decision.response


def test_policy_fallback_hides_method_implementation_label():
    packet = RetrievalPacket(
        artifacts=[
            {
                "id": "repo-a:generic-symbols",
                "repository": "repo-a",
                "file_path": "src/parsers/generic_symbols.py",
                "language": "python",
                "kind": "method-implementation",
                "symbol_name": "_symbols",
                "text": "def _symbols(self, lines, language): return parse_typescript_go_rust_symbols(lines, language)",
                "tier": 3,
                "metadata": {"qualified_name": "GenericSymbolParser._symbols"},
            }
        ],
        summaries=[
            "[1] _symbols (method-implementation, python, lines 1-20) - Mentions _symbols, lines, language, parse_typescript_go_rust_symbols."
        ],
        timings_ms={},
        index_fingerprint="fp-1",
        policy_version="response-policy-v3",
    )

    decision = ResponsePolicy().apply(
        "def _symbols(self, lines, language):\n    return []",
        _task("How does GenericSymbolParser handle TypeScript or Go symbols?"),
        packet,
    )

    assert "_symbols is a Python method tied to lines, language, and parse_typescript_go_rust_symbols." in decision.response
    assert "method-implementation" not in decision.response


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


def test_policy_no_hits_ignores_unrelated_retrieval_noise():
    packet = RetrievalPacket(
        artifacts=[
            {
                "id": "repo-a:retrieval-engine",
                "repository": "repo-a",
                "file_path": "demo.py",
                "language": "python",
                "kind": "method",
                "symbol_name": "__init__",
                "text": "def __init__(self, store, searcher)",
                "tier": 1,
                "metadata": {"qualified_name": "RetrievalEngine.__init__"},
            }
        ],
        summaries=[
            "[1] __init__ (method, python, lines 1-2) - Mentions __init__, store, searcher."
        ],
        timings_ms={},
        index_fingerprint="fp-1",
        policy_version="response-policy-v3",
    )

    decision = ResponsePolicy().apply("", _task("How does the payout settlement engine work?"), packet)

    assert decision.source == "fallback"
    assert decision.response == "No indexed context matched `How does the payout settlement engine work?`."
    assert "RetrievalEngine" not in decision.response


def test_policy_no_hits_ignores_generic_engine_class_overlap():
    packet = RetrievalPacket(
        artifacts=[
            {
                "id": "repo-a:retrieval-engine",
                "repository": "repo-a",
                "file_path": "demo.py",
                "language": "python",
                "kind": "class",
                "symbol_name": "RetrievalEngine",
                "text": "class RetrievalEngine: def search(self, query): pass",
                "tier": 1,
                "metadata": {"qualified_name": "RetrievalEngine"},
            }
        ],
        summaries=[
            "[1] RetrievalEngine (class, python, lines 1-5) - Mentions RetrievalEngine, search, query."
        ],
        timings_ms={},
        index_fingerprint="fp-1",
        policy_version="response-policy-v3",
    )

    decision = ResponsePolicy().apply("", _task("How does the payout settlement engine work?"), packet)

    assert decision.response == "No indexed context matched `How does the payout settlement engine work?`."


def test_policy_no_hits_when_named_query_has_no_symbol_anchor():
    packet = RetrievalPacket(
        artifacts=[
            {
                "id": "repo-a:indexer",
                "repository": "repo-a",
                "file_path": "src/ingestion/indexer.py",
                "language": "python",
                "kind": "class-implementation",
                "symbol_name": "RepositoryIndexer",
                "text": "class RepositoryIndexer relative_path index_repository _iter_files",
                "tier": 3,
                "metadata": {"qualified_name": "RepositoryIndexer"},
            }
        ],
        summaries=[
            "[1] RepositoryIndexer (class-implementation, python, lines 1-40) - Mentions RepositoryIndexer, relative_path, index_repository, _iter_files."
        ],
        timings_ms={},
        index_fingerprint="fp-1",
        policy_version="response-policy-v3",
    )
    query = "Explain velvet taxonomy in the ZzyzxQuasarProtocol and its relation to parquet flooring."

    decision = ResponsePolicy().apply("", _task(query), packet)

    assert decision.response == f"No indexed context matched `{query}`."
    assert "RepositoryIndexer" not in decision.response


def test_policy_no_hits_ignores_repository_word_in_obscure_prompt():
    packet = RetrievalPacket(
        artifacts=[
            {
                "id": "repo-a:indexer",
                "repository": "repo-a",
                "file_path": "src/ingestion/indexer.py",
                "language": "python",
                "kind": "class",
                "symbol_name": "RepositoryIndexer",
                "text": "class RepositoryIndexer indexes repositories",
                "tier": 1,
                "metadata": {"qualified_name": "RepositoryIndexer"},
            }
        ],
        summaries=[
            "[1] RepositoryIndexer (class, python, lines 1-2) - Mentions RepositoryIndexer."
        ],
        timings_ms={},
        index_fingerprint="fp-1",
        policy_version="response-policy-v3",
    )
    query = "Does the repository mention a purple astrolabe negotiating Byzantine pottery?"

    decision = ResponsePolicy().apply("", _task(query), packet)

    assert decision.response == f"No indexed context matched `{query}`."


def test_policy_fallback_filters_unrelated_retrieved_artifacts():
    packet = RetrievalPacket(
        artifacts=[
            {
                "id": "repo-a:indexer",
                "repository": "repo-a",
                "file_path": "src/ingestion/indexer.py",
                "language": "python",
                "kind": "class",
                "symbol_name": "RepositoryIndexer",
                "text": "class RepositoryIndexer",
                "tier": 1,
                "metadata": {"qualified_name": "RepositoryIndexer"},
            },
            {
                "id": "repo-a:test-noise",
                "repository": "repo-a",
                "file_path": "tests/test_window.py",
                "language": "python",
                "kind": "function",
                "symbol_name": "test_window_visible",
                "text": "def test_window_visible(): pass",
                "tier": 1,
                "metadata": {"qualified_name": "test_window_visible"},
            },
        ],
        summaries=[
            "[1] RepositoryIndexer (class, python, lines 1-2) - Mentions RepositoryIndexer.",
            "[2] test_window_visible (function, python, lines 5-6) - Mentions test_window_visible.",
        ],
        timings_ms={},
        index_fingerprint="fp-1",
        policy_version="response-policy-v3",
    )

    decision = ResponsePolicy().apply("RepositoryIndexer is a class in Python.", _task("What does RepositoryIndexer do?"), packet)

    assert "RepositoryIndexer is a Python class." in decision.response
    assert "test_window_visible" not in decision.response
    assert "indexed context is too thin for a behavioral answer" in decision.response


def test_policy_fallback_keeps_artifacts_for_named_owner_not_word_overlap_helpers():
    packet = RetrievalPacket(
        artifacts=[
            {
                "id": "repo-a:generate-key",
                "repository": "repo-a",
                "file_path": "src/gateway/services.py",
                "language": "python",
                "kind": "method",
                "symbol_name": "_generate_key",
                "text": "def _generate_key(self, query, tier, scopes, response_mode, model_id)",
                "tier": 1,
                "metadata": {"qualified_name": "CacheService._generate_key"},
            },
            {
                "id": "repo-a:get-cache-service",
                "repository": "repo-a",
                "file_path": "src/gateway/main.py",
                "language": "python",
                "kind": "function",
                "symbol_name": "get_cache_service",
                "text": "def get_cache_service(repo)",
                "tier": 1,
                "metadata": {"qualified_name": "get_cache_service"},
            },
        ],
        summaries=[
            "[1] _generate_key (method, python, lines 1-2) - Mentions _generate_key, query, tier, scopes, response_mode, model_id.",
            "[2] get_cache_service (function, python, lines 1-2) - Mentions get_cache_service, repo.",
        ],
        timings_ms={},
        index_fingerprint="fp-1",
        policy_version="response-policy-v3",
    )

    decision = ResponsePolicy().apply(
        "Relevant files:\n- src/gateway/services.py",
        _task("How does CacheService generate cache keys?"),
        packet,
    )

    assert "_generate_key is a Python method" in decision.response
    assert "get_cache_service" not in decision.response
