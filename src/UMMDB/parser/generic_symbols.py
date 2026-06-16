from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class _Symbol:
    name: str
    qualified_name: str
    kind: str
    line_start: int
    signature_end: int
    body_end: int
    calls: tuple[str, ...]


class GenericSymbolParser:
    _EXTENSION_LANGUAGES = {
        ".js": "javascript",
        ".jsx": "javascript",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".go": "go",
        ".rs": "rust",
        ".java": "java",
        ".cs": "csharp",
    }
    _SUPPORTED_LANGUAGES = set(_EXTENSION_LANGUAGES.values())
    _CLASS_PATTERNS = {
        "javascript": re.compile(r"\b(?:export\s+default\s+|export\s+)?(?:abstract\s+)?class\s+([A-Za-z_$][A-Za-z0-9_$]*)"),
        "typescript": re.compile(r"\b(?:export\s+default\s+|export\s+)?(?:abstract\s+)?class\s+([A-Za-z_$][A-Za-z0-9_$]*)"),
        "java": re.compile(r"\b(?:public|private|protected|abstract|final|static|\s)*\b(?:class|interface|enum)\s+([A-Za-z_][A-Za-z0-9_]*)"),
        "csharp": re.compile(r"\b(?:public|private|protected|internal|abstract|sealed|static|partial|\s)*\b(?:class|interface|struct|enum|record)\s+([A-Za-z_][A-Za-z0-9_]*)"),
        "go": re.compile(r"\btype\s+([A-Za-z_][A-Za-z0-9_]*)\s+struct\b"),
        "rust": re.compile(r"\b(?:pub\s+)?(?:struct|enum|trait)\s+([A-Za-z_][A-Za-z0-9_]*)"),
    }
    _JS_FUNCTION_RE = re.compile(r"\b(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*\(")
    _JS_ARROW_RE = re.compile(r"\b(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*=\s*(?:async\s*)?(?:\([^)]*\)|[A-Za-z_$][A-Za-z0-9_$]*)\s*=>")
    _JS_METHOD_RE = re.compile(
        r"^\s*(?:public|private|protected|static|async|override|readonly|get|set|\s)*"
        r"([A-Za-z_$][A-Za-z0-9_$]*)\s*(?:<[^>]+>)?\s*\([^)]*\)\s*(?::\s*[A-Za-z0-9_<>,\[\]\s|.&?]+)?\s*\{?"
    )
    _GO_FUNCTION_RE = re.compile(r"^\s*func\s+(?:\((?P<receiver>[^)]*)\)\s*)?(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*\(")
    _RUST_IMPL_RE = re.compile(r"^\s*impl(?:\s*<[^>]+>)?\s+([A-Za-z_][A-Za-z0-9_]*)")
    _RUST_FUNCTION_RE = re.compile(r"^\s*(?:pub(?:\([^)]*\))?\s+)?(?:async\s+)?fn\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(")
    _JVM_METHOD_RE = re.compile(
        r"^\s*(?:public|private|protected|internal|static|final|abstract|virtual|override|async|sealed|partial|synchronized|\s)+"
        r"(?:[A-Za-z_][A-Za-z0-9_<>,\[\].?]*\s+)+([A-Za-z_][A-Za-z0-9_]*)\s*\([^;]*\)\s*(?:throws\s+[^{]+)?\{?"
    )
    _CALL_RE = re.compile(r"\b([A-Za-z_$][A-Za-z0-9_$]*)\s*\(")
    _CALL_EXCLUDES = {
        "catch",
        "class",
        "for",
        "func",
        "function",
        "if",
        "new",
        "return",
        "sizeof",
        "switch",
        "while",
    }
    _METHOD_EXCLUDES = _CALL_EXCLUDES | {"constructor", "get", "set"}

    def can_parse(self, file_path: str, language: Optional[str]) -> bool:
        language_name = self._resolve_language(file_path, language)
        return language_name in self._SUPPORTED_LANGUAGES

    def parse(self, file_path: str, language: Optional[str]) -> list[object]:
        from .cascade import ParsedChunk

        language_name = self._resolve_language(file_path, language)
        if language_name not in self._SUPPORTED_LANGUAGES:
            return []

        content = Path(file_path).read_text(encoding="utf-8")
        lines = content.splitlines()
        symbols = self._symbols(lines, language_name)
        chunks: list[object] = []
        for symbol in symbols:
            signature = " ".join(line.strip() for line in lines[symbol.line_start - 1 : symbol.signature_end])
            interface = signature.split("{", 1)[0].rstrip(" ;") + ";"
            metadata = {
                "parser": "generic-symbols",
                "language": language_name,
                "qualified_name": symbol.qualified_name,
                "chunk_role": "interface",
            }
            chunks.append(
                ParsedChunk(
                    interface,
                    "L-2",
                    metadata,
                    symbol_name=symbol.name,
                    line_start=symbol.line_start,
                    line_end=symbol.signature_end,
                    kind=symbol.kind,
                    tier=1,
                    calls=symbol.calls,
                )
            )
            if symbol.body_end > symbol.signature_end or "{" in signature:
                chunks.append(
                    ParsedChunk(
                        "\n".join(lines[symbol.line_start - 1 : symbol.body_end]),
                        "L-3",
                        {**metadata, "chunk_role": "implementation"},
                        symbol_name=symbol.name,
                        line_start=symbol.line_start,
                        line_end=symbol.body_end,
                        kind=f"{symbol.kind}-implementation",
                        tier=3,
                        calls=symbol.calls,
                    )
                )
        return chunks

    def _symbols(self, lines: list[str], language: str) -> list[_Symbol]:
        symbols: list[_Symbol] = []
        class_stack: list[tuple[str, int]] = []
        rust_impl_stack: list[tuple[str, int]] = []
        brace_depth = 0

        for index, line in enumerate(lines):
            stripped = line.strip()
            class_stack = [(name, depth) for name, depth in class_stack if brace_depth >= depth]
            rust_impl_stack = [(name, depth) for name, depth in rust_impl_stack if brace_depth >= depth]

            class_match = self._CLASS_PATTERNS[language].search(line)
            if class_match:
                class_name = class_match.group(1)
                end = self._find_body_end(lines, index)
                symbols.append(
                    _Symbol(
                        name=class_name,
                        qualified_name=class_name,
                        kind="class",
                        line_start=index + 1,
                        signature_end=index + 1,
                        body_end=max(index + 1, end + 1),
                        calls=(),
                    )
                )
                if "{" in line:
                    class_stack.append((class_name, brace_depth + 1))

            if language == "rust":
                impl_match = self._RUST_IMPL_RE.match(line)
                if impl_match and "{" in line:
                    rust_impl_stack.append((impl_match.group(1), brace_depth + 1))

            symbol = self._function_symbol(lines, index, language, class_stack, rust_impl_stack)
            if symbol is not None:
                symbols.append(symbol)

            brace_depth += line.count("{") - line.count("}")

        return symbols

    def _function_symbol(
        self,
        lines: list[str],
        index: int,
        language: str,
        class_stack: list[tuple[str, int]],
        rust_impl_stack: list[tuple[str, int]],
    ) -> Optional[_Symbol]:
        line = lines[index]
        stripped = line.strip()
        if not stripped or stripped.startswith(("//", "/*", "*", "@")):
            return None

        owner = class_stack[-1][0] if class_stack else None
        name: Optional[str] = None
        receiver_owner: Optional[str] = None

        if language in {"javascript", "typescript"}:
            match = self._JS_FUNCTION_RE.search(line) or self._JS_ARROW_RE.search(line)
            if match:
                name = match.group(1)
            elif owner:
                method_match = self._JS_METHOD_RE.match(line)
                if method_match:
                    name = method_match.group(1)
        elif language == "go":
            match = self._GO_FUNCTION_RE.match(line)
            if match:
                name = match.group("name")
                receiver_owner = self._go_receiver_owner(match.group("receiver") or "")
        elif language == "rust":
            match = self._RUST_FUNCTION_RE.match(line)
            if match:
                name = match.group(1)
                owner = rust_impl_stack[-1][0] if rust_impl_stack else owner
        elif language in {"java", "csharp"}:
            method_match = self._JVM_METHOD_RE.match(line)
            if method_match:
                name = method_match.group(1)

        if not name or name in self._METHOD_EXCLUDES:
            return None

        effective_owner = receiver_owner or owner
        kind = "method" if effective_owner else "function"
        qualified_name = f"{effective_owner}.{name}" if effective_owner else name
        signature_end = self._find_signature_end(lines, index)
        body_end = self._find_body_end(lines, signature_end)
        body = "\n".join(lines[index : max(body_end + 1, signature_end + 1)])
        body_for_calls = body.split("{", 1)[1] if "{" in body else body
        return _Symbol(
            name=name,
            qualified_name=qualified_name,
            kind=kind,
            line_start=index + 1,
            signature_end=signature_end + 1,
            body_end=max(body_end + 1, signature_end + 1),
            calls=self._collect_calls(body_for_calls),
        )

    @classmethod
    def _collect_calls(cls, body: str) -> tuple[str, ...]:
        calls: list[str] = []
        for match in cls._CALL_RE.finditer(body):
            name = match.group(1)
            if name in cls._CALL_EXCLUDES:
                continue
            if name not in calls:
                calls.append(name)
        return tuple(calls)

    @staticmethod
    def _go_receiver_owner(receiver: str) -> Optional[str]:
        cleaned = receiver.replace("*", " ").strip()
        parts = cleaned.split()
        return parts[-1] if parts else None

    @staticmethod
    def _find_signature_end(lines: list[str], start: int) -> int:
        for index in range(start, min(len(lines), start + 12)):
            if "{" in lines[index] or lines[index].rstrip().endswith((";", "=>")):
                return index
            if index > start and not lines[index].strip():
                return index - 1
        return start

    @staticmethod
    def _find_body_end(lines: list[str], open_line: int) -> int:
        depth = 0
        saw_open = False
        for index in range(open_line, len(lines)):
            for char in lines[index]:
                if char == "{":
                    depth += 1
                    saw_open = True
                elif char == "}":
                    depth -= 1
            if saw_open and depth <= 0:
                return index
        return open_line

    @classmethod
    def _resolve_language(cls, file_path: str, language: Optional[str]) -> Optional[str]:
        if language:
            return language.lower()
        return cls._EXTENSION_LANGUAGES.get(Path(file_path).suffix.lower())
