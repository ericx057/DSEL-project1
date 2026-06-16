import pytest
from unittest.mock import patch, MagicMock
from retrieval.reranker import LexicalReranker, Reranker

def test_reranker_mock_scoring():
    reranker = Reranker(use_mock=True)
    chunks = [
        {"id": "1", "text": "This is a random document about apples."},
        {"id": "2", "text": "This document specifically mentions the query keyword."},
        {"id": "3", "text": "Nothing to see here."}
    ]
    query = "query keyword"
    
    top_chunks = reranker.rerank(query, chunks, top_m=2)
    assert len(top_chunks) == 2
    assert top_chunks[0]["id"] == "2" # Has both "query" and "keyword"
    assert "rerank_score" in top_chunks[0]
    assert top_chunks[0]["rerank_score"] > 0

def test_reranker_empty_chunks():
    reranker = Reranker(use_mock=True)
    assert reranker.rerank("query", []) == []

@patch("retrieval.reranker.CrossEncoder")
def test_reranker_real_scoring(MockCrossEncoder):
    # Setup mock
    mock_model = MagicMock()
    # Predict returns high score for the second document
    mock_model.predict.return_value = [0.1, 0.9, 0.2]
    MockCrossEncoder.return_value = mock_model
    
    reranker = Reranker(use_mock=False)
    
    chunks = [
        {"id": "1", "text": "bad match"},
        {"id": "2", "text": "good match"},
        {"id": "3", "text": "okay match"}
    ]
    query = "match"
    
    top_chunks = reranker.rerank(query, chunks, top_m=2)
    assert len(top_chunks) == 2
    assert top_chunks[0]["id"] == "2"
    assert top_chunks[0]["rerank_score"] == 0.9
    assert top_chunks[1]["id"] == "3"
    assert top_chunks[1]["rerank_score"] == 0.2

@patch("retrieval.reranker.CrossEncoder", None)
def test_reranker_missing_library():
    with pytest.raises(ImportError):
        Reranker(use_mock=False)


def test_lexical_reranker_prioritizes_exact_paths_and_extensions():
    reranker = LexicalReranker()
    chunks = [
        {"id": "generic", "file_path": "README.md", "text": "generic schema examples"},
        {
            "id": "target",
            "file_path": "examples/widget.part",
            "text": "metadata.material = Steel",
        },
        {
            "id": "schema",
            "file_path": "schemas/part.schema.json",
            "text": "title = Generic Part Schema",
        },
    ]

    ranked = reranker.rerank(
        "In examples/widget.part, what is metadata.material and the .part schema title?",
        chunks,
        top_m=3,
    )

    assert ranked[0]["id"] == "target"
    assert ranked[1]["id"] == "schema"


def test_lexical_reranker_uses_text_matches_without_filename_policy_boosts():
    reranker = LexicalReranker()
    chunks = [
        {
            "id": "directory-file",
            "file_path": "docs/reference.md",
            "text": "API reference",
        },
        {
            "id": "rules",
            "file_path": "RULES.md",
            "text": "Files under `docs/` require Platform approval before release.",
        },
        {
            "id": "owner",
            "file_path": "OWNERS.md",
            "text": "The Platform team owns approval for files under `docs/`.",
        },
    ]

    ranked = reranker.rerank(
        "Which rules explain approval for `docs/` files?",
        chunks,
        top_m=3,
    )

    assert [item["id"] for item in ranked[:2]] == ["rules", "owner"]


def test_lexical_reranker_keeps_file_diversity_before_duplicates():
    reranker = LexicalReranker()
    chunks = [
        {"id": "a1", "file_path": "a.md", "text": "query query query"},
        {"id": "a2", "file_path": "a.md", "text": "query query"},
        {"id": "b1", "file_path": "b.md", "text": "query"},
    ]

    ranked = reranker.rerank("query", chunks, top_m=2)

    assert [item["id"] for item in ranked] == ["a1", "b1"]


def test_lexical_reranker_keeps_basename_diversity_before_sibling_configs():
    reranker = LexicalReranker()
    chunks = [
        {"id": "root-config", "file_path": "pyproject.toml", "text": "project metadata"},
        {"id": "example-config", "file_path": "examples/demo/pyproject.toml", "text": "project metadata"},
        {"id": "doc", "file_path": "docs/install.rst", "text": "install docs"},
    ]

    ranked = reranker.rerank("Which `install.rst` documentation page and `pyproject.toml` file?", chunks, top_m=3)

    assert {item["id"] for item in ranked[:2]} == {"doc", "root-config"}


