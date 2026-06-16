import pytest

from run_demo import LocalDemoCompletionClient, should_use_local_demo_inference


@pytest.mark.asyncio
async def test_local_demo_completion_client_summarizes_retrieved_context():
    prompt = "\n".join(
        [
            "You are a read-only codebase intelligence assistant.",
            "Context:",
            "--- File: src/ingestion/indexer.py | Language: python | Tier: 1 ---",
            "class RepositoryIndexer:",
            "    pass",
            "--- File: src/gateway/main.py | Language: python | Tier: 1 ---",
            "def create_app():",
            "    pass",
            "Query: summary: What does RepositoryIndexer do?",
        ]
    )
    client = LocalDemoCompletionClient(max_context_files=1)

    chunks = [chunk async for chunk in client.text_generation(prompt)]
    answer = "".join(chunks)

    assert "I found relevant indexed context for: summary: What does RepositoryIndexer do?" in answer
    assert "Most relevant evidence:" in answer
    assert "RepositoryIndexer" in answer
    assert "RepositoryIndexer is a class in python" in answer
    assert "src/ingestion/indexer.py" not in answer
    assert "class RepositoryIndexer:" not in answer
    assert "src/gateway/main.py" not in answer
    assert "external inference server" not in answer


def test_local_demo_inference_is_default_unless_llamacpp_is_requested(monkeypatch):
    monkeypatch.delenv("CIS_LOCAL_USE_LLAMA_CPP", raising=False)
    assert should_use_local_demo_inference()

    monkeypatch.setenv("CIS_LOCAL_USE_LLAMA_CPP", "true")
    assert not should_use_local_demo_inference()
