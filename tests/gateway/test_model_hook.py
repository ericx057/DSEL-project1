import pytest

from src.gateway.model_hook import LlamaCppCompletionClient, ModelHook
from src.gateway.services import CircuitBreaker


class RecordingEngineClient:
    def __init__(self, chunks=None):
        self.prompts = []
        self.chunks = chunks or ["chunk1", "chunk2"]

    async def text_generation(self, prompt: str, **kwargs):
        self.prompts.append(prompt)
        for chunk in self.chunks:
            yield chunk


@pytest.mark.asyncio
async def test_model_hook_streams_from_inference_engine_without_model_prompt_template():
    cb = CircuitBreaker()
    client = RecordingEngineClient()
    hook = ModelHook(inference_engine_id="engine-under-test", circuit_breaker=cb, client=client)
    
    chunks = []
    async for chunk in hook.generate_stream("test prompt"):
        chunks.append(chunk)
        
    assert chunks == ["chunk1", "chunk2"]
    assert client.prompts == ["test prompt"]
    assert hook.inference_engine_id == "engine-under-test"
    assert not hasattr(hook, "model_id")
    assert cb.failure_count == 0

@pytest.mark.asyncio
async def test_model_hook_failure():
    cb = CircuitBreaker(failure_threshold=1)
    hook = ModelHook(circuit_breaker=cb, client=RecordingEngineClient())
    
    async def mock_text_generation_error(*args, **kwargs):
        raise ValueError("Simulated backend Error")
        yield "" 
        
    hook.client.text_generation = mock_text_generation_error
    
    chunks = []
    async for chunk in hook.generate_stream("test prompt"):
        chunks.append(chunk)
        
    assert chunks == ["\n[Inference Error: local inference engine unavailable]"]
    assert cb.state == "OPEN"


@pytest.mark.asyncio
async def test_model_hook_skips_backend_when_circuit_breaker_is_open():
    cb = CircuitBreaker(failure_threshold=1)
    cb.record_failure()
    client = RecordingEngineClient()
    hook = ModelHook(circuit_breaker=cb, client=client)

    chunks = []
    async for chunk in hook.generate_stream("test prompt"):
        chunks.append(chunk)

    assert chunks == ["\n[Inference Error: local inference engine unavailable]"]
    assert client.prompts == []


@pytest.mark.asyncio
async def test_llamacpp_completion_client_posts_to_native_completion_endpoint_without_model(monkeypatch):
    requests = []

    class MockStreamResponse:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

        def raise_for_status(self):
            pass

        async def aiter_lines(self):
            yield '{"content": "Hello", "stop": false}'
            yield '{"content": " world", "stop": true}'

    class MockAsyncClient:
        def __init__(self, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

        def stream(self, method, url, json):
            requests.append({"method": method, "url": url, "json": json})
            return MockStreamResponse()

    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", MockAsyncClient)

    client = LlamaCppCompletionClient(base_url="http://engine.local")
    chunks = []
    async for chunk in client.text_generation("raw prompt", max_new_tokens=128):
        chunks.append(chunk)

    assert chunks == ["Hello", " world"]
    assert requests == [
        {
            "method": "POST",
            "url": "http://engine.local/completion",
            "json": {"prompt": "raw prompt", "stream": True, "n_predict": 128, "cache_prompt": True},
        }
    ]
