from typing import List, Dict, Any
from retrieval.database import UnifiedStore

class HybridSearcher:
    def __init__(self, store: UnifiedStore, lambda_ratio: float = 0.5):
        self.store = store
        self.lambda_ratio = lambda_ratio
        
    def search(self, query: str, user_tier: int) -> List[Dict[str, Any]]:
        if self.lambda_ratio == 1.0:
            return self.store.vector_search(query, user_tier)
        elif self.lambda_ratio == 0.0:
            return self.store.graph_search(query, user_tier)
        else:
            v_res = self.store.vector_search(query, user_tier)
            g_res = self.store.graph_search(query, user_tier)
            results = []
            seen = set()
            for doc in v_res + g_res:
                if doc["id"] not in seen:
                    seen.add(doc["id"])
                    results.append(doc)
            return results
