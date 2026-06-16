from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
import os

@dataclass(frozen=True)
class ParsedChunk:
    content: str
    fidelity: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    symbol_name: Optional[str] = None
    line_start: int = 1
    line_end: int = 1
    kind: str = "chunk"
    tier: int = 3
    calls: Tuple[str, ...] = ()
    inherits: Tuple[str, ...] = ()

class BaseParser:
    def can_parse(self, file_path: str, language: Optional[str]) -> bool:
        return False
        
    def parse(self, file_path: str, language: Optional[str]) -> List[ParsedChunk]:
        return []

from .python_ast import PythonAstParser
from .cpp import CppSignatureParser
from .generic_symbols import GenericSymbolParser
from .tree_sitter import TreeSitterParser
from .ctags import CtagsParser
from .fallback import RegexParser, SlidingWindowParser

class CascadingParser(BaseParser):
    def __init__(self):
        self.parsers = [
            PythonAstParser(),
            CppSignatureParser(),
            GenericSymbolParser(),
            TreeSitterParser(),
            CtagsParser(),
            RegexParser(),
            SlidingWindowParser()
        ]

    def can_parse(self, file_path: str, language: Optional[str]) -> bool:
        return True # The cascade always tries something

    def parse(self, file_path: str, language: Optional[str] = None) -> List[ParsedChunk]:
        if not os.path.exists(file_path):
            return []
        fallback_chunks: List[ParsedChunk] = []
        for parser in self.parsers:
            if parser.can_parse(file_path, language):
                try:
                    chunks = parser.parse(file_path, language)
                    if chunks and self._has_symbol_chunks(chunks):
                        return chunks
                    if chunks and not fallback_chunks:
                        fallback_chunks = chunks
                except Exception:
                    continue # Fallback to next parser
        return fallback_chunks

    @staticmethod
    def _has_symbol_chunks(chunks: List[ParsedChunk]) -> bool:
        symbol_kinds = {"class", "function", "method"}
        return any(chunk.tier == 1 and chunk.kind in symbol_kinds for chunk in chunks)
