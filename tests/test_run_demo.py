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

    assert "For `summary: What does RepositoryIndexer do?`, the indexed context is too thin for a behavioral answer." in answer
    assert "RepositoryIndexer is a Python class." in answer
    assert "only identifies the class" in answer
    assert "does not show methods or behavior" in answer
    assert "src/ingestion/indexer.py" not in answer
    assert "class RepositoryIndexer:" not in answer
    assert "src/gateway/main.py" not in answer
    assert "external inference server" not in answer


def test_local_demo_completion_client_turns_summary_hits_into_takeaways():
    prompt = "\n".join(
        [
            "You are a read-only codebase intelligence assistant.",
            "Retrieved summaries:",
            "[1] CheckoutService (class, typescript, lines 1-5) - Mentions CheckoutService, authorize, validate.",
            "[2] buildReceipt (function, typescript, lines 7-9) - Mentions buildReceipt, formatReceipt.",
            "Query: How does checkout authorization work?",
        ]
    )
    client = LocalDemoCompletionClient(max_context_files=2)

    answer = client.create_response(prompt)

    assert "For `How does checkout authorization work?`, the useful retrieved signals are:" in answer
    assert "CheckoutService is a TypeScript class tied to authorize and validate." in answer
    assert "buildReceipt is a TypeScript function tied to formatReceipt." in answer
    assert "Most relevant evidence" not in answer


def test_local_demo_inference_is_default_unless_llamacpp_is_requested(monkeypatch):
    monkeypatch.delenv("CIS_LOCAL_USE_LLAMA_CPP", raising=False)
    assert should_use_local_demo_inference()

    monkeypatch.setenv("CIS_LOCAL_USE_LLAMA_CPP", "true")
    assert not should_use_local_demo_inference()
