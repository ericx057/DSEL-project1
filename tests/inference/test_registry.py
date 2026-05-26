from inference.registry import InferenceEngineRegistry


def test_inference_engine_registry_returns_llamacpp_completion_endpoint_only():
    registry = InferenceEngineRegistry(
        base_url="http://llamacpp:8080/",
        engine_id="llama.cpp",
    )

    endpoint = registry.get_engine_endpoint()

    assert endpoint.url == "http://llamacpp:8080/completion"
    assert endpoint.health_url == "http://llamacpp:8080/health"
    assert endpoint.engine_id == "llama.cpp"
    assert not hasattr(registry, "get_available_models")
    assert not hasattr(registry, "get_model_for_task")


def test_inference_engine_registry_rejects_blank_llamacpp_base_url():
    registry = InferenceEngineRegistry(base_url="")

    try:
        registry.get_engine_endpoint()
        assert False
    except ValueError as exc:
        assert "llama.cpp base url" in str(exc).lower()
