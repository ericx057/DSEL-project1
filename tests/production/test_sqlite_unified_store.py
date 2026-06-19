from pathlib import Path
import sqlite3

from src.retrieval.database import (
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


def test_sqlite_store_matches_existing_hash_embedding_dimension(tmp_path: Path):
    db_path = tmp_path / "cis.db"
    writer = SQLiteUnifiedStore(db_path, HashingEmbeddingProvider(dimensions=16))
    writer.upsert_artifacts(
        [
            ArtifactRecord(
                artifact_id="repo-a:indexer",
                repository="repo-a",
                file_path="indexer.py",
                language="python",
                text="RepositoryIndexer indexes repositories and upserts artifacts",
                tier=3,
                fidelity="L-1",
                symbol_name="RepositoryIndexer",
            )
        ]
    )
    writer.close()

    reader = SQLiteUnifiedStore(db_path, HashingEmbeddingProvider(dimensions=128))

    results = reader.vector_search("RepositoryIndexer indexes repositories", user_tier=3, repo_scope=["repo-a"])

    assert [item["id"] for item in results] == ["repo-a:indexer"]


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


def test_sqlite_store_delete_repository_chunks_large_edge_deletes(tmp_path: Path):
    store = SQLiteUnifiedStore(tmp_path / "cis.db", HashingEmbeddingProvider(dimensions=8))
    if hasattr(store._connection, "setlimit"):
        store._connection.setlimit(sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER, 50)
    artifacts = [
        ArtifactRecord(
            artifact_id=f"repo-a:item-{index}",
            repository="repo-a",
            file_path=f"item_{index}.py",
            language="python",
            text=f"def item_{index}(): pass",
            tier=1,
            fidelity="L-1",
            symbol_name=f"item_{index}",
        )
        for index in range(80)
    ]
    store.upsert_artifacts(artifacts)
    store.upsert_edges(
        [
            GraphEdgeRecord(f"repo-a:item-{index}", f"repo-a:item-{index + 1}", "calls")
            for index in range(79)
        ]
    )

    store.delete_repository("repo-a")

    assert store.vector_search("item", user_tier=3, repo_scope=["repo-a"], top_k=10) == []
    assert store.list_edges(user_tier=3, repo_scope=["repo-a"]) == []


def test_sqlite_store_replaces_repository_atomically_and_records_metadata(tmp_path: Path):
    store = SQLiteUnifiedStore(tmp_path / "cis.db", HashingEmbeddingProvider(dimensions=8))
    store.upsert_artifacts(
        [
            ArtifactRecord(
                artifact_id="repo-a:old",
                repository="repo-a",
                file_path="old.py",
                language="python",
                text="def old_symbol(): pass",
                tier=1,
                fidelity="L-1",
                symbol_name="old_symbol",
            ),
            ArtifactRecord(
                artifact_id="repo-b:kept",
                repository="repo-b",
                file_path="kept.py",
                language="python",
                text="def kept_symbol(): pass",
                tier=1,
                fidelity="L-1",
                symbol_name="kept_symbol",
            ),
        ]
    )

    store.replace_repository(
        "repo-a",
        [
            ArtifactRecord(
                artifact_id="repo-a:new",
                repository="repo-a",
                file_path="new.py",
                language="python",
                text="def new_symbol(): pass",
                tier=1,
                fidelity="L-1",
                symbol_name="new_symbol",
            )
        ],
        [],
        source_path=str(tmp_path / "repo-a"),
    )

    repo_a_ids = [item["id"] for item in store.list_artifacts(user_tier=3, repo_scope=["repo-a"])]
    repo_b_ids = [item["id"] for item in store.list_artifacts(user_tier=3, repo_scope=["repo-b"])]
    assert repo_a_ids == ["repo-a:new"]
    assert "repo-a:old" not in repo_a_ids
    assert [item["id"] for item in store.vector_search("new_symbol", user_tier=3, repo_scope=["repo-a"], top_k=10)] == [
        "repo-a:new"
    ]
    assert repo_b_ids == ["repo-b:kept"]
    stats = store.index_stats(["repo-a"])
    assert stats["repositories"] == ["repo-a"]
    assert stats["repository_metadata"][0]["source_path"] == str(tmp_path / "repo-a")


def test_lexical_search_merges_symbol_cache_and_exact_text_matches(tmp_path: Path):
    store = SQLiteUnifiedStore(tmp_path / "cis.db", HashingEmbeddingProvider(dimensions=16))
    store.upsert_artifacts(
        [
            ArtifactRecord(
                artifact_id="repo-a:noisy-symbol",
                repository="repo-a",
                file_path="docs/checkout_flow.md",
                language="markdown",
                text="General checkout notes.",
                tier=1,
                fidelity="L-2",
                symbol_name="refund_webhook_index",
                kind="section",
            ),
            ArtifactRecord(
                artifact_id="repo-a:exact-body",
                repository="repo-a",
                file_path="docs/payment.md",
                language="markdown",
                text="The refund webhook validates chargeback evidence and retries payment settlement.",
                tier=1,
                fidelity="L-4",
                symbol_name="docs/payment.md",
                kind="chunk",
            ),
        ]
    )

    results = store.lexical_search(
        "refund webhook chargeback evidence settlement",
        user_tier=1,
        repo_scope=["repo-a"],
        top_k=5,
    )

    result_ids = [item["id"] for item in results]
    assert "repo-a:exact-body" in result_ids
    assert result_ids.index("repo-a:exact-body") < result_ids.index("repo-a:noisy-symbol")
