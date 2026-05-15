import pytest
from retrieval.assembler import PromptAssembler

def test_u_shape_order():
    assembler = PromptAssembler()
    chunks = [
        {"id": "1", "score": 0.9},
        {"id": "2", "score": 0.8},
        {"id": "3", "score": 0.7},
        {"id": "4", "score": 0.6},
        {"id": "5", "score": 0.5},
    ]
    ordered = assembler._u_shape_order(chunks)
    ids = [c["id"] for c in ordered]
    assert ids == ["1", "3", "5", "4", "2"]

def test_u_shape_order_even():
    assembler = PromptAssembler()
    chunks = [
        {"id": "1", "score": 0.9},
        {"id": "2", "score": 0.8},
        {"id": "3", "score": 0.7},
        {"id": "4", "score": 0.6},
    ]
    ordered = assembler._u_shape_order(chunks)
    ids = [c["id"] for c in ordered]
    assert ids == ["1", "3", "4", "2"]

def test_assemble_prompt():
    assembler = PromptAssembler("System rule.")
    chunks = [
        {"id": "1", "text": "Content 1", "file_path": "a.py", "language": "python", "tier": 0},
        {"id": "2", "text": "Content 2", "file_path": "b.py", "language": "python", "tier": 1},
    ]
    prompt = assembler.assemble("How to do X?", chunks)
    
    assert "System rule." in prompt
    assert "--- File: a.py | Language: python | Tier: 0 ---" in prompt
    assert "Content 1" in prompt
    assert "--- File: b.py | Language: python | Tier: 1 ---" in prompt
    assert "Content 2" in prompt
    assert "Query: How to do X?" in prompt

def test_assemble_empty_chunks():
    assembler = PromptAssembler()
    prompt = assembler.assemble("Query?", [])
    assert "Context:" not in prompt
    assert "Query: Query?" in prompt
