import os
import importlib
from pathlib import Path
from typing import List, Optional
try:
    import tree_sitter
    HAS_TREE_SITTER = True
except ImportError:
    HAS_TREE_SITTER = False

LANGUAGE_MODULES = {
    "python": "tree_sitter_python",
    "javascript": "tree_sitter_javascript",
    "typescript": "tree_sitter_typescript",
    "go": "tree_sitter_go",
    "rust": "tree_sitter_rust",
    "c": "tree_sitter_c",
    "cpp": "tree_sitter_cpp",
}

EXTENSION_LANGUAGES = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".go": "go",
    ".rs": "rust",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".hpp": "cpp",
}

class TreeSitterParser:
    def __init__(self):
        self._language_cache = {}

    def can_parse(self, file_path: str, language: Optional[str]) -> bool:
        if not HAS_TREE_SITTER:
            return False
        return self._load_language(self._resolve_language(file_path, language)) is not None
        
    def parse(self, file_path: str, language: Optional[str]) -> List[any]:
        from .cascade import ParsedChunk

        language_name = self._resolve_language(file_path, language)
        language_object = self._load_language(language_name)
        if language_object is None:
            return []

        content = Path(file_path).read_text(encoding='utf-8')
        parser = tree_sitter.Parser()
        try:
            parser.language = language_object
        except AttributeError:
            parser.set_language(language_object)
        tree = parser.parse(content.encode("utf-8"))
        if tree.root_node.has_error:
            return []

        return [
            ParsedChunk(
                content,
                "L-1",
                {
                    "parser": "tree-sitter",
                    "language": language_name,
                    "root_type": tree.root_node.type,
                },
                symbol_name=Path(file_path).name,
                line_start=1,
                line_end=max(1, content.count("\n") + 1),
                kind="module",
                tier=2,
            )
        ]

    @staticmethod
    def _resolve_language(file_path: str, language: Optional[str]) -> Optional[str]:
        if language:
            return language.lower()
        return EXTENSION_LANGUAGES.get(Path(file_path).suffix.lower())

    def _load_language(self, language: Optional[str]):
        if not language or language not in LANGUAGE_MODULES:
            return None
        if language in self._language_cache:
            return self._language_cache[language]
        try:
            module = importlib.import_module(LANGUAGE_MODULES[language])
            raw_language = module.language()
            try:
                language_object = tree_sitter.Language(raw_language)
            except TypeError:
                language_object = raw_language
        except Exception:
            language_object = None
        self._language_cache[language] = language_object
        return language_object
