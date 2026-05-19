from abc import ABC, abstractmethod
import json
import httpx

class InferenceRuntime(ABC):
    @abstractmethod
    def generate_stream(self, prompt: str, model: str):
        pass

class OllamaRuntime(InferenceRuntime):
    def __init__(self, base_url: str = "http://localhost:11434"):
        self.base_url = base_url

    def generate_stream(self, prompt: str, model: str):
        with httpx.stream("POST", f"{self.base_url}/api/generate", json={"prompt": prompt, "model": model}) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if line:
                    data = json.loads(line)
                    yield data.get("response", "")
                    if data.get("done"):
                        break

class MockRuntime(InferenceRuntime):
    def __init__(self, responses: list[str] = None):
        self.responses = responses or ["Mock", " response", " stream."]
        
    def generate_stream(self, prompt: str, model: str):
        for token in self.responses:
            yield token
