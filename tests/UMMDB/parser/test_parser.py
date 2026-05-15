import pytest
from unittest.mock import patch, MagicMock
from UMMDB.parser.parser import (
    CascadingParser, LanguageDetector, TreeSitterParser,
    LexerFallback, NaiveTokenWindow, ParseResult
)

def test_language_detector():
    detector = LanguageDetector()
    assert detector.detect("some_file.py") == "python"
    assert detector.detect("some_file.js") == "javascript"
    assert detector.detect("unknown_file") == "unknown"

def test_tree_sitter_success():
    parser = TreeSitterParser()
    result = parser.parse("def test(): pass", "python")
    assert result.success is True
    assert result.method == "tree-sitter"

def test_tree_sitter_failure():
    parser = TreeSitterParser()
    # Mocking failure for unknown language
    result = parser.parse("def test(): pass", "unknown")
    assert result.success is False

def test_lexer_fallback_success():
    lexer = LexerFallback()
    result = lexer.parse("code", "python")
    assert result.success is True
    assert result.method == "lexer"

def test_lexer_fallback_failure():
    lexer = LexerFallback()
    result = lexer.parse("", "unknown")
    assert result.success is False
    assert result.method == "lexer"

def test_naive_token_window():
    naive = NaiveTokenWindow()
    result = naive.parse("some code here", "unknown")
    assert result.success is True
    assert result.method == "naive"
    assert result.tokens == ["some", "code", "here"]

@patch("UMMDB.parser.heuristics.FileHeuristics.is_human_readable")
def test_cascading_parser_unparseable(mock_human_readable):
    mock_human_readable.return_value = False
    parser = CascadingParser()
    result = parser.parse_file("file.py", "content")
    assert result.success is False
    assert result.method == "skipped_heuristics"

@patch("UMMDB.parser.heuristics.FileHeuristics.is_human_readable")
def test_cascading_parser_tree_sitter_success(mock_human_readable):
    mock_human_readable.return_value = True
    parser = CascadingParser()
    
    with patch.object(parser.tree_sitter, 'parse', return_value=ParseResult(True, "tree-sitter", [])):
        result = parser.parse_file("file.py", "content")
        assert result.success is True
        assert result.method == "tree-sitter"

@patch("UMMDB.parser.heuristics.FileHeuristics.is_human_readable")
def test_cascading_parser_lexer_fallback(mock_human_readable):
    mock_human_readable.return_value = True
    parser = CascadingParser()
    
    with patch.object(parser.tree_sitter, 'parse', return_value=ParseResult(False, "tree-sitter", [])), \
         patch.object(parser.lexer, 'parse', return_value=ParseResult(True, "lexer", [])):
        
        result = parser.parse_file("file.py", "content")
        assert result.success is True
        assert result.method == "lexer"

@patch("UMMDB.parser.heuristics.FileHeuristics.is_human_readable")
def test_cascading_parser_naive_fallback(mock_human_readable):
    mock_human_readable.return_value = True
    parser = CascadingParser()
    
    with patch.object(parser.tree_sitter, 'parse', return_value=ParseResult(False, "tree-sitter", [])), \
         patch.object(parser.lexer, 'parse', return_value=ParseResult(False, "lexer", [])):
        
        result = parser.parse_file("file.py", "content")
        assert result.success is True
        assert result.method == "naive"
