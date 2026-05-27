from __future__ import annotations

import ast
from pathlib import Path
from typing import Optional


class PythonAstParser:
    def can_parse(self, file_path: str, language: Optional[str]) -> bool:
        return (language or "").lower() == "python" or Path(file_path).suffix.lower() == ".py"

    def parse(self, file_path: str, language: Optional[str]) -> list[object]:
        from .cascade import ParsedChunk

        if not self.can_parse(file_path, language):
            return []

        content = Path(file_path).read_text(encoding="utf-8")
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return []

        line_count = max(1, content.count("\n") + 1)
        chunks = [
            ParsedChunk(
                f"module {Path(file_path).name}",
                "L-1",
                {"parser": "python-ast", "qualified_name": Path(file_path).name},
                symbol_name=Path(file_path).name,
                line_start=1,
                line_end=line_count,
                kind="module",
                tier=1,
            )
        ]
        chunks.extend(_PythonChunkVisitor(content).collect(tree))
        return chunks


class _PythonChunkVisitor(ast.NodeVisitor):
    def __init__(self, content: str):
        self.content = content
        self.parents: list[str] = []
        self.chunks: list[object] = []

    def collect(self, tree: ast.AST) -> list[object]:
        self.visit(tree)
        return self.chunks

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        from .cascade import ParsedChunk

        qualified_name = self._qualified_name(node.name)
        line_end = getattr(node, "end_lineno", node.lineno)
        inherits = tuple(name for base in node.bases if (name := self._name(base)))
        metadata = {"parser": "python-ast", "qualified_name": qualified_name}
        self.chunks.append(
            ParsedChunk(
                self._class_signature(node),
                "L-1",
                {**metadata, "chunk_role": "interface"},
                symbol_name=node.name,
                line_start=node.lineno,
                line_end=node.lineno,
                kind="class",
                tier=1,
                inherits=inherits,
            )
        )
        self.chunks.append(
            ParsedChunk(
                ast.get_source_segment(self.content, node) or self._class_signature(node),
                "L-1",
                {**metadata, "chunk_role": "implementation"},
                symbol_name=node.name,
                line_start=node.lineno,
                line_end=line_end,
                kind="class-implementation",
                tier=3,
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
        from .cascade import ParsedChunk

        qualified_name = self._qualified_name(node.name)
        line_end = getattr(node, "end_lineno", node.lineno)
        kind = "function" if not self.parents else "method"
        metadata = {"parser": "python-ast", "qualified_name": qualified_name}
        calls = _CallVisitor.collect_calls(node)
        self.chunks.append(
            ParsedChunk(
                self._function_signature(node),
                "L-1",
                {**metadata, "chunk_role": "interface"},
                symbol_name=node.name,
                line_start=node.lineno,
                line_end=node.lineno,
                kind=kind,
                tier=1,
                calls=calls,
            )
        )
        self.chunks.append(
            ParsedChunk(
                ast.get_source_segment(self.content, node) or self._function_signature(node),
                "L-1",
                {**metadata, "chunk_role": "implementation"},
                symbol_name=node.name,
                line_start=node.lineno,
                line_end=line_end,
                kind=f"{kind}-implementation",
                tier=3,
            )
        )
        self.parents.append(node.name)
        self.generic_visit(node)
        self.parents.pop()

    def _qualified_name(self, name: str) -> str:
        return ".".join([*self.parents, name]) if self.parents else name

    @staticmethod
    def _function_signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
        prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
        args = [arg.arg for arg in node.args.args]
        return f"{prefix} {node.name}({', '.join(args)})"

    @staticmethod
    def _class_signature(node: ast.ClassDef) -> str:
        bases = [name for base in node.bases if (name := _PythonChunkVisitor._name(base))]
        return f"class {node.name}({', '.join(bases)})" if bases else f"class {node.name}"

    @staticmethod
    def _name(node: ast.AST) -> Optional[str]:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            parent = _PythonChunkVisitor._name(node.value)
            return f"{parent}.{node.attr}" if parent else node.attr
        return None


class _CallVisitor(ast.NodeVisitor):
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
        name = _PythonChunkVisitor._name(node.func)
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
