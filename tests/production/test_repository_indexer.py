from pathlib import Path

from ingestion.indexer import RepositoryIndexer
from retrieval.database import ArtifactRecord, HashingEmbeddingProvider, SQLiteUnifiedStore
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


def test_repository_indexer_limits_index_to_included_paths(tmp_path: Path):
    repo = tmp_path / "repo-a"
    repo.mkdir()
    src = repo / "src"
    opencad = repo / "external" / "OpenCAD" / "examples"
    noise = repo / "external" / "generalization"
    src.mkdir()
    opencad.mkdir(parents=True)
    noise.mkdir(parents=True)
    (src / "assistant.py").write_text("def chat_assistant():\n    return 'OpenCAD help'", encoding="utf-8")
    (opencad / "bracket_demo.ocp").write_text(
        '{"metadata":{"name":"Bracket"},"geometry":{"features":[]}}',
        encoding="utf-8",
    )
    (noise / "large_fixture.py").write_text("def unrelated_flask_fixture():\n    return True", encoding="utf-8")

    store = SQLiteUnifiedStore(tmp_path / "index.db", HashingEmbeddingProvider(dimensions=16))
    indexer = RepositoryIndexer(store, include_paths=("src", "external/OpenCAD"))

    report = indexer.index_repository("repo-a", repo)
    opencad_results = store.vector_search("bracket OpenCAD assistant", user_tier=3, repo_scope=["repo-a"], top_k=20)
    noise_results = store.vector_search("unrelated_flask_fixture", user_tier=3, repo_scope=["repo-a"], top_k=20)

    indexed_paths = {item["file_path"] for item in opencad_results}
    assert report.files_indexed == 2
    assert "src/assistant.py" in indexed_paths
    assert "external/OpenCAD/examples/bracket_demo.ocp" in indexed_paths
    assert all(item["file_path"] != "external/generalization/large_fixture.py" for item in noise_results)


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


def test_repository_indexer_keeps_previous_index_when_reindex_fails(tmp_path: Path):
    class ExplodingParser:
        def parse(self, file_path, language=None):
            raise RuntimeError("parser exploded")

    repo = tmp_path / "repo-a"
    repo.mkdir()
    (repo / "app.py").write_text("def new_symbol():\n    return True", encoding="utf-8")

    store = SQLiteUnifiedStore(tmp_path / "index.db", HashingEmbeddingProvider(dimensions=16))
    store.upsert_artifacts(
        [
            ArtifactRecord(
                artifact_id="repo-a:old.py:old_symbol:T1",
                repository="repo-a",
                file_path="old.py",
                language="python",
                text="def old_symbol(): pass",
                tier=1,
                fidelity="L-1",
                symbol_name="old_symbol",
            )
        ]
    )
    indexer = RepositoryIndexer(store, parser=ExplodingParser())

    try:
        indexer.index_repository("repo-a", repo)
    except RuntimeError as exc:
        assert str(exc) == "parser exploded"
    else:
        raise AssertionError("Expected parser failure")

    old_results = store.vector_search("old_symbol", user_tier=1, repo_scope=["repo-a"], top_k=10)
    stored_ids = [item["id"] for item in store.list_artifacts(user_tier=1, repo_scope=["repo-a"])]
    assert [item["id"] for item in old_results] == ["repo-a:old.py:old_symbol:T1"]
    assert stored_ids == ["repo-a:old.py:old_symbol:T1"]


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


def test_repository_indexer_builds_json_document_schema_and_reference_edges(tmp_path: Path):
    repo = tmp_path / "repo-a"
    repo.mkdir()
    schemas = repo / "schemas"
    examples = repo / "examples"
    schemas.mkdir()
    examples.mkdir()
    (schemas / "part.schema.json").write_text(
        '{"title":"Generic Part Schema","properties":{"metadata":{"type":"object"}}}',
        encoding="utf-8",
    )
    (examples / "widget.part").write_text(
        '{"metadata":{"name":"Widget","material":"Steel"},"history":[]}',
        encoding="utf-8",
    )
    (examples / "assembly.json").write_text(
        '{"instances":[{"id":"widget-1","source":"./widget.part"}]}',
        encoding="utf-8",
    )

    store = SQLiteUnifiedStore(tmp_path / "index.db", HashingEmbeddingProvider(dimensions=16))
    indexer = RepositoryIndexer(store)

    report = indexer.index_repository("repo-a", repo)
    results = store.vector_search(
        "examples/widget.part metadata.material Steel",
        user_tier=3,
        repo_scope=["repo-a"],
        top_k=10,
    )
    schema_edges = store.list_edges(user_tier=3, repo_scope=["repo-a"], relationship="validated-by")
    reference_edges = store.list_edges(user_tier=3, repo_scope=["repo-a"], relationship="references")
    graph_results = store.graph_search(
        "widget-1 metadata.material",
        user_tier=3,
        repo_scope=["repo-a"],
        depth=2,
        breadth=20,
    )

    assert report.files_indexed == 3
    assert any(
        item["file_path"] == "examples/widget.part"
        and item["kind"] == "json-document"
        and item["language"] == "json"
        and "metadata.material = Steel" in item["text"]
        for item in results
    )
    assert any(
        edge["source_id"] == "repo-a:examples/widget.part:json-document:T3"
        and edge["target_id"] == "repo-a:schemas/part.schema.json:json-document:T3"
        for edge in schema_edges
    )
    assert any(
        edge["source_id"] == "repo-a:examples/assembly.json:json-document:T3"
        and edge["target_id"] == "repo-a:examples/widget.part:json-document:T3"
        for edge in reference_edges
    )
    assert any(item["file_path"] == "examples/widget.part" for item in graph_results)


