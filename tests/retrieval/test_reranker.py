import pytest
from unittest.mock import patch, MagicMock
from retrieval.reranker import Reranker

def test_reranker_mock_scoring():
    reranker = Reranker(use_mock=True)
    chunks = [
        {"id": "1", "text": "This is a random document about apples."},
        {"id": "2", "text": "This document specifically mentions the query keyword."},
        {"id": "3", "text": "Nothing to see here."}
    ]
    query = "query keyword"
    
    top_chunks = reranker.rerank(query, chunks, top_m=2)
    assert len(top_chunks) == 2
    assert top_chunks[0]["id"] == "2" # Has both "query" and "keyword"
    assert "rerank_score" in top_chunks[0]
    assert top_chunks[0]["rerank_score"] > 0

def test_reranker_empty_chunks():
    reranker = Reranker(use_mock=True)
    assert reranker.rerank("query", []) == []

@patch("retrieval.reranker.CrossEncoder")
def test_reranker_real_scoring(MockCrossEncoder):
    # Setup mock
    mock_model = MagicMock()
    # Predict returns high score for the second document
    mock_model.predict.return_value = [0.1, 0.9, 0.2]
    MockCrossEncoder.return_value = mock_model
    
    reranker = Reranker(use_mock=False)
    
    chunks = [
        {"id": "1", "text": "bad match"},
        {"id": "2", "text": "good match"},
        {"id": "3", "text": "okay match"}
    ]
    query = "match"
    
    top_chunks = reranker.rerank(query, chunks, top_m=2)
    assert len(top_chunks) == 2
    assert top_chunks[0]["id"] == "2"
    assert top_chunks[0]["rerank_score"] == 0.9
    assert top_chunks[1]["id"] == "3"
    assert top_chunks[1]["rerank_score"] == 0.2

@patch("retrieval.reranker.CrossEncoder", None)
def test_reranker_missing_library():
    with pytest.raises(ImportError):
        Reranker(use_mock=False)
