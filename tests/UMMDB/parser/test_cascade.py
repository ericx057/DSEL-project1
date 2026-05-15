import os
import tempfile
from src.UMMDB.parser.cascade import CascadingParser, BaseParser, ParsedChunk

class MockParser(BaseParser):
    def __init__(self, can_parse_val=True, throw=False, chunks=None):
        self.can_parse_val = can_parse_val
        self.throw = throw
        self.chunks = chunks or []

    def can_parse(self, file_path, language):
        return self.can_parse_val

    def parse(self, file_path, language):
        if self.throw:
            raise Exception("Mock error")
        return self.chunks

def test_cascade_no_file():
    parser = CascadingParser()
    assert parser.parse("/non/existent/path") == []

def test_cascade_fallback():
    cascade = CascadingParser()
    cascade.parsers = [
        MockParser(can_parse_val=False),
        MockParser(throw=True),
        MockParser(chunks=[ParsedChunk("content", "L-3")])
    ]
    
    with tempfile.NamedTemporaryFile(delete=False) as f:
        f.close()
        chunks = cascade.parse(f.name)
        assert len(chunks) == 1
        assert chunks[0].fidelity == "L-3"
        os.unlink(f.name)

def test_base_parser():
    base = BaseParser()
    assert base.can_parse("file.py", "python") is False
    assert base.parse("file.py", "python") == []
