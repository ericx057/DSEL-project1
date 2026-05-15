import os
import pytest
from UMMDB.summarizer.hooks import EmbeddingHook, LLMHook

def test_embedding_hook_mock():
    # Force mock
    hook = EmbeddingHook(mock=True)
    embeddings = hook.get_embeddings(["text1", "text2"])
    assert len(embeddings) == 2
    assert embeddings[0] == [0.1, 0.2, 0.3]

def test_embedding_hook_empty():
    hook = EmbeddingHook(mock=True)
    assert hook.get_embeddings([]) == []

def test_embedding_hook_fallback(monkeypatch):
    monkeypatch.setattr(os, "environ", {})
    def mock_from_pretrained(*args, **kwargs):
        raise Exception("Failed to load")
    
    import transformers
    monkeypatch.setattr(transformers.AutoTokenizer, "from_pretrained", mock_from_pretrained)
    
    hook = EmbeddingHook(mock=False)
    assert hook.mock is True
    
    embeddings = hook.get_embeddings(["test"])
    assert embeddings == [[0.1, 0.2, 0.3]]

def test_embedding_hook_exception_in_call(monkeypatch):
    class MockModel:
        def __call__(self, *args, **kwargs):
            raise Exception("Forward fail")
            
    hook = EmbeddingHook(mock=False)
    # forcefully set mock=False to bypass initial checks, 
    # but we will fail during get_embeddings
    hook.mock = False
    hook.tokenizer = lambda *args, **kwargs: {}
    hook.model = MockModel()
    
    embeddings = hook.get_embeddings(["test"])
    assert embeddings == [[0.1, 0.2, 0.3]]

def test_llm_hook_mock():
    hook = LLMHook(mock=True)
    summary = hook.summarize("This is a long text to summarize")
    assert summary.startswith("Summary of: ")

def test_llm_hook_empty():
    hook = LLMHook(mock=True)
    assert hook.summarize("") == ""

def test_llm_hook_fallback(monkeypatch):
    monkeypatch.setattr(os, "environ", {})
    def mock_from_pretrained(*args, **kwargs):
        raise Exception("Failed to load")
    
    import transformers
    monkeypatch.setattr(transformers.AutoTokenizer, "from_pretrained", mock_from_pretrained)
    
    hook = LLMHook(mock=False)
    assert hook.mock is True
    
    summary = hook.summarize("test")
    assert summary.startswith("Summary of: ")

def test_llm_hook_exception_in_call(monkeypatch):
    class MockModel:
        def generate(self, *args, **kwargs):
            raise Exception("Generate fail")
            
    hook = LLMHook(mock=False)
    hook.mock = False
    hook.tokenizer = lambda *args, **kwargs: {}
    hook.model = MockModel()
    
    summary = hook.summarize("test")
    assert summary.startswith("Summary of: ")
