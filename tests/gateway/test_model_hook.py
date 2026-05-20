import pytest
from unittest.mock import AsyncMock, patch
from src.gateway.model_hook import ModelHook
from src.gateway.services import CircuitBreaker

@pytest.mark.asyncio
async def test_model_hook_success():
    cb = CircuitBreaker()
    hook = ModelHook(circuit_breaker=cb)
    
    # Mock the text_generation to yield chunks
    async def mock_text_generation(*args, **kwargs):
        yield "chunk1"
        yield "chunk2"
        
    hook.client.text_generation = mock_text_generation
    
    chunks = []
    async for chunk in hook.generate_stream("test prompt"):
        chunks.append(chunk)
        
    assert chunks == ["chunk1", "chunk2"]
    assert cb.failure_count == 0

@pytest.mark.asyncio
async def test_model_hook_failure():
    cb = CircuitBreaker(failure_threshold=1)
    hook = ModelHook(circuit_breaker=cb)
    
    # Mock text_generation to raise an error
    async def mock_text_generation_error(*args, **kwargs):
        raise ValueError("Simulated HuggingFace Error")
        # Generator needs to yield something or just raise
        yield "" 
        
    hook.client.text_generation = mock_text_generation_error
    
    chunks = []
    async for chunk in hook.generate_stream("test prompt"):
        chunks.append(chunk)
        
    assert "Inference Error: Simulated HuggingFace Error" in chunks[0]
    assert cb.state == "OPEN"
