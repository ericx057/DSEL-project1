from typing import List, Dict, Any

from src.retrieval.context_summary import RetrievedContextSummarizer

class PromptAssembler:
    def __init__(self, system_rule: str = None, summarizer: RetrievedContextSummarizer | None = None):
        self.system_rule = system_rule
        self.summarizer = summarizer or RetrievedContextSummarizer()

    def _u_shape_order(self, chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        left = []
        right = []
        for i, chunk in enumerate(chunks):
            if i % 2 == 0:
                left.append(chunk)
            else:
                right.append(chunk)
        return left + right[::-1]

    def assemble(self, query: str, chunks: List[Dict[str, Any]]) -> str:
        parts = []
        if self.system_rule:
            parts.append(self.system_rule)
            
        if chunks:
            ordered_chunks = self._u_shape_order(chunks)
            parts.append("Retrieved summaries:")
            parts.append(self.summarizer.summarize_chunks(ordered_chunks))
                
        parts.append(f"Query: {query}")
        return "\n".join(parts)
