from __future__ import annotations

import re
from typing import Any, Dict, List, Sequence


class RetrievedContextSummarizer:
    _IDENTIFIER_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_:]*")
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
        symbol = str(chunk.get("symbol_name") or "").strip() or "unnamed artifact"
        kind = str(chunk.get("kind") or "artifact").strip()
        language = str(chunk.get("language") or "").strip()
        line_start = chunk.get("line_start")
        line_end = chunk.get("line_end")
        descriptors = ", ".join(
            value
            for value in (kind, language, self._line_summary(line_start, line_end))
            if value
        )
        identifiers = self._identifier_summary(str(chunk.get("text") or ""), symbol)
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
            for token in cls._IDENTIFIER_RE.findall(value):
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


class ResponseShaper:
    _FILE_HEADER_RE = re.compile(r"^--- File: .*?---$", re.MULTILINE)
    _PATH_RE = re.compile(
        r"(?i)(?:[A-Z]:\\|(?:^|[\s`'\"(])(?:\.{1,2}/|src/|tests?/|scripts?/|"
        r"evaluation/|[A-Za-z0-9_.-]+/)[^\s`'\"),]+)"
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
        shaped = self._FILE_HEADER_RE.sub("", stripped)
        shaped = self._PATH_RE.sub(" ", shaped)
        shaped = self._RAW_CODE_RE.sub("", shaped)
        shaped = shaped.replace("```", "")
        shaped = "\n".join(line.rstrip() for line in shaped.splitlines() if line.strip())
        shaped = re.sub(r"\n{3,}", "\n\n", shaped).strip()
        if shaped:
            return shaped
        return "The retrieved artifacts matched, but the cached response did not contain a usable summary."
