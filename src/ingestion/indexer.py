from __future__ import annotations

import mimetypes
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from src.retrieval.database import ArtifactRecord, GraphEdgeRecord, SQLiteUnifiedStore
from src.UMMDB.parser.cascade import CascadingParser, ParsedChunk
from src.UMMDB.parser.filters import FileHeuristics


@dataclass(frozen=True)
class IndexReport:
    repository: str
    files_indexed: int
    files_skipped: int
    artifacts_indexed: int
    edges_indexed: int


class RepositoryIndexer:
    DEFAULT_EXCLUDES = (
        ".git",
        ".venv",
        "__pycache__",
        "node_modules",
        "vendor",
        "build",
        "dist",
        ".idea",
        ".cis",
    )
    SENSITIVE_FILENAMES = {
        ".env",
        ".env.local",
        ".env.production",
        "credentials",
        "credentials.json",
        "id_dsa",
        "id_ed25519",
        "id_rsa",
        "known_hosts",
        "kubeconfig",
    }
    SENSITIVE_SUFFIXES = (".pem", ".key", ".p12", ".pfx", ".crt", ".cer")
    SECRET_PATTERNS = (
        re.compile(r"-----BEGIN (?:RSA |DSA |EC |OPENSSH |)PRIVATE KEY-----"),
        re.compile(r"(?i)\b(?:api[_-]?key|secret[_-]?key|access[_-]?token|private[_-]?key|password)\s*[:=]\s*['\"]?[^'\"\s]{12,}"),
    )

    def __init__(
        self,
        store: SQLiteUnifiedStore,
        heuristics: Optional[FileHeuristics] = None,
        exclusions: Sequence[str] = DEFAULT_EXCLUDES,
        parser: Optional[CascadingParser] = None,
    ):
        self.store = store
        self.exclusions = set(exclusions)
        self.heuristics = heuristics or FileHeuristics()
        self.parser = parser or CascadingParser()

    def index_repository(self, repository: str, repo_path: str | Path) -> IndexReport:
        root = Path(repo_path).resolve()
        if not root.exists() or not root.is_dir():
            raise ValueError(f"Repository path does not exist: {root}")

        self.store.delete_repository(repository)
        artifacts: List[ArtifactRecord] = []
        edges: List[GraphEdgeRecord] = []
        files_indexed = 0
        files_skipped = 0

        for file_path in self._iter_files(root):
            if self._is_excluded(root, file_path) or self._is_sensitive_path(root, file_path):
                files_skipped += 1
                continue
            if not self.heuristics.is_human_readable(str(file_path)):
                files_skipped += 1
                continue
            file_artifacts, file_edges = self._index_file(repository, root, file_path)
            if not file_artifacts:
                files_skipped += 1
                continue
            artifacts.extend(file_artifacts)
            edges.extend(file_edges)
            files_indexed += 1

        self.store.upsert_artifacts(artifacts)
        self.store.upsert_edges(edges)
        return IndexReport(
            repository=repository,
            files_indexed=files_indexed,
            files_skipped=files_skipped,
            artifacts_indexed=len(artifacts),
            edges_indexed=len(edges),
        )

    def _iter_files(self, root: Path) -> Iterable[Path]:
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            yield path

    def _is_excluded(self, root: Path, path: Path) -> bool:
        return any(part in self.exclusions for part in path.relative_to(root).parts)

    def _is_sensitive_path(self, root: Path, path: Path) -> bool:
        relative = path.relative_to(root)
        names = {part.lower() for part in relative.parts}
        filename = path.name.lower()
        return (
            bool(names & self.SENSITIVE_FILENAMES)
            or filename.startswith(".env.")
            or filename.endswith(self.SENSITIVE_SUFFIXES)
            or "secret" in names
            or "secrets" in names
        )

    def _index_file(
        self,
        repository: str,
        root: Path,
        file_path: Path,
    ) -> Tuple[List[ArtifactRecord], List[GraphEdgeRecord]]:
        relative_path = file_path.relative_to(root).as_posix()
        language = self._detect_language(file_path)
        content = file_path.read_text(encoding="utf-8")
        if self._is_generated(content):
            return [
                ArtifactRecord(
                    artifact_id=self._artifact_id(repository, relative_path, "module", 1),
                    repository=repository,
                    file_path=relative_path,
                    language=language,
                    text=f"module {relative_path}",
                    tier=1,
                    fidelity="L-4",
                    symbol_name=relative_path,
                    line_start=1,
                    line_end=max(1, content.count("\n") + 1),
                    kind="module",
                    metadata={"generated": True},
                )
            ], []

        if self._contains_secret_pattern(content):
            return [], []

        chunks = self.parser.parse(str(file_path), language)
        if not chunks:
            return self._index_text_file(repository, relative_path, language, content)
        return self._index_chunks(repository, relative_path, language, chunks)

    def _index_chunks(
        self,
        repository: str,
        relative_path: str,
        language: str,
        chunks: Sequence[ParsedChunk],
    ) -> Tuple[List[ArtifactRecord], List[GraphEdgeRecord]]:
        artifacts: List[ArtifactRecord] = []
        chunk_ids: Dict[int, str] = {}
        qualified_ids: Dict[str, str] = {}
        short_name_ids: Dict[str, set[str]] = {}

        for index, chunk in enumerate(chunks, start=1):
            symbol = self._chunk_symbol(relative_path, chunk, index)
            artifact_id = self._artifact_id(repository, relative_path, symbol, chunk.tier)
            chunk_ids[id(chunk)] = artifact_id
            artifacts.append(
                ArtifactRecord(
                    artifact_id=artifact_id,
                    repository=repository,
                    file_path=relative_path,
                    language=language,
                    text=chunk.content,
                    tier=chunk.tier,
                    fidelity=chunk.fidelity,
                    symbol_name=chunk.symbol_name or symbol,
                    line_start=chunk.line_start,
                    line_end=chunk.line_end,
                    kind=chunk.kind,
                    metadata=chunk.metadata,
                )
            )
            if chunk.tier == 1 and chunk.kind != "module":
                qualified_name = self._chunk_qualified_name(chunk)
                if qualified_name:
                    qualified_ids[qualified_name] = artifact_id
                if chunk.symbol_name:
                    short_name_ids.setdefault(chunk.symbol_name, set()).add(artifact_id)

        edges = self._build_edges(chunks, chunk_ids, qualified_ids, short_name_ids)
        return artifacts, edges

    def _build_edges(
        self,
        chunks: Sequence[ParsedChunk],
        chunk_ids: Dict[int, str],
        qualified_ids: Dict[str, str],
        short_name_ids: Dict[str, set[str]],
    ) -> List[GraphEdgeRecord]:
        seen: set[Tuple[str, str, str]] = set()
        edges: List[GraphEdgeRecord] = []
        for chunk in chunks:
            if chunk.tier != 1 or chunk.kind == "module":
                continue
            source_id = chunk_ids[id(chunk)]
            source_qualified_name = self._chunk_qualified_name(chunk)
            for call in chunk.calls:
                target_id = self._resolve_symbol_reference(
                    call,
                    source_qualified_name,
                    qualified_ids,
                    short_name_ids,
                )
                if target_id:
                    self._append_edge(edges, seen, source_id, target_id, "calls")
            for parent in chunk.inherits:
                target_id = self._resolve_symbol_reference(
                    parent,
                    source_qualified_name,
                    qualified_ids,
                    short_name_ids,
                )
                if target_id:
                    self._append_edge(edges, seen, source_id, target_id, "inherits")
        return edges

    @staticmethod
    def _append_edge(
        edges: List[GraphEdgeRecord],
        seen: set[Tuple[str, str, str]],
        source_id: str,
        target_id: str,
        relationship: str,
    ) -> None:
        edge_key = (source_id, target_id, relationship)
        if source_id == target_id or edge_key in seen:
            return
        seen.add(edge_key)
        edges.append(GraphEdgeRecord(source_id, target_id, relationship))

    @staticmethod
    def _chunk_symbol(relative_path: str, chunk: ParsedChunk, index: int) -> str:
        if chunk.kind == "module":
            return "module"
        qualified_name = RepositoryIndexer._chunk_qualified_name(chunk)
        if qualified_name:
            return qualified_name
        if chunk.symbol_name:
            return chunk.symbol_name
        return f"chunk-{index}"

    @staticmethod
    def _chunk_qualified_name(chunk: ParsedChunk) -> Optional[str]:
        qualified_name = chunk.metadata.get("qualified_name")
        if isinstance(qualified_name, str) and qualified_name:
            return qualified_name
        return chunk.symbol_name

    @staticmethod
    def _resolve_symbol_reference(
        reference: str,
        source_qualified_name: Optional[str],
        qualified_ids: Dict[str, str],
        short_name_ids: Dict[str, set[str]],
    ) -> Optional[str]:
        if "." in reference and reference in qualified_ids:
            return qualified_ids[reference]

        if source_qualified_name and reference.startswith(("self.", "cls.")):
            if "." in source_qualified_name:
                class_scope = source_qualified_name.rsplit(".", 1)[0]
                scoped_reference = f"{class_scope}.{reference.split('.', 1)[1]}"
                if scoped_reference in qualified_ids:
                    return qualified_ids[scoped_reference]

        if "." in reference:
            short_reference = reference.split(".")[-1]
            candidates = short_name_ids.get(short_reference, set())
        else:
            candidates = short_name_ids.get(reference, set())
        if len(candidates) == 1:
            return next(iter(candidates))
        return None

    def _index_text_file(
        self,
        repository: str,
        relative_path: str,
        language: str,
        content: str,
    ) -> Tuple[List[ArtifactRecord], List[GraphEdgeRecord]]:
        text = content[:4000]
        if not text.strip():
            return [], []
        return [
            ArtifactRecord(
                artifact_id=self._artifact_id(repository, relative_path, "chunk-1", 3),
                repository=repository,
                file_path=relative_path,
                language=language,
                text=text,
                tier=3,
                fidelity="L-4",
                symbol_name=relative_path,
                line_start=1,
                line_end=max(1, text.count("\n") + 1),
                kind="chunk",
            )
        ], []

    @staticmethod
    def _artifact_id(repository: str, relative_path: str, symbol: str, tier: int) -> str:
        safe_symbol = symbol.replace(" ", "_")
        return f"{repository}:{relative_path}:{safe_symbol}:T{tier}"

    @staticmethod
    def _detect_language(path: Path) -> str:
        suffix = path.suffix.lower()
        mapping = {
            ".py": "python",
            ".js": "javascript",
            ".ts": "typescript",
            ".tsx": "typescript",
            ".jsx": "javascript",
            ".go": "go",
            ".rs": "rust",
            ".c": "c",
            ".h": "c",
            ".cpp": "cpp",
            ".hpp": "cpp",
            ".java": "java",
            ".cs": "csharp",
        }
        if suffix in mapping:
            return mapping[suffix]
        guessed, _ = mimetypes.guess_type(path.name)
        return guessed or "text"

    @staticmethod
    def _is_generated(content: str) -> bool:
        header = "\n".join(content.splitlines()[:5]).lower()
        markers = ("auto-generated", "autogenerated", "generated by", "do not edit")
        return any(marker in header for marker in markers)

    @classmethod
    def _contains_secret_pattern(cls, content: str) -> bool:
        sample = content[:8192]
        return any(pattern.search(sample) for pattern in cls.SECRET_PATTERNS)
