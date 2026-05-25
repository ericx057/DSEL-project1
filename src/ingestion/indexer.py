from __future__ import annotations

import ast
import mimetypes
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from src.retrieval.database import ArtifactRecord, GraphEdgeRecord, SQLiteUnifiedStore
from src.UMMDB.parser.filters import FileHeuristics


@dataclass(frozen=True)
class IndexReport:
    repository: str
    files_indexed: int
    files_skipped: int
    artifacts_indexed: int
    edges_indexed: int


@dataclass(frozen=True)
class _Symbol:
    name: str
    qualified_name: str
    kind: str
    signature: str
    line_start: int
    line_end: int
    text: str
    calls: Tuple[str, ...]
    inherits: Tuple[str, ...] = ()


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
    ):
        self.store = store
        self.exclusions = set(exclusions)
        self.heuristics = heuristics or FileHeuristics()

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

        if language == "python":
            return self._index_python_file(repository, relative_path, content)
        return self._index_text_file(repository, relative_path, language, content)

    def _index_python_file(
        self,
        repository: str,
        relative_path: str,
        content: str,
    ) -> Tuple[List[ArtifactRecord], List[GraphEdgeRecord]]:
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return self._index_text_file(repository, relative_path, "text", content)

        symbols = _PythonSymbolVisitor(content).collect(tree)
        artifacts: List[ArtifactRecord] = [
            ArtifactRecord(
                artifact_id=self._artifact_id(repository, relative_path, "module", 1),
                repository=repository,
                file_path=relative_path,
                language="python",
                text=f"module {relative_path}",
                tier=1,
                fidelity="L-1",
                symbol_name=relative_path,
                line_start=1,
                line_end=max(1, content.count("\n") + 1),
                kind="module",
            )
        ]
        symbol_ids_by_name: Dict[str, str] = {}
        for symbol in symbols:
            interface_id = self._artifact_id(repository, relative_path, symbol.qualified_name, 1)
            implementation_id = self._artifact_id(repository, relative_path, symbol.qualified_name, 3)
            symbol_ids_by_name[symbol.name] = interface_id
            symbol_ids_by_name[symbol.qualified_name] = interface_id
            artifacts.append(
                ArtifactRecord(
                    artifact_id=interface_id,
                    repository=repository,
                    file_path=relative_path,
                    language="python",
                    text=symbol.signature,
                    tier=1,
                    fidelity="L-1",
                    symbol_name=symbol.name,
                    line_start=symbol.line_start,
                    line_end=symbol.line_start,
                    kind=symbol.kind,
                    metadata={"qualified_name": symbol.qualified_name},
                )
            )
            artifacts.append(
                ArtifactRecord(
                    artifact_id=implementation_id,
                    repository=repository,
                    file_path=relative_path,
                    language="python",
                    text=symbol.text,
                    tier=3,
                    fidelity="L-1",
                    symbol_name=symbol.name,
                    line_start=symbol.line_start,
                    line_end=symbol.line_end,
                    kind=f"{symbol.kind}-implementation",
                    metadata={"qualified_name": symbol.qualified_name},
                )
            )

        edges: List[GraphEdgeRecord] = []
        for symbol in symbols:
            source_id = self._artifact_id(repository, relative_path, symbol.qualified_name, 1)
            for call in symbol.calls:
                target_id = symbol_ids_by_name.get(call)
                if target_id:
                    edges.append(GraphEdgeRecord(source_id, target_id, "calls"))
            for parent in symbol.inherits:
                target_id = symbol_ids_by_name.get(parent)
                if target_id:
                    edges.append(GraphEdgeRecord(source_id, target_id, "inherits"))
        return artifacts, edges

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


class _PythonSymbolVisitor(ast.NodeVisitor):
    def __init__(self, content: str):
        self.content = content
        self.parents: List[str] = []
        self.symbols: List[_Symbol] = []

    def collect(self, tree: ast.AST) -> List[_Symbol]:
        self.visit(tree)
        return self.symbols

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        qualified_name = ".".join([*self.parents, node.name]) if self.parents else node.name
        self.symbols.append(
            _Symbol(
                name=node.name,
                qualified_name=qualified_name,
                kind="class",
                signature=self._class_signature(node),
                line_start=node.lineno,
                line_end=getattr(node, "end_lineno", node.lineno),
                text=ast.get_source_segment(self.content, node) or self._class_signature(node),
                calls=tuple(_CallVisitor.collect_calls(node)),
                inherits=tuple(self._name(base) for base in node.bases if self._name(base)),
            )
        )
        self.parents.append(node.name)
        self.generic_visit(node)
        self.parents.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        qualified_name = ".".join([*self.parents, node.name]) if self.parents else node.name
        self.symbols.append(
            _Symbol(
                name=node.name,
                qualified_name=qualified_name,
                kind="function" if not self.parents else "method",
                signature=self._function_signature(node),
                line_start=node.lineno,
                line_end=getattr(node, "end_lineno", node.lineno),
                text=ast.get_source_segment(self.content, node) or self._function_signature(node),
                calls=tuple(_CallVisitor.collect_calls(node)),
            )
        )
        self.parents.append(node.name)
        self.generic_visit(node)
        self.parents.pop()

    @staticmethod
    def _function_signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
        prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
        args = [arg.arg for arg in node.args.args]
        return f"{prefix} {node.name}({', '.join(args)})"

    @staticmethod
    def _class_signature(node: ast.ClassDef) -> str:
        bases = [name for base in node.bases if (name := _PythonSymbolVisitor._name(base))]
        return f"class {node.name}({', '.join(bases)})" if bases else f"class {node.name}"

    @staticmethod
    def _name(node: ast.AST) -> Optional[str]:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            parent = _PythonSymbolVisitor._name(node.value)
            return f"{parent}.{node.attr}" if parent else node.attr
        return None


class _CallVisitor(ast.NodeVisitor):
    def __init__(self):
        self.calls: List[str] = []

    @classmethod
    def collect_calls(cls, node: ast.AST) -> List[str]:
        visitor = cls()
        visitor.visit(node)
        return visitor.calls

    def visit_Call(self, node: ast.Call) -> None:
        name = _PythonSymbolVisitor._name(node.func)
        if name:
            self.calls.append(name.split(".")[-1])
            if "." in name:
                self.calls.append(name)
        self.generic_visit(node)
