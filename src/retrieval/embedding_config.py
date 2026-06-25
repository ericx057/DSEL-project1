from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping, Optional

from src.retrieval.database import HashingEmbeddingProvider
from src.retrieval.embeddings import (
    LocalTransformersEmbeddingProvider,
    SentenceTransformersProvider,
    make_nomic_provider,
)


DEFAULT_NOMIC_MODEL = "nomic-ai/nomic-embed-text-v1.5"
DEFAULT_SENTENCE_TRANSFORMERS_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
STRONG_SENTENCE_TRANSFORMERS_MODEL = "BAAI/bge-large-en-v1.5"


@dataclass(frozen=True)
class EmbeddingSettings:
    backend: str = "nomic"
    model_name: str = DEFAULT_NOMIC_MODEL
    trust_remote_code: bool = True
    local_files_only: bool = False
    batch_size: int = 64

    @classmethod
    def from_env(cls, env: Optional[Mapping[str, str]] = None) -> "EmbeddingSettings":
        values = env if env is not None else os.environ
        backend = values.get("CIS_EMBEDDING_BACKEND", "nomic").strip().lower()
        model_name = values.get("CIS_EMBEDDING_MODEL") or cls._default_model_for_backend(backend)
        return cls(
            backend=backend,
            model_name=model_name,
            trust_remote_code=_bool_env(values, "CIS_EMBEDDING_TRUST_REMOTE_CODE", True),
            local_files_only=_bool_env(values, "CIS_EMBEDDING_LOCAL_FILES_ONLY", False),
            batch_size=_int_env(values, "CIS_EMBEDDING_BATCH_SIZE", 64),
        )

    @staticmethod
    def _default_model_for_backend(backend: str) -> str:
        if backend in {"sentence_transformers", "sentence-transformers", "minilm"}:
            return DEFAULT_SENTENCE_TRANSFORMERS_MODEL
        return DEFAULT_NOMIC_MODEL


def build_embedding_provider(settings: Optional[EmbeddingSettings] = None):
    resolved = settings or EmbeddingSettings.from_env()
    backend = resolved.backend
    if backend == "hashing":
        return HashingEmbeddingProvider()
    if backend in {"sentence_transformers", "sentence-transformers", "minilm"}:
        return SentenceTransformersProvider(
            model_name=resolved.model_name,
            batch_size=resolved.batch_size,
        )
    if backend == "nomic" and resolved.model_name == DEFAULT_NOMIC_MODEL:
        return make_nomic_provider(local_files_only=resolved.local_files_only)
    return LocalTransformersEmbeddingProvider(
        model_name=resolved.model_name,
        trust_remote_code=resolved.trust_remote_code,
        local_files_only=resolved.local_files_only,
    )


def _bool_env(values: Mapping[str, str], name: str, default: bool) -> bool:
    raw = values.get(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _int_env(values: Mapping[str, str], name: str, default: int) -> int:
    raw = values.get(name)
    if raw is None or raw.strip() == "":
        return default
    return int(raw)
