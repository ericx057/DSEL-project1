import pytest
from pathlib import Path

from retrieval.database import ArtifactRecord, HashingEmbeddingProvider, InMemoryUnifiedStore, SQLiteUnifiedStore
from retrieval.hybrid import HybridSearcher
from retrieval.reranker import LexicalReranker

@pytest.fixture
def store():
    data = [
        {"id": "1", "text": "public doc", "tier": 0},
        {"id": "2", "text": "secret doc", "tier": 2},
        {"id": "3", "text": "top secret", "tier": 3},
        {"id": "4", "text": "general info", "tier": 1},
    ]
    return InMemoryUnifiedStore(data)

def test_hybrid_search_deduplication(store):
    # Setup hybrid searcher with 0.5 lambda
    searcher = HybridSearcher(store, lambda_ratio=0.5)
    
    # Query for "doc" with tier 2. 
    # vector_search will return [1, 2]
    # graph_search will return [1, 2, 4]
    results = searcher.search("doc", user_tier=2)
    
    # deduplicated should be [1, 2, 4] length 3
    assert len(results) == 3
    ids = {r["id"] for r in results}
    assert ids == {"1", "2", "4"}

def test_hybrid_search_lambda_1(store):
    searcher = HybridSearcher(store, lambda_ratio=1.0)
    results = searcher.search("doc", user_tier=2)
    # Should only contain vector results
    ids = {r["id"] for r in results}
    assert ids == {"1", "2", "4"}

def test_hybrid_search_lambda_0(store):
    searcher = HybridSearcher(store, lambda_ratio=0.0)
    results = searcher.search("doc", user_tier=2)
    # Should only contain graph results
    ids = {r["id"] for r in results}
    assert ids == {"1", "2", "4"}


def test_hybrid_search_includes_exact_symbol_lexical_hits_before_vector_noise(tmp_path: Path):
    store = SQLiteUnifiedStore(tmp_path / "index.db", HashingEmbeddingProvider(dimensions=16))
    store.upsert_artifacts(
        [
            ArtifactRecord(
                artifact_id="repo-a:RepositoryIndexer",
                repository="repo-a",
                file_path="src/ingestion/indexer.py",
                language="python",
                text="class RepositoryIndexer",
                tier=1,
                fidelity="L-1",
                symbol_name="RepositoryIndexer",
                kind="class",
                metadata={"qualified_name": "RepositoryIndexer"},
            ),
            ArtifactRecord(
                artifact_id="repo-a:unrelated-test",
                repository="repo-a",
                file_path="tests/test_window.py",
                language="python",
                text="def test_window_visible(): pass",
                tier=1,
                fidelity="L-1",
                symbol_name="test_window_visible",
                kind="function",
            ),
            ArtifactRecord(
                artifact_id="repo-a:RepositoryIndexer._is_json_document",
                repository="repo-a",
                file_path="src/ingestion/indexer.py",
                language="python",
                text="def _is_json_document(cls, path, content)",
                tier=1,
                fidelity="L-1",
                symbol_name="_is_json_document",
                kind="method",
                metadata={"qualified_name": "RepositoryIndexer._is_json_document"},
            ),
        ]
    )

    results = HybridSearcher(store).search("What does RepositoryIndexer do?", user_tier=1, repo_scope=["repo-a"])

    assert results[0]["id"] == "repo-a:RepositoryIndexer"


def test_hybrid_search_adds_policy_text_matches_beyond_vector_window(tmp_path: Path):
    class PolicyStore(InMemoryUnifiedStore):
        def filename_search(self, query, user_tier, repo_scope=None):
            return []

        def vector_search(self, query, user_tier, repo_scope=None, top_k=20):
            return [
                {
                    "id": "repo-a:schema",
                    "file_path": "schemas/ocp.schema.json",
                    "text": "schemas examples format data",
                    "kind": "json-document",
                    "symbol_name": "schemas/ocp.schema.json",
                    "score": 1.0,
                }
            ]

        def graph_search(self, query, user_tier, repo_scope=None, depth=3, breadth=50):
            return []

        def lexical_search(self, query, user_tier, repo_scope=None, top_k=50):
            return [
                {
                    "id": "repo-a:licenses",
                    "file_path": "LICENSES.md",
                    "text": "schemas/ and examples/ are licensed under MIT.",
                    "kind": "text/markdown",
                    "symbol_name": "chunk-1",
                    "score": 10.0,
                },
                {
                    "id": "repo-a:contributing",
                    "file_path": "CONTRIBUTING.md",
                    "text": "Contributions to MIT-licensed areas are licensed under MIT.",
                    "kind": "text/markdown",
                    "symbol_name": "chunk-2",
                    "score": 9.0,
                },
            ]

    candidates = HybridSearcher(PolicyStore([]), vector_top_k=1).search(
        "Which license applies to schemas and examples, and what contribution rule covers MIT-licensed areas?",
        user_tier=3,
        repo_scope=["repo-a"],
    )
    ranked = LexicalReranker().rerank(
        "Which license applies to schemas and examples, and what contribution rule covers MIT-licensed areas?",
        candidates,
        top_m=5,
    )

    file_paths = {item["file_path"] for item in ranked}
    assert "LICENSES.md" in file_paths
    assert "CONTRIBUTING.md" in file_paths
