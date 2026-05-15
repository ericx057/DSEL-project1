from abc import ABC, abstractmethod
from typing import List, Dict, Any

class UnifiedStore(ABC):
    @abstractmethod
    def vector_search(self, query: str, user_tier: int) -> List[Dict[str, Any]]:
        pass
        
    @abstractmethod
    def graph_search(self, query: str, user_tier: int) -> List[Dict[str, Any]]:
        pass

class InMemoryUnifiedStore(UnifiedStore):
    def __init__(self, data: List[Dict[str, Any]]):
        self.data = data
        
    def vector_search(self, query: str, user_tier: int) -> List[Dict[str, Any]]:
        return [doc for doc in self.data if doc.get("tier", 0) <= user_tier]
        
    def graph_search(self, query: str, user_tier: int) -> List[Dict[str, Any]]:
        return [doc for doc in self.data if doc.get("tier", 0) <= user_tier]
