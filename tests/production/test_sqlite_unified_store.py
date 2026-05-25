from pathlib import Path

from retrieval.database import (
    ArtifactRecord,
    GraphEdgeRecord,
    HashingEmbeddingProvider,
    SQLiteUnifiedStore,
)


def test_sqlite_store_filters_tier_and_scope_in_query(tmp_path: Path):
    store = SQLiteUnifiedStore(tmp_path / "cis.db", HashingEmbeddingProvider(dimensions=16))
    store.upsert_artifacts(
        [
            ArtifactRecord(
                artifact_id="repo-a:api",
                repository="repo-a",
                file_path="api.py",
                language="python",
                text="def public_api()",
                tier=1,
                fidelity="L-1",
                symbol_name="public_api",
            ),
            ArtifactRecord(
                artifact_id="repo-a:impl",
                repository="repo-a",
                file_path="api.py",
                language="python",
                text="password = compute_secret()",
                tier=3,
                fidelity="L-1",
                symbol_name="compute_secret",
            ),
            ArtifactRecord(
                artifact_id="repo-b:api",
                repository="repo-b",
                file_path="other.py",
                language="python",
                text="def other_repo_api()",
                tier=1,
                fidelity="L-1",
                symbol_name="other_repo_api",
            ),
        ]
    )

    results = store.vector_search("secret public", user_tier=1, repo_scope=["repo-a"], top_k=10)

    assert [item["id"] for item in results] == ["repo-a:api"]
    assert all(item["tier"] <= 1 for item in results)
    assert all(item["repository"] == "repo-a" for item in results)


def test_sqlite_store_graph_search_walks_allowed_edges_only(tmp_path: Path):
    store = SQLiteUnifiedStore(tmp_path / "cis.db", HashingEmbeddingProvider(dimensions=16))
    store.upsert_artifacts(
        [
            ArtifactRecord(
                artifact_id="repo-a:handler",
                repository="repo-a",
                file_path="handler.py",
                language="python",
                text="def handler(): return service()",
                tier=1,
                fidelity="L-1",
                symbol_name="handler",
            ),
            ArtifactRecord(
                artifact_id="repo-a:service-summary",
                repository="repo-a",
                file_path="service.py",
                language="python",
                text="service validates input and calls storage",
                tier=2,
                fidelity="L-1",
                symbol_name="service",
            ),
            ArtifactRecord(
                artifact_id="repo-a:storage-impl",
                repository="repo-a",
                file_path="storage.py",
                language="python",
                text="raw SQL implementation detail",
                tier=3,
                fidelity="L-1",
                symbol_name="storage",
            ),
        ]
    )
    store.upsert_edges(
        [
            GraphEdgeRecord("repo-a:handler", "repo-a:service-summary", "calls"),
            GraphEdgeRecord("repo-a:service-summary", "repo-a:storage-impl", "calls"),
        ]
    )

    results = store.graph_search("handler", user_tier=2, repo_scope=["repo-a"], depth=3, breadth=10)

    assert {item["id"] for item in results} == {"repo-a:handler", "repo-a:service-summary"}
    assert all(item["tier"] <= 2 for item in results)

