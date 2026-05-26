import json

from inference.runtime import LlamaCppRuntime, MockRuntime, decode_stream_line


def test_mock_runtime():
    runtime = MockRuntime(["A", "B"])

    assert list(runtime.generate_stream("prompt")) == ["A", "B"]


def test_mock_runtime_default():
    runtime = MockRuntime()

    assert list(runtime.generate_stream("prompt")) == ["Mock", " response", " stream."]


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


def test_llamacpp_runtime_posts_prompt_to_native_completion_endpoint_without_model(monkeypatch):
    import httpx

    requests = []
    lines = [
        json.dumps({"content": "Hello", "stop": False}),
        "",
        json.dumps({"content": " World", "stop": True}),
    ]

    def mock_stream(method, url, json, timeout=None):
        requests.append({"method": method, "url": url, "json": json, "timeout": timeout})
        return MockResponse(lines)

    monkeypatch.setattr(httpx, "stream", mock_stream)

    runtime = LlamaCppRuntime(base_url="http://engine.local")

    assert list(runtime.generate_stream("prompt")) == ["Hello", " World"]
    assert len(requests) == 1
    assert requests[0]["method"] == "POST"
    assert requests[0]["url"] == "http://engine.local/completion"
    assert requests[0]["json"] == {"prompt": "prompt", "stream": True, "cache_prompt": True}
    assert isinstance(requests[0]["timeout"], httpx.Timeout)


def test_llamacpp_runtime_applies_configured_timeout(monkeypatch):
    import httpx

    requests = []

    def mock_stream(method, url, json, timeout=None):
        requests.append({"method": method, "url": url, "json": json, "timeout": timeout})
        return MockResponse([json_module.dumps({"content": "done", "stop": True})])

    json_module = json
    monkeypatch.setattr(httpx, "stream", mock_stream)

    runtime = LlamaCppRuntime(base_url="http://engine.local", timeout_seconds=17.0)

    assert list(runtime.generate_stream("prompt")) == ["done"]
    assert isinstance(requests[0]["timeout"], httpx.Timeout)
    assert requests[0]["timeout"].connect == 10.0


def test_decode_stream_line_handles_llamacpp_native_content():
    token, done = decode_stream_line('data: {"content":"part","stop":false}')

    assert token == "part"
    assert done is False


def test_decode_stream_line_handles_openai_compatible_completion_choice():
    token, done = decode_stream_line(
        'data: {"choices":[{"text":"part","finish_reason":"stop"}]}'
    )

    assert token == "part"
    assert done is True
