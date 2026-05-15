from typing import List, Dict, Any

class PromptAssembler:
    def __init__(self, system_rule: str = None):
        self.system_rule = system_rule

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
            parts.append("Context:")
            ordered_chunks = self._u_shape_order(chunks)
            for chunk in ordered_chunks:
                fp = chunk.get("file_path")
                lang = chunk.get("language")
                tier = chunk.get("tier")
                text = chunk.get("text", "")
                parts.append(f"--- File: {fp} | Language: {lang} | Tier: {tier} ---")
                parts.append(text)
                
        parts.append(f"Query: {query}")
        return "\n".join(parts)
