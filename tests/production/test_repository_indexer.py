from pathlib import Path

from ingestion.indexer import RepositoryIndexer
from retrieval.database import HashingEmbeddingProvider, SQLiteUnifiedStore


def test_repository_indexer_builds_tiered_artifacts_and_graph(tmp_path: Path):
    repo = tmp_path / "repo-a"
    repo.mkdir()
    source = repo / "app.py"
    source.write_text(
        "\n".join(
            [
                "import json",
                "",
                "class Service:",
                "    def run(self, payload):",
                "        return helper(payload)",
                "",
                "def helper(value):",
                "    return json.dumps(value)",
            ]
        ),
        encoding="utf-8",
    )

    store = SQLiteUnifiedStore(tmp_path / "index.db", HashingEmbeddingProvider(dimensions=16))
    indexer = RepositoryIndexer(store)

    report = indexer.index_repository("repo-a", repo)
    t1_results = store.vector_search("Service run helper", user_tier=1, repo_scope=["repo-a"], top_k=20)
    t3_results = store.vector_search("json.dumps", user_tier=3, repo_scope=["repo-a"], top_k=20)
    graph_results = store.graph_search("run", user_tier=3, repo_scope=["repo-a"], depth=2, breadth=20)

    assert report.files_indexed == 1
    assert report.files_skipped == 0
    assert any(item["tier"] == 1 and "def helper" in item["text"] for item in t1_results)
    assert any(item["tier"] == 3 and "json.dumps" in item["text"] for item in t3_results)
    assert any(item["symbol_name"] == "helper" for item in graph_results)


def test_repository_indexer_skips_binary_and_excluded_paths(tmp_path: Path):
    repo = tmp_path / "repo-a"
    repo.mkdir()
    excluded_dir = repo / "node_modules"
    excluded_dir.mkdir()
    (excluded_dir / "pkg.js").write_text("export const hidden = true", encoding="utf-8")
    (repo / "image.bin").write_bytes(b"\x00\x01\x02" * 20)

    store = SQLiteUnifiedStore(tmp_path / "index.db", HashingEmbeddingProvider(dimensions=16))
    indexer = RepositoryIndexer(store)

    report = indexer.index_repository("repo-a", repo)
    results = store.vector_search("hidden", user_tier=3, repo_scope=["repo-a"], top_k=10)

    assert report.files_indexed == 0
    assert report.files_skipped == 2
    assert results == []


def test_repository_indexer_skips_sensitive_files_and_secret_patterns(tmp_path: Path):
    repo = tmp_path / "repo-a"
    repo.mkdir()
    (repo / ".env").write_text("API_KEY=should_not_be_indexed", encoding="utf-8")
    (repo / "config.py").write_text("PASSWORD='super-secret-value-12345'", encoding="utf-8")
    (repo / "safe.py").write_text("def visible():\n    return 'ok'", encoding="utf-8")

    store = SQLiteUnifiedStore(tmp_path / "index.db", HashingEmbeddingProvider(dimensions=16))
    indexer = RepositoryIndexer(store)

    report = indexer.index_repository("repo-a", repo)
    secret_results = store.vector_search("super secret API_KEY", user_tier=3, repo_scope=["repo-a"], top_k=10)
    safe_results = store.vector_search("visible", user_tier=3, repo_scope=["repo-a"], top_k=10)

    assert report.files_indexed == 1
    assert report.files_skipped == 2
    assert all("super-secret-value" not in item["text"] for item in secret_results)
    assert all("API_KEY" not in item["text"] for item in secret_results)
    assert any(item["symbol_name"] == "visible" for item in safe_results)
