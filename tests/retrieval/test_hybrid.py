import pytest
from pathlib import Path

from retrieval.database import ArtifactRecord, HashingEmbeddingProvider, InMemoryUnifiedStore, SQLiteUnifiedStore
from retrieval.hybrid import HybridSearcher

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
