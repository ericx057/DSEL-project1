import os
from typing import List, Dict, Any

try:
    from transformers import AutoModel, AutoModelForCausalLM, AutoTokenizer
except Exception:
    AutoModel = None
    AutoModelForCausalLM = None
    AutoTokenizer = None

class EmbeddingHook:
    def __init__(
        self,
        model_name: str = "nomic-ai/nomic-embed-text-v1.5",
        mock: bool = False,
        trust_remote_code: bool = False,
    ):
        self.model_name = model_name
        self.mock = mock
        self.tokenizer = None
        self.model = None
        
        if not self.mock and not os.environ.get("UMMDB_MOCK_MODELS"):
            try:
                if AutoTokenizer is None or AutoModel is None:
                    raise ImportError("transformers is not available")
                self.tokenizer = AutoTokenizer.from_pretrained(model_name, local_files_only=True)
                self.model = AutoModel.from_pretrained(
                    model_name,
                    trust_remote_code=trust_remote_code,
                    local_files_only=True,
                )
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
                if AutoTokenizer is None or AutoModelForCausalLM is None:
                    raise ImportError("transformers is not available")
                self.tokenizer = AutoTokenizer.from_pretrained(model_name, local_files_only=True)
                self.model = AutoModelForCausalLM.from_pretrained(model_name, local_files_only=True)
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
