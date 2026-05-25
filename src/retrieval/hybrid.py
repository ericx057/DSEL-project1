from typing import Any, Dict, List, Optional, Sequence
from .database import UnifiedStore

class HybridSearcher:
    def __init__(
        self,
        store: UnifiedStore,
        lambda_ratio: float = 0.5,
        vector_top_k: int = 20,
        graph_depth: int = 3,
        graph_breadth: int = 50,
    ):
        if not 0.0 <= lambda_ratio <= 1.0:
            raise ValueError("lambda_ratio must be between 0 and 1")
        self.store = store
        self.lambda_ratio = lambda_ratio
        self.vector_top_k = vector_top_k
        self.graph_depth = graph_depth
        self.graph_breadth = graph_breadth
        
    def search(
        self,
        query: str,
        user_tier: int,
        repo_scope: Optional[Sequence[str]] = None,
    ) -> List[Dict[str, Any]]:
        if self.lambda_ratio == 1.0:
            return self.store.vector_search(query, user_tier, repo_scope, self.vector_top_k)
        elif self.lambda_ratio == 0.0:
            return self.store.graph_search(query, user_tier, repo_scope, self.graph_depth, self.graph_breadth)
        else:
            v_res = self.store.vector_search(query, user_tier, repo_scope, self.vector_top_k)
            g_res = self.store.graph_search(query, user_tier, repo_scope, self.graph_depth, self.graph_breadth)
            results = []
            seen = set()
            vector_slots = max(1, int(len(v_res) * self.lambda_ratio))
            ordered_candidates = v_res[:vector_slots] + g_res + v_res[vector_slots:]
            for doc in ordered_candidates:
                if doc["id"] not in seen:
                    seen.add(doc["id"])
                    results.append(doc)
            return results
