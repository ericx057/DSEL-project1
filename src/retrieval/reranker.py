import re
from typing import List, Dict, Any

_UNLOADED = object()
CrossEncoder = _UNLOADED


def _load_cross_encoder():
    global CrossEncoder
    if CrossEncoder is _UNLOADED:
        try:
            from sentence_transformers import CrossEncoder as LoadedCrossEncoder
            CrossEncoder = LoadedCrossEncoder
        except ImportError:
            CrossEncoder = None
    if CrossEncoder is None:
        raise ImportError("sentence-transformers is required for Reranker")
    return CrossEncoder

class Reranker:
    def __init__(self, use_mock: bool = False):
        self.use_mock = use_mock
        if not use_mock:
            cross_encoder = _load_cross_encoder()
            self.model = cross_encoder(
                "cross-encoder/ms-marco-MiniLM-L-6-v2",
                automodel_args={"local_files_only": True},
                tokenizer_args={"local_files_only": True},
            )

    def rerank(self, query: str, chunks: List[Dict[str, Any]], top_m: int = 5) -> List[Dict[str, Any]]:
        if not chunks:
            return []
            
        scored_chunks = []
        if self.use_mock:
            query_words = query.lower().split()
            for chunk in chunks:
                score = sum(1 for word in query_words if word in chunk.get("text", "").lower())
                chunk_copy = chunk.copy()
                chunk_copy["rerank_score"] = float(score)
                scored_chunks.append(chunk_copy)
        else:
            pairs = [[query, chunk.get("text", "")] for chunk in chunks]
            scores = self.model.predict(pairs)
            for chunk, score in zip(chunks, scores):
                chunk_copy = chunk.copy()
                chunk_copy["rerank_score"] = float(score)
                scored_chunks.append(chunk_copy)
                
        scored_chunks.sort(key=lambda x: x["rerank_score"], reverse=True)
        return scored_chunks[:top_m]


class LexicalReranker:
    STOPWORDS = {
        "a",
        "an",
        "and",
        "are",
        "artifact",
        "as",
        "at",
        "be",
        "by",
        "callee",
        "confirm",
        "contains",
        "correspond",
        "defined",
        "does",
        "file",
        "for",
        "from",
        "in",
        "indexed",
        "is",
        "it",
        "kind",
        "kinds",
        "of",
        "on",
        "or",
        "public",
        "repository",
        "symbol",
        "the",
        "to",
        "what",
        "where",
        "which",
        "with",
    }

    def rerank(self, query: str, chunks: List[Dict[str, Any]], top_m: int = 8) -> List[Dict[str, Any]]:
        query_terms = self._terms(query)
        scored_chunks = []
        for chunk in chunks:
            metadata = chunk.get("metadata") or {}
            metadata_text = " ".join(str(value) for value in metadata.values())
            searchable = " ".join(
                str(chunk.get(field, "")) for field in ("id", "symbol_name", "file_path", "kind", "text")
            ).lower()
            searchable = f"{searchable} {metadata_text.lower()}"
            searchable_terms = self._terms(searchable, keep_stopwords=True)
            overlap_score = len(query_terms & searchable_terms)
            symbol_candidates = [
                str(chunk.get("symbol_name") or "").lower(),
                str(metadata.get("qualified_name") or "").lower(),
                str(chunk.get("id") or "").lower(),
            ]
            file_path = str(chunk.get("file_path") or "").lower()
            kind = str(chunk.get("kind") or "").lower()
            tier = int(chunk.get("tier") or 0)
            query_lower = query.lower()
            exact_symbol_score = max((4 if symbol and symbol in query_lower else 0) for symbol in symbol_candidates)
            file_score = 2 if file_path and file_path in query_lower else 0
            exact_kind_score = 4 if kind and kind in query_lower else 0
            interface_score = (
                2
                if tier == 1
                and kind in {"class", "function", "method"}
                and "implementation" not in query_lower
                else 0
            )
            score = overlap_score + exact_symbol_score + file_score + exact_kind_score + interface_score
            chunk_copy = chunk.copy()
            chunk_copy["rerank_score"] = float(score)
            scored_chunks.append(chunk_copy)
        scored_chunks.sort(key=lambda item: (item["rerank_score"], item.get("score", 0.0)), reverse=True)
        return scored_chunks[:top_m]

    @classmethod
    def _terms(cls, text: str, keep_stopwords: bool = False) -> set[str]:
        terms = {
            token.lower()
            for token in re.findall(r"[A-Za-z_][A-Za-z0-9_.-]*|[A-Za-z0-9_.-]+", text)
            if token.strip()
        }
        if keep_stopwords:
            return terms
        return {term for term in terms if term not in cls.STOPWORDS}
