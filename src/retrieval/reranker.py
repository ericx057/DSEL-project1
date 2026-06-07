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

    @staticmethod
    def _symbol_standalone(sym: str, query_lower: str) -> bool:
        """True if sym appears as a whole token in query_lower — not as a :: prefix or .ext suffix."""
        pattern = r"(?<![:\w])" + re.escape(sym) + r"(?![:\w.])"
        return bool(re.search(pattern, query_lower))

    def rerank(self, query: str, chunks: List[Dict[str, Any]], top_m: int = 8) -> List[Dict[str, Any]]:
        query_terms = self._terms(query)
        query_lower = query.lower()
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
            exact_symbol_score = 0
            for sym in symbol_candidates:
                if not sym:
                    continue
                if "::" in sym:
                    # Qualified names match if they appear verbatim anywhere in query.
                    if sym in query_lower:
                        exact_symbol_score = max(exact_symbol_score, 6)
                else:
                    # Simple names must appear as a standalone token (not as a :: qualifier prefix).
                    if self._symbol_standalone(sym, query_lower):
                        exact_symbol_score = max(exact_symbol_score, 4)

            file_path = str(chunk.get("file_path") or "").lower()
            file_basename = file_path.split("/")[-1] if file_path else ""
            file_stem = file_basename.rsplit(".", 1)[0] if "." in file_basename else file_basename
            file_score = (
                8 if file_path and file_path in query_lower
                else 5 if file_basename and file_basename in query_lower
                else 3 if file_stem and len(file_stem) > 3 and file_stem.lower() in query_lower
                else 0
            )
            # Prefer implementation files over headers when scores are otherwise equal.
            impl_bonus = 1 if file_basename.endswith((".cpp", ".c", ".py")) else 0

            score = overlap_score + exact_symbol_score + file_score + impl_bonus
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
