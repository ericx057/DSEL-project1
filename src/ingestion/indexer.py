from __future__ import annotations

import json
import mimetypes
import re
from collections import defaultdict
from dataclasses import dataclass, field
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
    skipped_by_reason: Dict[str, int] = field(default_factory=dict)


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
    JSON_SUFFIXES = {".json"}
    MARKDOWN_SUFFIXES = {".md", ".markdown"}

    def __init__(
        self,
        store: SQLiteUnifiedStore,
        heuristics: Optional[FileHeuristics] = None,
        exclusions: Sequence[str] = DEFAULT_EXCLUDES,
        parser: Optional[CascadingParser] = None,
        include_paths: Optional[Sequence[str | Path]] = None,
    ):
        self.store = store
        self.exclusions = set(exclusions)
        self.heuristics = heuristics or FileHeuristics()
        self.parser = parser or CascadingParser()
        self.include_paths = tuple(Path(path) for path in include_paths) if include_paths is not None else None

    def index_repository(self, repository: str, repo_path: str | Path) -> IndexReport:
        root = Path(repo_path).resolve()
        if not root.exists() or not root.is_dir():
            raise ValueError(f"Repository path does not exist: {root}")

        self.store.delete_repository(repository)
        artifacts: List[ArtifactRecord] = []
        edges: List[GraphEdgeRecord] = []
        files_indexed = 0
        files_skipped = 0
        skipped_by_reason: Dict[str, int] = defaultdict(int)

        for file_path in self._iter_files(root):
            if self._is_excluded(root, file_path):
                skipped_by_reason["excluded_path"] += 1
                files_skipped += 1
                continue
            if self._is_sensitive_path(root, file_path):
                skipped_by_reason["sensitive_path"] += 1
                files_skipped += 1
                continue
            if not self.heuristics.is_human_readable(str(file_path)):
                skipped_by_reason["not_human_readable"] += 1
                files_skipped += 1
                continue
            file_artifacts, file_edges, skip_reason = self._index_file(repository, root, file_path)
            if not file_artifacts:
                skipped_by_reason[skip_reason or "no_artifacts"] += 1
                files_skipped += 1
                continue
            artifacts.extend(file_artifacts)
            edges.extend(file_edges)
            files_indexed += 1

        edges.extend(self._build_cross_file_edges(artifacts))
        self.store.upsert_artifacts(artifacts)
        self.store.upsert_edges(edges)
        return IndexReport(
            repository=repository,
            files_indexed=files_indexed,
            files_skipped=files_skipped,
            artifacts_indexed=len(artifacts),
            edges_indexed=len(edges),
            skipped_by_reason=dict(sorted(skipped_by_reason.items())),
        )

    def _iter_files(self, root: Path) -> Iterable[Path]:
        seen: set[Path] = set()
        for start_path in self._iter_start_paths(root):
            if start_path.is_file():
                if start_path not in seen:
                    seen.add(start_path)
                    yield start_path
                continue
            for path in start_path.rglob("*"):
                if not path.is_file() or path in seen:
                    continue
                seen.add(path)
                yield path

    def _iter_start_paths(self, root: Path) -> Tuple[Path, ...]:
        if self.include_paths is None:
            return (root,)

        start_paths: List[Path] = []
        for include_path in self.include_paths:
            target = (root / include_path).resolve()
            try:
                target.relative_to(root)
            except ValueError as exc:
                raise ValueError(f"Included index path escapes repository root: {include_path}") from exc
            if target.exists():
                start_paths.append(target)
        return tuple(start_paths)

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
    ) -> Tuple[List[ArtifactRecord], List[GraphEdgeRecord], Optional[str]]:
        relative_path = file_path.relative_to(root).as_posix()
        content = file_path.read_text(encoding="utf-8")
        language = self._detect_language(file_path, content)
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
            ], [], None

        if self._contains_secret_pattern(content):
            return [], [], "secret_pattern"

        if self._is_json_document(file_path, content):
            return self._index_json_file(repository, root, file_path, relative_path, "json", content)

        chunks = self.parser.parse(str(file_path), language)
        if not chunks:
            artifacts, edges = self._index_text_file(repository, relative_path, language, content)
        else:
            artifacts, edges = self._index_chunks(repository, relative_path, language, chunks)
        artifacts.extend(self._extra_structured_artifacts(repository, relative_path, language, content))
        return artifacts, edges, None if artifacts else "empty_or_unparseable"

    def _index_json_file(
        self,
        repository: str,
        root: Path,
        file_path: Path,
        relative_path: str,
        language: str,
        content: str,
    ) -> Tuple[List[ArtifactRecord], List[GraphEdgeRecord], Optional[str]]:
        try:
            payload = json.loads(content)
        except json.JSONDecodeError:
            artifacts, edges = self._index_text_file(repository, relative_path, language, content)
            return artifacts, edges, None if artifacts else "empty_or_unparseable"

        metadata = {
            "parser": "json-document",
            "json_references": self._json_references(root, file_path, payload),
        }
        if isinstance(payload, dict):
            if isinstance(payload.get("title"), str):
                metadata["title"] = payload["title"]
            if isinstance(payload.get("description"), str):
                metadata["description"] = payload["description"]

        return [
            ArtifactRecord(
                artifact_id=self._artifact_id(repository, relative_path, "json-document", 3),
                repository=repository,
                file_path=relative_path,
                language=language,
                text=self._json_document_text(relative_path, payload),
                tier=3,
                fidelity="L-2",
                symbol_name=relative_path,
                line_start=1,
                line_end=max(1, content.count("\n") + 1),
                kind="json-document",
                metadata=metadata,
            )
        ], [], None

    def _build_cross_file_edges(self, artifacts: Sequence[ArtifactRecord]) -> List[GraphEdgeRecord]:
        document_ids: Dict[str, str] = {}
        schema_ids: Dict[str, str] = {}
        first_ids: Dict[str, str] = {}
        for artifact in artifacts:
            normalized_path = artifact.file_path.lower()
            first_ids.setdefault(normalized_path, artifact.artifact_id)
            if artifact.kind == "json-document":
                document_ids.setdefault(normalized_path, artifact.artifact_id)
                if self._is_json_schema_artifact(artifact):
                    schema_ids.setdefault(normalized_path, artifact.artifact_id)
        edges: List[GraphEdgeRecord] = []
        seen: set[Tuple[str, str, str]] = set()

        for artifact in artifacts:
            if artifact.kind == "json-document":
                for schema_path in self._candidate_schema_paths(artifact.file_path):
                    if schema_path not in schema_ids:
                        continue
                    self._append_edge(
                        edges,
                        seen,
                        artifact.artifact_id,
                        schema_ids[schema_path],
                        "validated-by",
                    )
                    break

                for reference in artifact.metadata.get("json_references", []):
                    if not isinstance(reference, dict):
                        continue
                    target_path = reference.get("target_path")
                    if isinstance(target_path, str) and target_path.lower() in first_ids:
                        self._append_edge(
                            edges,
                            seen,
                            artifact.artifact_id,
                            first_ids[target_path.lower()],
                            "references",
                        )
        return edges

    def _extra_structured_artifacts(
        self,
        repository: str,
        relative_path: str,
        language: str,
        content: str,
    ) -> List[ArtifactRecord]:
        if Path(relative_path).suffix.lower() in self.MARKDOWN_SUFFIXES:
            text = self._markdown_table_text(relative_path, content)
            if text:
                return [
                    self._structured_artifact(
                        repository,
                        relative_path,
                        "markdown-table",
                        language,
                        text,
                        {"parser": "markdown-table"},
                    )
                ]
        return []

    def _structured_artifact(
        self,
        repository: str,
        relative_path: str,
        symbol: str,
        language: str,
        text: str,
        metadata: Dict[str, object],
    ) -> ArtifactRecord:
        return ArtifactRecord(
            artifact_id=self._artifact_id(repository, relative_path, symbol, 3),
            repository=repository,
            file_path=relative_path,
            language=language,
            text=text,
            tier=3,
            fidelity="L-2",
            symbol_name=symbol,
            line_start=1,
            line_end=max(1, text.count("\n") + 1),
            kind=symbol,
            metadata=metadata,
        )

    def _markdown_table_text(self, relative_path: str, content: str) -> str:
        lines = [f"markdown tables {relative_path}", f"file_path = {relative_path}"]
        source_lines = content.splitlines()
        table_index = 0
        index = 0
        while index + 1 < len(source_lines):
            headers = self._markdown_table_columns(source_lines[index])
            if len(headers) < 2 or not self._is_markdown_table_separator(source_lines[index + 1]):
                index += 1
                continue

            table_index += 1
            index += 2
            row_index = 0
            while index < len(source_lines):
                values = self._markdown_table_columns(source_lines[index])
                if not values:
                    break
                row_index += 1
                pairs = list(zip(headers, values))
                lines.append(
                    f"table[{table_index}].row[{row_index}] = "
                    + " | ".join(f"{header}: {value}" for header, value in pairs)
                )
                for header, value in pairs:
                    lines.append(f"table[{table_index}].row[{row_index}].{header} = {value}")
                index += 1
            continue
        return "\n".join(lines) if table_index else ""

    @staticmethod
    def _markdown_table_columns(line: str) -> List[str]:
        if "|" not in line:
            return []
        return [column.strip() for column in line.strip().strip("|").split("|")]

    @classmethod
    def _is_markdown_table_separator(cls, line: str) -> bool:
        columns = cls._markdown_table_columns(line)
        if len(columns) < 2:
            return False
        return all(re.fullmatch(r":?-{3,}:?", column.replace(" ", "")) for column in columns)

    def _json_references(self, root: Path, file_path: Path, payload: object) -> List[Dict[str, str]]:
        references: List[Dict[str, str]] = []
        for json_path, value in self._iter_json_leaf_values(payload):
            if not isinstance(value, str):
                continue
            target_path = self._resolve_json_reference(root, file_path, value)
            if target_path is None:
                continue
            references.append(
                {
                    "path": json_path,
                    "key": self._json_path_key(json_path),
                    "value": value,
                    "target_path": target_path,
                }
            )
        return references

    @staticmethod
    def _resolve_json_reference(root: Path, file_path: Path, value: str) -> Optional[str]:
        normalized = value.strip().replace("\\", "/")
        if not normalized or re.match(r"^[a-z][a-z0-9+.-]*://", normalized, re.IGNORECASE):
            return None
        if not (
            normalized.startswith(("./", "../"))
            or "/" in normalized
            or bool(Path(normalized).suffix)
        ):
            return None

        candidates = []
        if normalized.startswith(("./", "../")):
            candidates.append((file_path.parent / normalized).resolve())
        else:
            candidates.append((root / normalized).resolve())
            candidates.append((file_path.parent / normalized).resolve())

        for target in candidates:
            if not target.is_file():
                continue
            try:
                return target.relative_to(root).as_posix()
            except ValueError:
                continue
        return None

    @staticmethod
    def _json_path_key(json_path: str) -> str:
        key = json_path.rsplit(".", 1)[-1]
        return key.split("[", 1)[0]

    def _json_document_text(self, relative_path: str, payload: object) -> str:
        lines = [
            f"json document {relative_path}",
            f"file_path = {relative_path}",
            f"basename = {Path(relative_path).name}",
            f"extension = {Path(relative_path).suffix.lower()}",
        ]
        if isinstance(payload, dict):
            title = payload.get("title")
            description = payload.get("description")
            if self._is_json_schema_payload(payload):
                lines.append("document_role = json schema")
            if isinstance(title, str):
                lines.append(f"title = {title}")
            if isinstance(description, str):
                lines.append(f"description = {description}")
        for path, value in self._iter_json_leaf_values(payload):
            lines.append(f"{path} = {self._json_value_text(value)}")
        return "\n".join(lines)

    def _iter_json_leaf_values(self, node: object, prefix: str = "") -> Iterable[Tuple[str, object]]:
        if isinstance(node, dict):
            for key, value in node.items():
                child_prefix = f"{prefix}.{key}" if prefix else key
                yield from self._iter_json_leaf_values(value, child_prefix)
        elif isinstance(node, list):
            for index, value in enumerate(node):
                yield from self._iter_json_leaf_values(value, f"{prefix}[{index}]")
        elif isinstance(node, (str, int, float, bool)) or node is None:
            yield prefix, node

    @staticmethod
    def _json_value_text(value: object) -> str:
        if isinstance(value, str):
            return value
        return json.dumps(value, sort_keys=True, separators=(",", ":"))

    @staticmethod
    def _is_json_schema_payload(payload: object) -> bool:
        return isinstance(payload, dict) and (
            "$schema" in payload
            or isinstance(payload.get("properties"), dict)
            or isinstance(payload.get("$defs"), dict)
            or isinstance(payload.get("definitions"), dict)
        )

    @staticmethod
    def _is_json_schema_artifact(artifact: ArtifactRecord) -> bool:
        file_path = artifact.file_path.lower()
        return artifact.kind == "json-document" and (
            file_path.endswith(".schema.json")
            or "document_role = json schema" in artifact.text.lower()
            or "$schema =" in artifact.text.lower()
        )

    @staticmethod
    def _candidate_schema_paths(relative_path: str) -> List[str]:
        path = Path(relative_path)
        suffix = path.suffix.lower().lstrip(".")
        stem = path.stem.lower()
        parent = path.parent.as_posix().lower()
        names = []
        if suffix:
            names.extend(
                [
                    f"schemas/{suffix}.schema.json",
                    f"schema/{suffix}.schema.json",
                    f"{parent}/{suffix}.schema.json" if parent != "." else f"{suffix}.schema.json",
                ]
            )
        if stem:
            names.extend(
                [
                    f"schemas/{stem}.schema.json",
                    f"schema/{stem}.schema.json",
                    f"{parent}/{stem}.schema.json" if parent != "." else f"{stem}.schema.json",
                    f"{parent}/{path.name.lower()}.schema.json" if parent != "." else f"{path.name.lower()}.schema.json",
                ]
            )
        return list(dict.fromkeys(name.replace("\\", "/") for name in names if name))

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
            signature_hash = chunk.metadata.get("signature_hash")
            if isinstance(signature_hash, str) and signature_hash:
                return f"{qualified_name}#{signature_hash}"
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
            return None

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
    def _detect_language(path: Path, content: str = "") -> str:
        suffix = path.suffix.lower()
        if suffix == ".h" and RepositoryIndexer._looks_like_cpp_header(content):
            return "cpp"
        mapping = {
            ".json": "json",
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
    def _looks_like_cpp_header(content: str) -> bool:
        sample = content[:8192]
        return bool(re.search(r"\b(class|namespace|template)\b|::|\b(public|private|protected):", sample))

    @classmethod
    def _is_json_document(cls, path: Path, content: str) -> bool:
        return path.suffix.lower() in cls.JSON_SUFFIXES or cls._looks_like_json(content)

    @staticmethod
    def _looks_like_json(content: str) -> bool:
        stripped = content.lstrip()
        return stripped.startswith("{") or stripped.startswith("[")

    @staticmethod
    def _is_generated(content: str) -> bool:
        header = "\n".join(content.splitlines()[:5]).lower()
        markers = ("auto-generated", "autogenerated", "generated by", "do not edit")
        return any(marker in header for marker in markers)

    @classmethod
    def _contains_secret_pattern(cls, content: str) -> bool:
        sample = content[:8192]
        return any(pattern.search(sample) for pattern in cls.SECRET_PATTERNS)
