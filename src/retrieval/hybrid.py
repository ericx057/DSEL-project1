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
        # Filename shortlist: directly fetch artifacts for any named source file.
        # This bypasses the embedding scan and dramatically improves recall when
        # the query explicitly names files (e.g. "service.py", "widget.hpp").
        fn_res = (
            self.store.filename_search(query, user_tier, repo_scope)
            if hasattr(self.store, "filename_search")
            else []
        )
        lex_res = (
            self.store.lexical_search(query, user_tier, repo_scope, top_k=max(self.vector_top_k, 20))
            if hasattr(self.store, "lexical_search")
            else []
        )

        if self.lambda_ratio == 1.0:
            v_res = self.store.vector_search(query, user_tier, repo_scope, self.vector_top_k)
        elif self.lambda_ratio == 0.0:
            v_res = []
        else:
            v_res = self.store.vector_search(query, user_tier, repo_scope, self.vector_top_k)

        g_res = (
            []
            if self.lambda_ratio == 1.0
            else self.store.graph_search(query, user_tier, repo_scope, self.graph_depth, self.graph_breadth)
        )

        results: List[Dict[str, Any]] = []
        seen: set = set()
        # Filename hits first (highest precision), then vector/graph blend.
        vector_slots = max(1, int(len(v_res) * self.lambda_ratio)) if v_res else 0
        ordered_candidates = fn_res + v_res[:vector_slots] + lex_res + g_res + v_res[vector_slots:]
        for doc in ordered_candidates:
            if doc["id"] not in seen:
                seen.add(doc["id"])
                results.append(doc)
        return results