def test_repository_indexer_adds_generic_markdown_table_artifacts(tmp_path: Path):
    repo = tmp_path / "repo-a"
    repo.mkdir()
    (repo / "README.md").write_text(
        "\n".join(
            [
                "| Component | Owner | Purpose |",
                "| --------- | ----- | ------- |",
                "| API | Platform | Serves repository metadata. |",
            ]
        ),
        encoding="utf-8",
    )

    store = SQLiteUnifiedStore(tmp_path / "index.db", HashingEmbeddingProvider(dimensions=16))
    RepositoryIndexer(store).index_repository("repo-a", repo)

    results = store.vector_search(
        "README table Platform repository metadata",
        user_tier=3,
        repo_scope=["repo-a"],
        top_k=10,
    )

    assert any(
        item["file_path"] == "README.md"
        and item["kind"] == "markdown-table"
        and "table[1].row[1].Owner = Platform" in item["text"]
        and "table[1].row[1].Purpose = Serves repository metadata." in item["text"]
        for item in results
    )


def test_repository_indexer_indexes_cpp_methods_as_symbols(tmp_path: Path):
    repo = tmp_path / "repo-a"
    repo.mkdir()
    source = repo / "TopoShapePyImp.cpp"
    source.write_text(
        "\n".join(
            [
                "Py::List TopoShapePy::getVertexes() const",
                "{",
                "    return getElements(*getTopoShapePtr(), TopAbs_VERTEX);",
                "}",
                "",
                "Py::List TopoShapePy::getEdges() const",
                "{",
                "    return getElements(*getTopoShapePtr(), TopAbs_EDGE);",
                "}",
                "",
                "Py::List TopoShapePy::getWires() const",
                "{",
                "    return getElements(*getTopoShapePtr(), TopAbs_WIRE);",
                "}",
            ]
        ),
        encoding="utf-8",
    )

    store = SQLiteUnifiedStore(tmp_path / "index.db", HashingEmbeddingProvider(dimensions=16))

    RepositoryIndexer(store).index_repository("repo-a", repo)

    artifacts = store.list_artifacts(user_tier=3, repo_scope=["repo-a"])
    method_symbols = {
        item["symbol_name"]
        for item in artifacts
        if item["kind"] in {"method", "method-implementation"}
    }
    assert {"getEdges", "getVertexes", "getWires"} <= method_symbols


def test_repository_indexer_does_not_resolve_external_dotted_python_call_to_local_leaf(tmp_path: Path):
    repo = tmp_path / "repo-a"
    repo.mkdir()
    (repo / "app.py").write_text(
        "\n".join(
            [
                "import json",
                "",
                "def dumps(value):",
                "    return 'local'",
                "",
                "def encode(value):",
                "    return json.dumps(value)",
            ]
        ),
        encoding="utf-8",
    )
    store = SQLiteUnifiedStore(tmp_path / "index.db", HashingEmbeddingProvider(dimensions=16))

    RepositoryIndexer(store).index_repository("repo-a", repo)

    edges = store.list_edges(user_tier=3, repo_scope=["repo-a"], relationship="calls")
    assert not any(edge["source_id"].endswith(":encode:T1") and edge["target_id"].endswith(":dumps:T1") for edge in edges)


def test_repository_indexer_detects_cpp_header_from_content(tmp_path: Path):
    repo = tmp_path / "repo-a"
    repo.mkdir()
    (repo / "Shape.h").write_text(
        "\n".join(
            [
                "namespace geom {",
                "class Shape {",
                "public:",
                "    void draw() const;",
                "};",
                "}",
            ]
        ),
        encoding="utf-8",
    )
    store = SQLiteUnifiedStore(tmp_path / "index.db", HashingEmbeddingProvider(dimensions=16))

    RepositoryIndexer(store).index_repository("repo-a", repo)

    artifacts = store.list_artifacts(user_tier=3, repo_scope=["repo-a"])
    class_artifact = next(item for item in artifacts if item["symbol_name"] == "Shape" and item["kind"] == "class")
    assert class_artifact["language"] == "cpp"


def test_repository_indexer_indexes_multilanguage_classes_and_functions(tmp_path: Path):
    repo = tmp_path / "repo-a"
    repo.mkdir()
    (repo / "checkout.ts").write_text(
        "\n".join(
            [
                "export class CheckoutService {",
                "  authorize(amount: number): boolean {",
                "    return validate(amount);",
                "  }",
                "}",
                "export function buildReceipt(id: string): string {",
                "  return formatReceipt(id);",
                "}",
            ]
        ),
        encoding="utf-8",
    )
    (repo / "checkout.go").write_text(
        "\n".join(
            [
                "package checkout",
                "type Service struct {}",
                "func (s *Service) Authorize(amount int) bool {",
                "    return validate(amount)",
                "}",
            ]
        ),
        encoding="utf-8",
    )
    store = SQLiteUnifiedStore(tmp_path / "index.db", HashingEmbeddingProvider(dimensions=16))

    RepositoryIndexer(store).index_repository("repo-a", repo)

    artifacts = store.list_artifacts(user_tier=3, repo_scope=["repo-a"])
    symbol_pairs = {(item["language"], item["kind"], item["metadata"].get("qualified_name")) for item in artifacts}
    assert ("typescript", "class", "CheckoutService") in symbol_pairs
    assert ("typescript", "method", "CheckoutService.authorize") in symbol_pairs
    assert ("typescript", "function", "buildReceipt") in symbol_pairs
    assert ("go", "class", "Service") in symbol_pairs
    assert ("go", "method", "Service.Authorize") in symbol_pairs
