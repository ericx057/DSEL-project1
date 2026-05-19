import pytest
from inference.runtime import OllamaRuntime, MockRuntime

def test_mock_runtime():
    runtime = MockRuntime(["A", "B"])
    res = list(runtime.generate_stream("prompt", "7b"))
    assert res == ["A", "B"]

def test_mock_runtime_default():
    runtime = MockRuntime()
    res = list(runtime.generate_stream("prompt", "7b"))
    assert res == ["Mock", " response", " stream."]

class MockResponse:
    def __init__(self, lines):
        self.lines = lines
    def iter_lines(self):
        return self.lines
    def raise_for_status(self):
        pass
    def __enter__(self):
        return self
    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

def test_ollama_runtime(monkeypatch):
    import httpx
    import json
    
    lines = [
        json.dumps({"response": "Hello", "done": False}),
        "",
        json.dumps({"response": " World", "done": True})
    ]
    
    def mock_stream(*args, **kwargs):
        return MockResponse(lines)
    
    monkeypatch.setattr(httpx, "stream", mock_stream)
    
    runtime = OllamaRuntime()
    res = list(runtime.generate_stream("prompt", "7b"))
    assert res == ["Hello", " World"]
