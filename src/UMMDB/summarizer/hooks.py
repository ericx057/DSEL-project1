import os
from typing import List, Dict, Any

class EmbeddingHook:
    def __init__(self, model_name: str = "nomic-ai/nomic-embed-text-v1.5", mock: bool = False):
        self.model_name = model_name
        self.mock = mock
        self.tokenizer = None
        self.model = None
        
        if not self.mock and not os.environ.get("UMMDB_MOCK_MODELS"):
            try:
                from transformers import AutoTokenizer, AutoModel
                self.tokenizer = AutoTokenizer.from_pretrained(model_name)
                self.model = AutoModel.from_pretrained(model_name, trust_remote_code=True)
            except Exception:
                # Fallback gracefully
                self.mock = True

    def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
            
        if self.mock:
            return [[0.1, 0.2, 0.3] for _ in texts]
            
        try:
            import torch
            inputs = self.tokenizer(texts, padding=True, truncation=True, return_tensors="pt")
            with torch.no_grad():
                outputs = self.model(**inputs)
            embeddings = outputs.last_hidden_state.mean(dim=1)
            return embeddings.tolist()
        except Exception:
            return [[0.1, 0.2, 0.3] for _ in texts]

class LLMHook:
    def __init__(self, model_name: str = "gpt2", mock: bool = False):
        self.model_name = model_name
        self.mock = mock
        self.tokenizer = None
        self.model = None
        
        if not self.mock and not os.environ.get("UMMDB_MOCK_MODELS"):
            try:
                from transformers import AutoTokenizer, AutoModelForCausalLM
                self.tokenizer = AutoTokenizer.from_pretrained(model_name)
                self.model = AutoModelForCausalLM.from_pretrained(model_name)
            except Exception:
                self.mock = True

    def summarize(self, text: str) -> str:
        if not text:
            return ""
            
        if self.mock:
            return f"Summary of: {text[:20]}..."
            
        try:
            import torch
            inputs = self.tokenizer(text, return_tensors="pt", max_length=512, truncation=True)
            with torch.no_grad():
                outputs = self.model.generate(**inputs, max_new_tokens=50)
            return self.tokenizer.decode(outputs[0], skip_special_tokens=True)
        except Exception:
            return f"Summary of: {text[:20]}..."
