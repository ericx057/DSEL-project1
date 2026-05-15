import tempfile
import os
from src.UMMDB.parser.tree_sitter import TreeSitterParser
import src.UMMDB.parser.tree_sitter as ts_module

def test_tree_sitter_can_parse(monkeypatch):
    monkeypatch.setattr(ts_module, 'HAS_TREE_SITTER', True)
    parser = TreeSitterParser()
    assert parser.can_parse("test.py", "python") is True
    assert parser.can_parse("test.js", None) is True
    assert parser.can_parse("test.txt", None) is False

def test_tree_sitter_no_library(monkeypatch):
    monkeypatch.setattr(ts_module, 'HAS_TREE_SITTER', False)
    parser = TreeSitterParser()
    assert parser.can_parse("test.py", "python") is False

def test_tree_sitter_parse(monkeypatch):
    monkeypatch.setattr(ts_module, 'HAS_TREE_SITTER', True)
    parser = TreeSitterParser()
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', delete=False) as f:
        f.write("def foo():\n    pass")
        f.close()
        chunks = parser.parse(f.name, "python")
        assert len(chunks) == 1
        assert chunks[0].fidelity == "L-1"
        assert chunks[0].content == "def foo():\n    pass"
        os.unlink(f.name)
