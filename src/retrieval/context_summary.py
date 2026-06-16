from __future__ import annotations

import re
from typing import Any, Dict, List, Sequence


class RetrievedContextSummarizer:
    _IDENTIFIER_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_:]*")
    _PATH_LIKE_RE = re.compile(r"(?i)(?:[A-Z]:[\\/]|(?:^|[\\/])|[A-Za-z0-9_.-]+[\\/]).*\.[A-Za-z0-9]{1,8}$")
    _STOPWORDS = {
        "and",
        "bool",
        "class",
        "const",
        "def",
        "else",
        "false",
        "for",
        "if",
        "int",
        "return",
        "self",
        "static",
        "struct",
        "the",
        "this",
        "true",
        "void",
        "while",
    }

    def summarize_chunks(self, chunks: Sequence[Dict[str, Any]], limit: int = 8) -> str:
        summaries = [self.summarize_chunk(chunk, index) for index, chunk in enumerate(chunks[:limit], 1)]
        return "\n".join(summaries) if summaries else "No retrieved artifacts."

    def summarize_chunk(self, chunk: Dict[str, Any], index: int) -> str:
        raw_symbol = str(chunk.get("symbol_name") or "").strip()
        symbol = self._display_symbol(raw_symbol, chunk)
        kind = str(chunk.get("kind") or "artifact").strip()
        language = str(chunk.get("language") or "").strip()
        line_start = chunk.get("line_start")
        line_end = chunk.get("line_end")
        descriptors = ", ".join(
            value
            for value in (kind, language, self._line_summary(line_start, line_end))
            if value
        )
        identifier_seed = "" if self._looks_like_path(raw_symbol) else raw_symbol
        identifiers = self._identifier_summary(str(chunk.get("text") or ""), identifier_seed)
        return f"[{index}] {symbol} ({descriptors}) - {identifiers}"

    @staticmethod
    def _line_summary(line_start: object, line_end: object) -> str:
        if isinstance(line_start, int) and isinstance(line_end, int) and line_start > 0:
            return f"lines {line_start}-{line_end}"
        return ""

    @classmethod
    def _identifier_summary(cls, text: str, symbol: str) -> str:
        identifiers: List[str] = []
        for value in (symbol, text):
            for raw_token in cls._IDENTIFIER_RE.findall(value):
                token = raw_token.strip(":")
                lowered = token.lower().strip(":")
                if len(lowered) <= 2 or lowered in cls._STOPWORDS:
                    continue
                if "/" in token or "\\" in token:
                    continue
                if token not in identifiers:
                    identifiers.append(token)
                if len(identifiers) >= 10:
                    break
            if len(identifiers) >= 10:
                break
        if not identifiers:
            return "No salient identifiers extracted."
        return "Mentions " + ", ".join(identifiers[:10]) + "."

    @classmethod
    def _display_symbol(cls, symbol: str, chunk: Dict[str, Any]) -> str:
        if symbol and not cls._looks_like_path(symbol):
            return symbol
        language = str(chunk.get("language") or "").strip()
        kind = str(chunk.get("kind") or "artifact").strip() or "artifact"
        if language:
            return f"{language} {kind}"
        return kind if kind != "chunk" else "unnamed artifact"

    @classmethod
    def _looks_like_path(cls, value: str) -> bool:
        normalized = value.strip()
        if not normalized:
            return False
        return bool(cls._PATH_LIKE_RE.search(normalized.replace("\\", "/")))


class ResponseShaper:
    _FILE_HEADER_RE = re.compile(r"^--- File: .*?---$", re.MULTILINE)
    _LEGACY_FILE_BLOCK_RE = re.compile(
        r"^--- File: (?P<file>.*?) \| Language: (?P<language>.*?) \| Tier: (?P<tier>\d+) ---\n"
        r"(?P<text>.*?)(?=^--- File: |\Z)",
        re.MULTILINE | re.DOTALL,
    )
    _PATH_RE = re.compile(
        r"(?i)\b(?:[A-Z]:[\\/]|(?:\.{1,2}|src|tests?|scripts?|evaluation|[A-Za-z0-9_.-]+)[\\/])"
        r"[^\s`'\"),]+"
    )
    _RAW_CODE_RE = re.compile(
        r"^\s*(?:class|def|async def|return|if|else|for|while|switch|case|"
        r"template|namespace|public:|private:|protected:|[A-Za-z_:<>~*&\s]+\([^)]*\)\s*(?:const)?\s*[;{])",
        re.MULTILINE,
    )

    def shape(self, text: str) -> str:
        stripped = text.strip()
        if not stripped:
            return stripped
        legacy_summary = self._shape_legacy_file_blocks(stripped)
        if legacy_summary:
            return legacy_summary
        shaped = self._FILE_HEADER_RE.sub("", stripped)
        shaped = self._PATH_RE.sub(" ", shaped)
        shaped = self._RAW_CODE_RE.sub("", shaped)
        shaped = shaped.replace("```", "")
        shaped = "\n".join(self._clean_line(line) for line in shaped.splitlines() if line.strip())
        shaped = re.sub(r"\n{3,}", "\n\n", shaped).strip()
        if shaped:
            return shaped
        return "The retrieved artifacts matched, but the cached response did not contain a usable summary."

    def _shape_legacy_file_blocks(self, text: str) -> str:
        matches = list(self._LEGACY_FILE_BLOCK_RE.finditer(text))
        if not matches:
            return ""

        chunks: List[Dict[str, Any]] = []
        notes: List[str] = []
        for index, match in enumerate(matches, start=1):
            language = match.group("language").strip()
            body = match.group("text")
            chunks.append(
                {
                    "symbol_name": "",
                    "kind": "cached artifact",
                    "language": language,
                    "line_start": 1,
                    "line_end": max(1, body.count("\n") + 1),
                    "text": body,
                }
            )
            for line in body.splitlines():
                note = self._clean_line(self._PATH_RE.sub(" ", line))
                if not note or self._is_raw_code_line(note):
                    continue
                if note not in notes:
                    notes.append(note)
                if len(notes) >= 6:
                    break

        parts = ["Retrieved summaries:", RetrievedContextSummarizer().summarize_chunks(chunks)]
        if notes:
            parts.extend(["Cached notes:", "\n".join(notes)])
        return "\n".join(part for part in parts if part).strip()

    @staticmethod
    def _clean_line(line: str) -> str:
        return re.sub(r"[ \t]{2,}", " ", line).strip()

    @classmethod
    def _is_raw_code_line(cls, line: str) -> bool:
        stripped = line.strip()
        if not stripped:
            return True
        if cls._RAW_CODE_RE.match(stripped):
            return True
        if stripped in {"{", "}", "};"}:
            return True
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*\s*=", stripped):
            return True
        if re.match(r"^[A-Za-z_][A-Za-z0-9_:.\->]*\s*\([^)]*\)\s*;?$", stripped):
            return True
        return False
