import pytest
from retrieval.database import InMemoryUnifiedStore
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
