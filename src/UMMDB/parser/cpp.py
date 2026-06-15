from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class _CppSignature:
    simple_name: str
    qualified_name: str
    signature: str
    signature_hash: str
    interface: str
    kind: str
    has_body: bool
    calls: tuple[str, ...] = ()


class CppSignatureParser:
    _EXTENSION_LANGUAGES = {
        ".c": "c",
        ".cc": "cpp",
        ".cxx": "cpp",
        ".cpp": "cpp",
        ".h": "cpp",
        ".hh": "cpp",
        ".hxx": "cpp",
        ".hpp": "cpp",
    }
    _SUPPORTED_LANGUAGES = {"c", "cpp"}
    _CONTROL_PREFIXES = (
        "if ",
        "for ",
        "while ",
        "switch ",
        "catch ",
        "return ",
        "throw ",
        "else",
        "case ",
        "do ",
        "#",
        "//",
        "*",
        "public:",
        "private:",
        "protected:",
    )
    _CLASS_RE = re.compile(r"\b(?:class|struct)\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)(?:\s*:\s*(?P<bases>[^{;]+))?")
    _NAMESPACE_RE = re.compile(r"^\s*namespace\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*{")
    _NAME_RE = re.compile(r"(?P<qualified>(?:~?[A-Za-z_][A-Za-z0-9_]*::)*~?[A-Za-z_][A-Za-z0-9_]*)$")
    _CALL_RE = re.compile(r"\b(?P<name>[A-Za-z_][A-Za-z0-9_:]*)\s*\(")
    _CALL_EXCLUDES = {
        "if",
        "for",
        "while",
        "switch",
        "catch",
        "return",
        "sizeof",
        "static_cast",
        "reinterpret_cast",
        "dynamic_cast",
        "const_cast",
    }

    def can_parse(self, file_path: str, language: Optional[str]) -> bool:
        language_name = (language or self._EXTENSION_LANGUAGES.get(Path(file_path).suffix.lower()) or "").lower()
        return language_name in self._SUPPORTED_LANGUAGES

    def parse(self, file_path: str, language: Optional[str]) -> list[object]:
        from .cascade import ParsedChunk

        if not self.can_parse(file_path, language):
            return []

        content = Path(file_path).read_text(encoding="utf-8")
        lines = content.splitlines()
        chunks: list[object] = []
        namespace_stack: list[tuple[str, int]] = []
        brace_depth = 0
        index = 0

        while index < len(lines):
            stripped = lines[index].strip()
            namespace_match = self._NAMESPACE_RE.match(lines[index])
            if namespace_match:
                namespace_stack.append((namespace_match.group("name"), brace_depth + 1))

            class_match = self._CLASS_RE.search(stripped)
            if class_match and not stripped.startswith(("template", "using ")):
                parsed_class = self._parse_class(lines, index, namespace_stack, ParsedChunk)
                if parsed_class is not None:
                    class_chunks, end_index = parsed_class
                    chunks.extend(class_chunks)
                    for depth_index in range(index, end_index + 1):
                        brace_depth += lines[depth_index].count("{") - lines[depth_index].count("}")
                    namespace_stack = self._pop_namespaces(namespace_stack, brace_depth)
                    index = end_index + 1
                    continue

            if self._can_start_signature(lines[index]):
                parsed = self._collect_signature(lines, index)
                if parsed is not None:
                    signature_text, signature_end = parsed
                    body_end = self._find_body_end(lines, signature_end) if self._signature_terminator(signature_text) == "{" else signature_end
                    body = "\n".join(lines[index : body_end + 1]) if body_end >= index else ""
                    cpp_signature = self._parse_signature(signature_text, owner=None, body=body)
                    if cpp_signature is not None:
                        chunks.extend(self._signature_chunks(cpp_signature, lines, index, signature_end, body_end, ParsedChunk))
                        for depth_index in range(index, body_end + 1):
                            brace_depth += lines[depth_index].count("{") - lines[depth_index].count("}")
                        namespace_stack = self._pop_namespaces(namespace_stack, brace_depth)
                        index = body_end + 1
                        continue

            brace_depth += lines[index].count("{") - lines[index].count("}")
            namespace_stack = self._pop_namespaces(namespace_stack, brace_depth)
            index += 1

        return chunks

    def _parse_class(self, lines: list[str], start: int, namespace_stack: list[tuple[str, int]], parsed_chunk_type) -> Optional[tuple[list[object], int]]:
        header_lines: list[str] = []
        open_line = start
        for index in range(start, min(len(lines), start + 20)):
            header_lines.append(lines[index].strip())
            if "{" in lines[index] or ";" in lines[index]:
                open_line = index
                break
        header = " ".join(header_lines)
        match = self._CLASS_RE.search(header)
        if not match:
            return None
        class_name = match.group("name")
        namespace = "::".join(name for name, _ in namespace_stack)
        qualified_name = f"{namespace}::{class_name}" if namespace else class_name
        inherits = self._parse_bases(match.group("bases") or "")
        has_body = "{" in header
        end_line = self._find_body_end(lines, open_line) if has_body else open_line
        metadata = {"parser": "cpp-regex", "qualified_name": qualified_name, "chunk_role": "interface"}
        chunks = [
            parsed_chunk_type(
                self._class_interface(class_name, inherits),
                "L-2",
                metadata,
                symbol_name=class_name,
                line_start=start + 1,
                line_end=open_line + 1,
                kind="class",
                tier=1,
                inherits=inherits,
            )
        ]
        if has_body:
            chunks.extend(self._parse_class_methods(lines, start + 1, end_line, qualified_name, parsed_chunk_type))
        return chunks, end_line

    def _parse_class_methods(
        self,
        lines: list[str],
        start: int,
        end: int,
        owner: str,
        parsed_chunk_type,
    ) -> list[object]:
        chunks: list[object] = []
        index = start
        while index < end:
            if not self._can_start_signature(lines[index]):
                index += 1
                continue
            parsed = self._collect_signature(lines, index, end=end)
            if parsed is None:
                index += 1
                continue
            signature_text, signature_end = parsed
            body_end = self._find_body_end(lines, signature_end) if self._signature_terminator(signature_text) == "{" else signature_end
            body = "\n".join(lines[index : body_end + 1]) if body_end >= index else ""
            cpp_signature = self._parse_signature(signature_text, owner=owner, body=body)
            if cpp_signature is None:
                index += 1
                continue
            chunks.extend(self._signature_chunks(cpp_signature, lines, index, signature_end, body_end, parsed_chunk_type))
            index = body_end + 1
        return chunks

    def _signature_chunks(self, cpp_signature: _CppSignature, lines: list[str], start: int, signature_end: int, body_end: int, parsed_chunk_type) -> list[object]:
        metadata = {
            "parser": "cpp-regex",
            "qualified_name": cpp_signature.qualified_name,
            "signature": cpp_signature.signature,
            "signature_hash": cpp_signature.signature_hash,
        }
        chunks = [
            parsed_chunk_type(
                cpp_signature.interface,
                "L-2",
                {**metadata, "chunk_role": "interface"},
                symbol_name=cpp_signature.simple_name,
                line_start=start + 1,
                line_end=signature_end + 1,
                kind=cpp_signature.kind,
                tier=1,
                calls=cpp_signature.calls,
            )
        ]
        if cpp_signature.has_body:
            chunks.append(
                parsed_chunk_type(
                    "\n".join(lines[start : body_end + 1]),
                    "L-2",
                    {**metadata, "chunk_role": "implementation"},
                    symbol_name=cpp_signature.simple_name,
                    line_start=start + 1,
                    line_end=body_end + 1,
                    kind=f"{cpp_signature.kind}-implementation",
                    tier=3,
                    calls=cpp_signature.calls,
                )
            )
        return chunks

    def _can_start_signature(self, line: str) -> bool:
        stripped = line.strip()
        if not stripped:
            return False
        if stripped.startswith(self._CONTROL_PREFIXES):
            return False
        return "(" in stripped or stripped.startswith("template")

    def _collect_signature(self, lines: list[str], start: int, end: Optional[int] = None) -> Optional[tuple[str, int]]:
        collected: list[str] = []
        stop = min(len(lines), start + 20, end if end is not None else len(lines))
        for index in range(start, stop):
            stripped = lines[index].strip()
            if not stripped:
                break
            if index > start and stripped.startswith(self._CONTROL_PREFIXES):
                break
            collected.append(stripped)
            signature = " ".join(collected)
            if ")" in signature and self._signature_terminator(signature):
                return signature, index
        return None

    @staticmethod
    def _signature_terminator(signature: str) -> Optional[str]:
        closing = signature.rfind(")")
        if closing < 0:
            return None
        tail = signature[closing + 1 :]
        if "{" in tail:
            return "{"
        if ";" in tail:
            return ";"
        return None

    def _parse_signature(self, signature: str, owner: Optional[str], body: str) -> Optional[_CppSignature]:
        has_body = self._signature_terminator(signature) == "{"
        head = signature.split("{", 1)[0].split(";", 1)[0].strip()
        head = re.sub(r"\s+", " ", head)
        if "(" not in head:
            return None

        before_params, params_tail = head.rsplit("(", 1)
        before_params = before_params.strip()
        params = params_tail.rsplit(")", 1)[0].strip()
        match = self._NAME_RE.search(before_params)
        if not match:
            return None

        qualified_name = match.group("qualified")
        simple_name = qualified_name.rsplit("::", 1)[-1]
        if simple_name in self._CALL_EXCLUDES:
            return None

        prefix = before_params[: match.start("qualified")].strip()
        if owner and "::" not in qualified_name:
            qualified_name = f"{owner}::{simple_name}"
        if "::" not in qualified_name and not prefix:
            return None

        kind = "method" if "::" in qualified_name or owner else "function"
        normalized_signature = f"{qualified_name}({params})"
        signature_hash = hashlib.sha1(normalized_signature.encode("utf-8")).hexdigest()[:12]
        body_for_calls = body.split("{", 1)[1] if "{" in body else body
        calls = self._collect_calls(body_for_calls) if has_body else ()
        return _CppSignature(
            simple_name=simple_name,
            qualified_name=qualified_name,
            signature=normalized_signature,
            signature_hash=signature_hash,
            interface=f"{head};",
            kind=kind,
            has_body=has_body,
            calls=calls,
        )

    def _collect_calls(self, body: str) -> tuple[str, ...]:
        calls: list[str] = []
        for match in self._CALL_RE.finditer(body):
            name = match.group("name")
            leaf = name.rsplit("::", 1)[-1]
            if leaf in self._CALL_EXCLUDES:
                continue
            if name not in calls:
                calls.append(name)
        return tuple(calls)

    @staticmethod
    def _parse_bases(raw_bases: str) -> tuple[str, ...]:
        bases: list[str] = []
        for raw in raw_bases.split(","):
            value = raw.strip()
            if not value:
                continue
            value = re.sub(r"\b(public|private|protected|virtual|final)\b", "", value).strip()
            if value and value not in bases:
                bases.append(value)
        return tuple(bases)

    @staticmethod
    def _class_interface(class_name: str, inherits: tuple[str, ...]) -> str:
        if not inherits:
            return f"class {class_name};"
        return f"class {class_name} : {', '.join(inherits)};"

    @staticmethod
    def _pop_namespaces(namespace_stack: list[tuple[str, int]], brace_depth: int) -> list[tuple[str, int]]:
        return [(name, depth) for name, depth in namespace_stack if brace_depth >= depth]

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
