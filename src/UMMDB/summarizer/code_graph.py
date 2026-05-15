import networkx as nx
from typing import List, Tuple, Dict, Any

class CodeGraph:
    def __init__(self):
        self.graph = nx.DiGraph()

    def add_node(self, node_id: str, metadata: Dict[str, Any] = None):
        self.graph.add_node(node_id, **(metadata or {}))

    def add_edge(self, source: str, target: str, relationship: str):
        self.graph.add_edge(source, target, type=relationship)

    def calculate_centrality(self) -> Dict[str, float]:
        if self.graph.number_of_nodes() == 0:
            return {}
        
        return nx.betweenness_centrality(self.graph)

    def get_top_percentile_nodes(self, percentile: float = 0.8) -> List[str]:
        centrality = self.calculate_centrality()
        if not centrality:
            return []
            
        scores = list(centrality.values())
        scores.sort()
        index = int(len(scores) * percentile)
        if index >= len(scores):
            index = len(scores) - 1
            
        threshold = scores[index]
        
        # Return nodes that score >= threshold
        return [node for node, score in centrality.items() if score >= threshold]
