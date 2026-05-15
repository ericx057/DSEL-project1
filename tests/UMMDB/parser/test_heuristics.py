import pytest
from UMMDB.parser.heuristics import FileHeuristics

def test_is_human_readable_normal_file():
    content = "def test_function():\n    pass\n"
    assert FileHeuristics.is_human_readable(content) is True

def test_is_human_readable_long_lines():
    content = "a" * 1000 + "\n" + "b" * 1000
    assert FileHeuristics.is_human_readable(content) is False

def test_is_human_readable_high_entropy():
    # Simulated high entropy / minified content
    content = "".join([chr(i) for i in range(256)]) * 10
    # Assuming this might fail or pass depending on implementation, let's keep it simple for now
    assert FileHeuristics.is_human_readable(content) is False

def test_is_human_readable_empty():
    assert FileHeuristics.is_human_readable("") is True
    assert FileHeuristics.is_human_readable(None) is True

def test_is_human_readable_only_newlines():
    assert FileHeuristics.is_human_readable("\n\n\n") is True

def test_calculate_entropy_empty():
    assert FileHeuristics.calculate_entropy("") == 0.0
    assert FileHeuristics.calculate_entropy(None) == 0.0
