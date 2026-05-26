import pytest

from inference.llamacpp import LlamaCppEndpointConfig, LlamaCppServerSettings


def test_llamacpp_endpoint_config_uses_native_completion_and_health_endpoints():
    config = LlamaCppEndpointConfig(base_url="http://llamacpp:8080/")

    assert config.completion_url == "http://llamacpp:8080/completion"
    assert config.health_url == "http://llamacpp:8080/health"


@pytest.mark.parametrize(
    ("precision", "cache_type"),
    [
        ("fp16", "f16"),
        ("fp8", "q8_0"),
        ("fp4", "q4_0"),
    ],
)
def test_server_settings_maps_precision_toggle_to_llamacpp_cache_types(precision, cache_type):
    settings = LlamaCppServerSettings(precision=precision, vram_gb=6, system_ram_gb=64)

    assert settings.cache_type_k == cache_type
    assert settings.cache_type_v == cache_type
    assert settings.kv_offload is True
    assert settings.n_gpu_layers == "auto"
    assert settings.to_llama_env()["LLAMA_ARG_KV_OFFLOAD"] == "true"


def test_server_settings_rejects_unknown_precision():
    with pytest.raises(ValueError, match="precision"):
        LlamaCppServerSettings(precision="q5")


def test_server_settings_resolves_precision_specific_model_path_without_quantizing():
    settings = LlamaCppServerSettings(precision="fp8")

    model_path = settings.resolve_model_path(
        {
            "CIS_LLAMA_CPP_MODEL_PATH": "/models/fallback.gguf",
            "CIS_LLAMA_CPP_MODEL_FP8": "/models/runtime-fp8.gguf",
        }
    )

    assert model_path == "/models/runtime-fp8.gguf"


def test_server_settings_exposes_custom_context_window():
    settings = LlamaCppServerSettings(context_window=8192)

    assert settings.context_window == 8192
    assert settings.to_llama_env()["LLAMA_ARG_CTX_SIZE"] == "8192"


def test_server_settings_reads_custom_context_window_from_env():
    settings = LlamaCppServerSettings.from_env({"CIS_LLAMA_CPP_CONTEXT_WINDOW": "12288"})

    assert settings.context_window == 12288
    assert settings.to_llama_env()["LLAMA_ARG_CTX_SIZE"] == "12288"


def test_server_settings_keeps_ctx_size_as_compatibility_alias():
    settings = LlamaCppServerSettings.from_env({"CIS_LLAMA_CPP_CTX_SIZE": "6144"})

    assert settings.context_window == 6144
    assert settings.to_llama_env()["LLAMA_ARG_CTX_SIZE"] == "6144"


def test_server_settings_rejects_non_positive_context_window():
    with pytest.raises(ValueError, match="context_window"):
        LlamaCppServerSettings(context_window=0)
