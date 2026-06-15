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
        {
            "id": "1",
            "text": "def save_document():\n    write_objects()",
            "file_path": "src/app/a.py",
            "language": "python",
            "tier": 0,
            "symbol_name": "save_document",
            "kind": "function",
        },
        {
            "id": "2",
            "text": "class RepositoryIndexer:\n    pass",
            "file_path": "src/app/b.py",
            "language": "python",
            "tier": 1,
            "symbol_name": "RepositoryIndexer",
            "kind": "class",
        },
    ]
    prompt = assembler.assemble("How to do X?", chunks)
    
    assert "System rule." in prompt
    assert "Retrieved summaries:" in prompt
    assert "--- File:" not in prompt
    assert "src/app/a.py" not in prompt
    assert "def save_document()" not in prompt
    assert "class RepositoryIndexer:" not in prompt
    assert "save_document" in prompt
    assert "RepositoryIndexer" in prompt
    assert "Query: How to do X?" in prompt

def test_assemble_empty_chunks():
    assembler = PromptAssembler()
    prompt = assembler.assemble("Query?", [])
    assert "Context:" not in prompt
    assert "Query: Query?" in prompt
