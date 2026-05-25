from pathlib import Path

from diagram.service import DiagramService
from retrieval.database import ArtifactRecord, GraphEdgeRecord, HashingEmbeddingProvider, SQLiteUnifiedStore


def test_diagram_service_renders_svg_from_allowed_graph(tmp_path: Path):
    store = SQLiteUnifiedStore(tmp_path / "index.db", HashingEmbeddingProvider(dimensions=8))
    store.upsert_artifacts(
        [
            ArtifactRecord("repo-a:a", "repo-a", "a.py", "python", "def a(): b()", 1, "L-1", "a"),
            ArtifactRecord("repo-a:b", "repo-a", "b.py", "python", "def b(): pass", 1, "L-1", "b"),
            ArtifactRecord("repo-a:secret", "repo-a", "s.py", "python", "def secret(): pass", 3, "L-1", "secret"),
        ]
    )
    store.upsert_edges(
        [
            GraphEdgeRecord("repo-a:a", "repo-a:b", "calls"),
            GraphEdgeRecord("repo-a:b", "repo-a:secret", "calls"),
        ]
    )

    svg = DiagramService(store).render_call_graph_svg("a", user_tier=1, repo_scope=["repo-a"])

    assert svg.startswith("<svg")
    assert "a" in svg
    assert "b" in svg
    assert "secret" not in svg

