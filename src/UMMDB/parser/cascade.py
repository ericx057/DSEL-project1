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
from .tree_sitter import TreeSitterParser
from .ctags import CtagsParser
from .fallback import RegexParser, SlidingWindowParser

class CascadingParser(BaseParser):
    def __init__(self):
        self.parsers = [
            PythonAstParser(),
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
            
        for parser in self.parsers:
            if parser.can_parse(file_path, language):
                try:
                    chunks = parser.parse(file_path, language)
                    if chunks:
                        return chunks
                except Exception:
                    continue # Fallback to next parser
        return []
