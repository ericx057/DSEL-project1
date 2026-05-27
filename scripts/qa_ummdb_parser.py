from __future__ import annotations

import argparse
import ast
import json
import random
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.UMMDB.parser.cascade import CascadingParser, ParsedChunk
from src.ingestion.indexer import RepositoryIndexer
from src.retrieval.database import HashingEmbeddingProvider, SQLiteUnifiedStore


@dataclass(frozen=True)
class ExpectedSymbol:
    file_path: str
    qualified_name: str
    kind: str
    line_start: int
    line_end: int
    calls: tuple[str, ...]
    inherits: tuple[str, ...]


@dataclass(frozen=True)
class SampleResult:
    file_path: str
    qualified_name: str
    expected_kind: str
    actual_kind: Optional[str]
    passed: bool
    issues: tuple[str, ...]


class FlaskParserQa:
    def __init__(self, repo_path: Path, sample_size: int, seed: int):
        self.repo_path = repo_path.resolve()
        self.sample_size = sample_size
        self.seed = seed
        self.parser = CascadingParser()

    def run(self) -> dict[str, object]:
        expected_symbols = list(self._collect_expected_symbols())
        sample = self._sample(expected_symbols)
        parsed_by_file = {
            symbol.file_path: self._parse_file(self.repo_path / symbol.file_path)
            for symbol in sample
        }
        results = [
            self._evaluate_symbol(symbol, parsed_by_file[symbol.file_path])
            for symbol in sample
        ]
        passed = sum(1 for result in results if result.passed)
        index_report = self._run_indexer()
        return {
            "repo_path": str(self.repo_path),
            "sample_size": len(sample),
            "seed": self.seed,
            "symbols_available": len(expected_symbols),
            "passed": passed,
            "failed": len(sample) - passed,
            "accuracy": passed / len(sample) if sample else 0.0,
            "index_report": asdict(index_report),
            "failures": [
                asdict(result)
                for result in results
                if not result.passed
            ],
        }

    def _collect_expected_symbols(self) -> Iterable[ExpectedSymbol]:
        for path in sorted(self.repo_path.rglob("*.py")):
            if self._is_excluded(path):
                continue
            relative_path = path.relative_to(self.repo_path).as_posix()
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except (SyntaxError, UnicodeDecodeError):
                continue
            yield from _ExpectedSymbolVisitor(relative_path).collect(tree)

    def _sample(self, symbols: list[ExpectedSymbol]) -> list[ExpectedSymbol]:
        if len(symbols) <= self.sample_size:
            return symbols
        return random.Random(self.seed).sample(symbols, self.sample_size)

    def _parse_file(self, path: Path) -> dict[tuple[str, str], ParsedChunk]:
        chunks = self.parser.parse(str(path), "python")
        return {
            (chunk.metadata.get("qualified_name", ""), chunk.kind): chunk
            for chunk in chunks
            if isinstance(chunk.metadata.get("qualified_name"), str)
        }

    def _evaluate_symbol(
        self,
        expected: ExpectedSymbol,
        parsed_chunks: dict[tuple[str, str], ParsedChunk],
    ) -> SampleResult:
        interface = parsed_chunks.get((expected.qualified_name, expected.kind))
        implementation = parsed_chunks.get(
            (expected.qualified_name, f"{expected.kind}-implementation")
        )
        issues: list[str] = []

        if interface is None:
            issues.append("missing interface chunk")
        else:
            if interface.line_start != expected.line_start:
                issues.append("interface line_start mismatch")
            if tuple(interface.calls) != expected.calls:
                issues.append("calls mismatch")
            if tuple(interface.inherits) != expected.inherits:
                issues.append("inherits mismatch")

        if implementation is None:
            issues.append("missing implementation chunk")
        elif implementation.line_end != expected.line_end:
            issues.append("implementation line_end mismatch")

        return SampleResult(
            file_path=expected.file_path,
            qualified_name=expected.qualified_name,
            expected_kind=expected.kind,
            actual_kind=interface.kind if interface else None,
            passed=not issues,
            issues=tuple(issues),
        )

    def _run_indexer(self):
        db_path = self.repo_path.parent / "ummdb_qa_index.db"
        if db_path.exists():
            db_path.unlink()
        store = SQLiteUnifiedStore(db_path, HashingEmbeddingProvider(dimensions=32))
        try:
            return RepositoryIndexer(store).index_repository("flask-qa", self.repo_path)
        finally:
            store.close()

    def _is_excluded(self, path: Path) -> bool:
        relative_parts = path.relative_to(self.repo_path).parts
        return any(part in {".git", ".venv", "__pycache__"} for part in relative_parts)


class _ExpectedSymbolVisitor(ast.NodeVisitor):
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.parents: list[str] = []
        self.symbols: list[ExpectedSymbol] = []

    def collect(self, tree: ast.AST) -> list[ExpectedSymbol]:
        self.visit(tree)
        return self.symbols

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        qualified_name = self._qualified_name(node.name)
        self.symbols.append(
            ExpectedSymbol(
                file_path=self.file_path,
                qualified_name=qualified_name,
                kind="class",
                line_start=node.lineno,
                line_end=getattr(node, "end_lineno", node.lineno),
                calls=(),
                inherits=tuple(name for base in node.bases if (name := self._name(base))),
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
        qualified_name = self._qualified_name(node.name)
        self.symbols.append(
            ExpectedSymbol(
                file_path=self.file_path,
                qualified_name=qualified_name,
                kind="function" if not self.parents else "method",
                line_start=node.lineno,
                line_end=getattr(node, "end_lineno", node.lineno),
                calls=_CallCollector.collect_calls(node),
                inherits=(),
            )
        )
        self.parents.append(node.name)
        self.generic_visit(node)
        self.parents.pop()

    def _qualified_name(self, name: str) -> str:
        return ".".join([*self.parents, name]) if self.parents else name

    @staticmethod
    def _name(node: ast.AST) -> Optional[str]:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            parent = _ExpectedSymbolVisitor._name(node.value)
            return f"{parent}.{node.attr}" if parent else node.attr
        return None


class _CallCollector(ast.NodeVisitor):
    def __init__(self, root: ast.AST):
        self.root = root
        self.calls: list[str] = []

    @classmethod
    def collect_calls(cls, node: ast.AST) -> tuple[str, ...]:
        visitor = cls(node)
        visitor.visit(node)
        return tuple(visitor.calls)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        if node is self.root:
            self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        if node is self.root:
            self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        if node is self.root:
            self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        name = _ExpectedSymbolVisitor._name(node.func)
        if name:
            self._append_name(name)
        self.generic_visit(node)

    def _append_name(self, name: str) -> None:
        candidates = [name]
        if "." in name:
            candidates.append(name.split(".")[-1])
        for candidate in candidates:
            if candidate not in self.calls:
                self.calls.append(candidate)


def main() -> int:
    args = _parse_args()
    result = FlaskParserQa(args.repo_path, args.n, args.seed).run()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["failed"] == 0 else 1


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run local UMMDB parser QA against a Python repo.")
    parser.add_argument("repo_path", type=Path)
    parser.add_argument("--n", type=int, default=30)
    parser.add_argument("--seed", type=int, default=1337)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
