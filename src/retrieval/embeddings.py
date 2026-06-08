from __future__ import annotations

import math
from typing import Iterable, List, Protocol


class EmbeddingProvider(Protocol):
    def embed(self, text: str) -> List[float]:
        ...

    def embed_many(self, texts: Iterable[str]) -> List[List[float]]:
        ...


def _best_device():
    try:
        import torch
        if torch.backends.mps.is_available():
            return "mps"
        if torch.cuda.is_available():
            return "cuda"
    except Exception:
        pass
    return "cpu"


class LocalTransformersEmbeddingProvider:
    """Raw HuggingFace transformers backend.

    Supports nomic-embed-text-v1.5 task prefixes:
      - queries get  "search_query: <text>"
      - documents get "search_document: <text>"
    Pass query_prefix / doc_prefix to override.
    """

    def __init__(
        self,
        model_name: str = "nomic-ai/nomic-embed-text-v1.5",
        trust_remote_code: bool = True,
        local_files_only: bool = False,
        query_prefix: str = "",
        doc_prefix: str = "",
        device: str | None = None,
    ):
        try:
            import torch
            from transformers import AutoModel, AutoTokenizer
        except Exception as exc:
            raise RuntimeError("transformers and torch are required for local embeddings") from exc

        self._torch = torch
        self._query_prefix = query_prefix
        self._doc_prefix   = doc_prefix
        self._device       = device or _best_device()

        self.tokenizer = AutoTokenizer.from_pretrained(
            model_name, local_files_only=local_files_only,
        )
        self.model = AutoModel.from_pretrained(
            model_name,
            trust_remote_code=trust_remote_code,
            local_files_only=local_files_only,
        ).to(self._device)
        self.model.eval()

    def embed(self, text: str) -> List[float]:
        return self.embed_query(text)

    def embed_query(self, text: str) -> List[float]:
        return self._encode([self._query_prefix + text])[0]

    def embed_doc(self, text: str) -> List[float]:
        return self._encode([self._doc_prefix + text])[0]

    def embed_many(self, texts: Iterable[str]) -> List[List[float]]:
        return self._encode([self._doc_prefix + t for t in texts])

    def _encode(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        inputs = self.tokenizer(
            texts, padding=True, truncation=True, return_tensors="pt"
        )
        inputs = {k: v.to(self._device) for k, v in inputs.items()}
        with self._torch.no_grad():
            outputs = self.model(**inputs)
        embeddings = outputs.last_hidden_state.mean(dim=1).cpu().tolist()
        return [self._normalize(v) for v in embeddings]

    @staticmethod
    def _normalize(vector: List[float]) -> List[float]:
        norm = math.sqrt(sum(v * v for v in vector))
        if norm == 0:
            return vector
        return [v / norm for v in vector]


def make_nomic_provider(local_files_only: bool = False) -> LocalTransformersEmbeddingProvider:
    """nomic-embed-text-v1.5 with the recommended task prefixes."""
    return LocalTransformersEmbeddingProvider(
        model_name="nomic-ai/nomic-embed-text-v1.5",
        trust_remote_code=True,
        local_files_only=local_files_only,
        query_prefix="search_query: ",
        doc_prefix="search_document: ",
    )


class SentenceTransformersProvider:
    """sentence-transformers backend — simpler API, good out-of-the-box quality.

    Defaults to all-MiniLM-L6-v2 (384 dims, fast CPU/MPS, already cached).
    """

    def __init__(
        self,
        model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
        device: str | None = None,
        batch_size: int = 64,
    ):
        try:
            from sentence_transformers import SentenceTransformer
        except Exception as exc:
            raise RuntimeError("sentence-transformers is required") from exc

        self._device     = device or _best_device()
        self._batch_size = batch_size
        self._model      = SentenceTransformer(model_name, device=self._device)

    def embed(self, text: str) -> List[float]:
        return self.embed_many([text])[0]

    def embed_many(self, texts: Iterable[str]) -> List[List[float]]:
        values = list(texts)
        if not values:
            return []
        vecs = self._model.encode(
            values,
            batch_size=self._batch_size,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return [v.tolist() for v in vecs]