def test_lexical_reranker_boosts_generic_path_tokens_and_light_stems():
    reranker = LexicalReranker()
    chunks = [
        {"id": "generic", "file_path": "docs/overview.md", "text": "schema version release"},
        {"id": "version", "file_path": "VERSION", "text": "1.2.3"},
        {"id": "script", "file_path": "tools/validate_repo.py", "text": "checks schema files"},
    ]

    ranked = reranker.rerank("Which validation script checks the version string?", chunks, top_m=3)

    assert {item["id"] for item in ranked[:2]} == {"script", "version"}


def test_lexical_reranker_prefers_exact_class_for_named_class_query():
    reranker = LexicalReranker()
    chunks = [
        {
            "id": "class",
            "file_path": "src/ingestion/indexer.py",
            "symbol_name": "RepositoryIndexer",
            "kind": "class",
            "text": "class RepositoryIndexer",
            "metadata": {"qualified_name": "RepositoryIndexer"},
        },
        {
            "id": "method",
            "file_path": "src/ingestion/indexer.py",
            "symbol_name": "_is_json_document",
            "kind": "method",
            "text": "def _is_json_document(cls, path, content)",
            "metadata": {"qualified_name": "RepositoryIndexer._is_json_document"},
        },
        {
            "id": "test-noise",
            "file_path": "tests/test_window.py",
            "symbol_name": "test_window_visible",
            "kind": "function",
            "text": "def test_window_visible(): pass",
            "metadata": {"qualified_name": "test_window_visible"},
        },
    ]

    ranked = reranker.rerank("What does RepositoryIndexer do?", chunks, top_m=3)

    assert ranked[0]["id"] == "class"


def test_lexical_reranker_prefers_owner_method_for_action_query():
    reranker = LexicalReranker()
    chunks = [
        {
            "id": "class",
            "file_path": "src/gateway/services.py",
            "symbol_name": "CacheService",
            "kind": "class",
            "text": "class CacheService",
            "metadata": {"qualified_name": "CacheService"},
        },
        {
            "id": "method",
            "file_path": "src/gateway/services.py",
            "symbol_name": "_generate_key",
            "kind": "method",
            "text": "def _generate_key(self, query, tier, scopes, response_mode, model_id, index_fingerprint)",
            "metadata": {"qualified_name": "CacheService._generate_key"},
        },
        {
            "id": "noise",
            "file_path": "tests/test_hooks.py",
            "symbol_name": "generate",
            "kind": "method",
            "text": "def generate(self): pass",
            "metadata": {"qualified_name": "MockModel.generate"},
        },
    ]

    ranked = reranker.rerank("How does CacheService generate cache keys?", chunks, top_m=3)

    assert ranked[0]["id"] == "method"


def test_lexical_reranker_prefers_same_symbol_implementation_over_interface():
    reranker = LexicalReranker()
    chunks = [
        {
            "id": "interface",
            "file_path": "src/ingestion/indexer.py",
            "symbol_name": "RepositoryIndexer",
            "kind": "class",
            "text": "class RepositoryIndexer",
            "metadata": {"qualified_name": "RepositoryIndexer"},
        },
        {
            "id": "implementation",
            "file_path": "src/ingestion/indexer.py",
            "symbol_name": "RepositoryIndexer",
            "kind": "class-implementation",
            "text": "class RepositoryIndexer index_repository _iter_files _index_file upsert_artifacts upsert_edges",
            "metadata": {"qualified_name": "RepositoryIndexer"},
        },
    ]

    ranked = reranker.rerank("What does RepositoryIndexer do?", chunks, top_m=1)

    assert ranked[0]["id"] == "implementation"


def test_lexical_reranker_keeps_same_owner_methods_for_named_class_query():
    reranker = LexicalReranker()
    chunks = [
        {
            "id": "implementation",
            "file_path": "src/ingestion/indexer.py",
            "symbol_name": "RepositoryIndexer",
            "kind": "class-implementation",
            "text": "class RepositoryIndexer",
            "metadata": {"qualified_name": "RepositoryIndexer"},
        },
        {
            "id": "index-method",
            "file_path": "src/ingestion/indexer.py",
            "symbol_name": "index_repository",
            "kind": "method",
            "text": "def index_repository(self, repository, repo_path)",
            "metadata": {"qualified_name": "RepositoryIndexer.index_repository"},
        },
        {
            "id": "noise",
            "file_path": "src/other.py",
            "symbol_name": "OtherThing",
            "kind": "class",
            "text": "class OtherThing",
            "metadata": {"qualified_name": "OtherThing"},
        },
    ]

    ranked = reranker.rerank("What does RepositoryIndexer do?", chunks, top_m=2)

    assert [item["id"] for item in ranked] == ["implementation", "index-method"]
