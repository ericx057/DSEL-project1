import os
from typing import List, Optional
from UMMDB.parser.heuristics import FileHeuristics

class ParseResult:
    def __init__(self, success: bool, method: str, tokens: List[str]):
        self.success = success
        self.method = method
        self.tokens = tokens

class LanguageDetector:
    EXTENSIONS = {
        ".py": "python",
        ".js": "javascript",
        ".ts": "typescript",
        ".java": "java",
        ".c": "c",
        ".cpp": "cpp",
        ".rs": "rust",
        ".go": "go",
    }
    
    def detect(self, filename: str) -> str:
        _, ext = os.path.splitext(filename)
        return self.EXTENSIONS.get(ext.lower(), "unknown")

class TreeSitterParser:
    def parse(self, content: str, language: str) -> ParseResult:
        # Mocking tree-sitter success condition: fails for "unknown" language
        if language == "unknown":
            return ParseResult(False, "tree-sitter", [])
        return ParseResult(True, "tree-sitter", ["mock_ast_node"])

class LexerFallback:
    def parse(self, content: str, language: str) -> ParseResult:
        # Mocking lexer fallback
        if language == "unknown" and not content:
            return ParseResult(False, "lexer", [])
        return ParseResult(True, "lexer", ["mock_lexer_token"])

class NaiveTokenWindow:
    def parse(self, content: str, language: str) -> ParseResult:
        tokens = content.split()
        return ParseResult(True, "naive", tokens)

class CascadingParser:
    def __init__(self):
        self.detector = LanguageDetector()
        self.tree_sitter = TreeSitterParser()
        self.lexer = LexerFallback()
        self.naive = NaiveTokenWindow()

    def parse_file(self, filename: str, content: str) -> ParseResult:
        if not FileHeuristics.is_human_readable(content):
            return ParseResult(False, "skipped_heuristics", [])

        language = self.detector.detect(filename)
        
        ts_result = self.tree_sitter.parse(content, language)
        if ts_result.success:
            return ts_result
            
        lexer_result = self.lexer.parse(content, language)
        if lexer_result.success:
            return lexer_result
            
        return self.naive.parse(content, language)
