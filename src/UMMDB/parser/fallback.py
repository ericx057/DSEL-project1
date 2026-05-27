import re
from pathlib import Path
from typing import List, Optional

class RegexParser:
    def can_parse(self, file_path: str, language: Optional[str]) -> bool:
        return True
        
    def parse(self, file_path: str, language: Optional[str]) -> List[any]:
        from .cascade import ParsedChunk
        chunks = []
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            language_name = (language or self._language_from_path(file_path) or "").lower()
            if language_name in ("", "python") or Path(file_path).suffix.lower() == ".py":
                chunks.extend(self._parse_python(content, ParsedChunk))
            return chunks
        except Exception:
            raise

    @staticmethod
    def _language_from_path(file_path: str) -> Optional[str]:
        return {".py": "python"}.get(Path(file_path).suffix.lower())

    def _parse_python(self, content: str, parsed_chunk_type) -> list[object]:
        lines = content.splitlines()
        chunks = []
        pattern = re.compile(r"^(?P<indent>\s*)(?:async\s+def|def|class)\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)")
        for index, line in enumerate(lines):
            match = pattern.match(line)
            if not match:
                continue
            indent = len(match.group("indent"))
            end_index = self._find_python_block_end(lines, index, indent)
            block = "\n".join(lines[index:end_index])
            kind = "class" if line.lstrip().startswith("class ") else "function"
            chunks.append(
                parsed_chunk_type(
                    block,
                    "L-3",
                    {"parser": "regex", "name": match.group("name")},
                    symbol_name=match.group("name"),
                    line_start=index + 1,
                    line_end=end_index,
                    kind=kind,
                    tier=3,
                )
            )
        return chunks

    @staticmethod
    def _find_python_block_end(lines: list[str], start_index: int, indent: int) -> int:
        end_index = start_index + 1
        for index in range(start_index + 1, len(lines)):
            line = lines[index]
            if not line.strip():
                end_index = index + 1
                continue
            current_indent = len(line) - len(line.lstrip())
            if current_indent <= indent:
                break
            end_index = index + 1
        return end_index

class SlidingWindowParser:
    def __init__(self, window_size: int = 200, overlap: int = 50):
        if window_size <= 0:
            raise ValueError("window_size must be positive")
        if overlap < 0:
            raise ValueError("overlap must be non-negative")
        if overlap >= window_size:
            raise ValueError("overlap must be smaller than window_size")
        self.window_size = window_size
        self.overlap = overlap

    def can_parse(self, file_path: str, language: Optional[str]) -> bool:
        return True
        
    def parse(self, file_path: str, language: Optional[str]) -> List[any]:
        from .cascade import ParsedChunk
        chunks = []
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                
            if not content:
                return []
                
            i = 0
            while i < len(content):
                chunk_text = content[i:i + self.window_size]
                chunks.append(
                    ParsedChunk(
                        chunk_text,
                        "L-4",
                        {"parser": "sliding-window"},
                        line_start=content.count("\n", 0, i) + 1,
                        line_end=content.count("\n", 0, min(i + self.window_size, len(content))) + 1,
                        kind="chunk",
                        tier=3,
                    )
                )
                i += (self.window_size - self.overlap)
                if i >= len(content) and len(chunk_text) < self.window_size:
                    break
            return chunks
        except Exception:
            raise
