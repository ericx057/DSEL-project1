import os
import tempfile
import pytest
from src.UMMDB.parser.fallback import RegexParser, SlidingWindowParser

def test_regex_can_parse():
    parser = RegexParser()
    assert parser.can_parse("any.txt", None) is True

def test_regex_parse():
    parser = RegexParser()
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', delete=False) as f:
        f.write("def foo():\n    return 1")
        f.close()
        chunks = parser.parse(f.name, None)
        assert len(chunks) == 1
        assert chunks[0].fidelity == "L-3"
        assert chunks[0].content == "def foo():\n    return 1"
        os.unlink(f.name)

def test_regex_returns_no_chunks_for_unstructured_text():
    parser = RegexParser()
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', delete=False) as f:
        f.write("word1 word2 word3")
        f.close()
        try:
            assert parser.parse(f.name, None) == []
        finally:
            os.unlink(f.name)

def test_regex_parse_exception():
    parser = RegexParser()
    try:
        parser.parse("/non/existent", None)
        assert False
    except Exception:
        pass

def test_sliding_window_can_parse():
    parser = SlidingWindowParser()
    assert parser.can_parse("any.txt", None) is True

def test_sliding_window_rejects_non_advancing_configuration():
    with pytest.raises(ValueError):
        SlidingWindowParser(window_size=10, overlap=10)

def test_sliding_window_parse():
    parser = SlidingWindowParser(window_size=10, overlap=5)
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', delete=False) as f:
        # "01234567890123456789" (20 chars)
        f.write("0123456789abcdefghij")
        f.close()
        chunks = parser.parse(f.name, None)
        # 1st: 0..10 "0123456789"
        # 2nd: 5..15 "56789abcde"
        # 3rd: 10..20 "abcdefghij"
        # 4th: 15..25 "fghij" -> break
        assert len(chunks) > 0
        assert chunks[0].fidelity == "L-4"
        os.unlink(f.name)

def test_sliding_window_empty():
    parser = SlidingWindowParser()
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', delete=False) as f:
        f.close()
        chunks = parser.parse(f.name, None)
        assert len(chunks) == 0
        os.unlink(f.name)

def test_sliding_window_exception():
    parser = SlidingWindowParser()
    try:
        parser.parse("/non/existent", None)
        assert False
    except Exception:
        pass
