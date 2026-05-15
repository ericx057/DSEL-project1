import os
import tempfile
import subprocess
from src.UMMDB.parser.ctags import CtagsParser

def test_ctags_can_parse_with_ctags(monkeypatch):
    def mock_run(*args, **kwargs):
        pass
    monkeypatch.setattr(subprocess, 'run', mock_run)
    parser = CtagsParser()
    assert parser.can_parse("test.py", None) is True

def test_ctags_can_parse_no_ctags(monkeypatch):
    def mock_run(*args, **kwargs):
        raise FileNotFoundError()
    monkeypatch.setattr(subprocess, 'run', mock_run)
    parser = CtagsParser()
    assert parser.can_parse("test.py", None) is False

def test_ctags_parse_success(monkeypatch):
    class MockResult:
        stdout = "symbol1\nsymbol2\n"
    
    def mock_run(*args, **kwargs):
        return MockResult()
    monkeypatch.setattr(subprocess, 'run', mock_run)
    
    parser = CtagsParser()
    chunks = parser.parse("dummy.py", None)
    assert len(chunks) == 2
    assert chunks[0].content == "symbol1"
    assert chunks[0].fidelity == "L-2"

def test_ctags_parse_fallback(monkeypatch):
    class MockResult:
        stdout = "\n" # empty or blank
        
    def mock_run(*args, **kwargs):
        return MockResult()
    monkeypatch.setattr(subprocess, 'run', mock_run)
    
    parser = CtagsParser()
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', delete=False) as f:
        f.write("some code here")
        f.close()
        chunks = parser.parse(f.name, None)
        assert len(chunks) == 1
        assert chunks[0].fidelity == "L-2"
        assert chunks[0].content == "some code here"
        os.unlink(f.name)

def test_ctags_parse_exception(monkeypatch):
    def mock_run(*args, **kwargs):
        raise Exception("Failed")
    monkeypatch.setattr(subprocess, 'run', mock_run)
    
    parser = CtagsParser()
    try:
        parser.parse("dummy.py", None)
        assert False, "Should raise exception"
    except Exception:
        pass
