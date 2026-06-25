from src.retrieval import embedding_config
from src.retrieval.database import HashingEmbeddingProvider


def test_default_embedding_settings_use_prefixed_nomic_model(monkeypatch):
    for name in (
        "CIS_EMBEDDING_BACKEND",
        "CIS_EMBEDDING_MODEL",
        "CIS_EMBEDDING_TRUST_REMOTE_CODE",
        "CIS_EMBEDDING_LOCAL_FILES_ONLY",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = embedding_config.EmbeddingSettings.from_env()

    assert settings.backend == "nomic"
    assert settings.model_name == embedding_config.DEFAULT_NOMIC_MODEL
    assert settings.trust_remote_code is True


def test_build_embedding_provider_uses_nomic_factory_for_default_model(monkeypatch):
    calls = []

    def fake_nomic_provider(*, local_files_only):
        calls.append(local_files_only)
        return "nomic-provider"

    monkeypatch.setattr(embedding_config, "make_nomic_provider", fake_nomic_provider)

    provider = embedding_config.build_embedding_provider(
        embedding_config.EmbeddingSettings(
            backend="nomic",
            model_name=embedding_config.DEFAULT_NOMIC_MODEL,
        )
    )

    assert provider == "nomic-provider"
    assert calls == [False]


def test_hashing_provider_requires_explicit_backend():
    provider = embedding_config.build_embedding_provider(
        embedding_config.EmbeddingSettings(backend="hashing")
    )

    assert isinstance(provider, HashingEmbeddingProvider)
