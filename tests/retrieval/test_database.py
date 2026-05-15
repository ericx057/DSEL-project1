import pytest
from retrieval.database import InMemoryUnifiedStore

@pytest.fixture
def store():
    data = [
        {"id": "1", "text": "public doc", "tier": 0},
        {"id": "2", "text": "secret doc with password", "tier": 2},
        {"id": "3", "text": "top secret public", "tier": 3},
        {"id": "4", "text": "general info", "tier": 1},
    ]
    return InMemoryUnifiedStore(data)

def test_vector_search_rbac(store):
    # Tier 0 user should only see tier 0 docs
    results = store.vector_search("doc", user_tier=0)
    assert len(results) == 1
    assert results[0]["id"] == "1"

    # Tier 2 user should see tier 0, 1, 2 docs
    results = store.vector_search("doc", user_tier=2)
    assert len(results) == 3
    tiers = [r["tier"] for r in results]
    assert all(t <= 2 for t in tiers)

def test_graph_search_rbac(store):
    # Tier 1 user should see tier 0, 1 docs
    results = store.graph_search("info", user_tier=1)
    assert len(results) == 2
    tiers = [r["tier"] for r in results]
    assert all(t <= 1 for t in tiers)
