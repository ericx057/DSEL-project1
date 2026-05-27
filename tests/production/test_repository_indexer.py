from pathlib import Path

from ingestion.indexer import RepositoryIndexer
from retrieval.database import HashingEmbeddingProvider, SQLiteUnifiedStore
from src.UMMDB.parser.cascade import ParsedChunk


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


def test_repository_indexer_uses_injected_ummdb_parser(tmp_path: Path):
    class StaticParser:
        def parse(self, file_path, language=None):
            return [
                ParsedChunk(
                    "def provided()",
                    "L-1",
                    {"qualified_name": "provided"},
                    symbol_name="provided",
                    line_start=1,
                    line_end=1,
                    kind="function",
                    tier=1,
                )
            ]

    repo = tmp_path / "repo-a"
    repo.mkdir()
    (repo / "app.py").write_text("this is not valid python", encoding="utf-8")

    store = SQLiteUnifiedStore(tmp_path / "index.db", HashingEmbeddingProvider(dimensions=16))
    indexer = RepositoryIndexer(store, parser=StaticParser())

    report = indexer.index_repository("repo-a", repo)
    results = store.vector_search("provided", user_tier=1, repo_scope=["repo-a"], top_k=10)

    assert report.artifacts_indexed == 1
    assert any(item["symbol_name"] == "provided" for item in results)


def test_repository_indexer_resolves_method_calls_without_short_name_collisions(tmp_path: Path):
    repo = tmp_path / "repo-a"
    repo.mkdir()
    source = repo / "app.py"
    source.write_text(
        "\n".join(
            [
                "class A:",
                "    def run(self):",
                "        return self.helper()",
                "    def helper(self):",
                "        return 'a'",
                "",
                "class B:",
                "    def helper(self):",
                "        return 'b'",
                "",
                "def helper():",
                "    return 'global'",
            ]
        ),
        encoding="utf-8",
    )

    store = SQLiteUnifiedStore(tmp_path / "index.db", HashingEmbeddingProvider(dimensions=16))
    indexer = RepositoryIndexer(store)

    indexer.index_repository("repo-a", repo)
    edges = store.list_edges(user_tier=3, repo_scope=["repo-a"], relationship="calls")

    run_id = "repo-a:app.py:A.run:T1"
    target_ids = {edge["target_id"] for edge in edges if edge["source_id"] == run_id}
    assert target_ids == {"repo-a:app.py:A.helper:T1"}
