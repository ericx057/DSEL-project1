from typing import List, Dict, Any

try:
    from sentence_transformers import CrossEncoder
except ImportError:
    CrossEncoder = None

class Reranker:
    def __init__(self, use_mock: bool = False):
        self.use_mock = use_mock
        if not use_mock:
            if CrossEncoder is None:
                raise ImportError("sentence-transformers is required for Reranker")
            self.model = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")

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
