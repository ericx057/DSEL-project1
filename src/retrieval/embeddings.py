from __future__ import annotations

import math
from typing import Iterable, List, Protocol


class EmbeddingProvider(Protocol):
    def embed(self, text: str) -> List[float]:
        ...

    def embed_many(self, texts: Iterable[str]) -> List[List[float]]:
        ...


class LocalTransformersEmbeddingProvider:
    def __init__(self, model_name: str = "nomic-ai/nomic-embed-text-v1.5", trust_remote_code: bool = False):
        try:
            import torch
            from transformers import AutoModel, AutoTokenizer
        except Exception as exc:
            raise RuntimeError("transformers and torch are required for local embeddings") from exc

        self._torch = torch
        self.tokenizer = AutoTokenizer.from_pretrained(model_name, local_files_only=True)
        self.model = AutoModel.from_pretrained(
            model_name,
            trust_remote_code=trust_remote_code,
            local_files_only=True,
        )
        self.model.eval()

    def embed(self, text: str) -> List[float]:
        return self.embed_many([text])[0]

    def embed_many(self, texts: Iterable[str]) -> List[List[float]]:
        values = list(texts)
        if not values:
            return []
        inputs = self.tokenizer(values, padding=True, truncation=True, return_tensors="pt")
        with self._torch.no_grad():
            outputs = self.model(**inputs)
        embeddings = outputs.last_hidden_state.mean(dim=1).tolist()
        return [self._normalize(vector) for vector in embeddings]

    @staticmethod
    def _normalize(vector: List[float]) -> List[float]:
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            return vector
        return [value / norm for value in vector]
