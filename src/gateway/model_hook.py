import asyncio
from typing import AsyncGenerator, Optional
from huggingface_hub import AsyncInferenceClient
from src.gateway.services import CircuitBreaker

class ModelHook:
    def __init__(self, model_id: str = "Qwen/Qwen2.5-Coder-7B-Instruct", circuit_breaker: Optional[CircuitBreaker] = None):
        self.client = AsyncInferenceClient(model=model_id)
        self.circuit_breaker = circuit_breaker

    async def generate_stream(self, prompt: str) -> AsyncGenerator[str, None]:
        """
        Simulates streaming inference from the Hugging Face model hook.
        Updates the circuit breaker on failures.
        """
        try:
            # Format prompt for the Instruct model
            formatted_prompt = f"<|im_start|>user\n{prompt}<|im_end|>\n<|im_start|>assistant\n"
            
            async for chunk in self.client.text_generation(
                formatted_prompt, 
                max_new_tokens=512, 
                stream=True, 
                details=False
            ):
                yield chunk
                
            if self.circuit_breaker:
                self.circuit_breaker.record_success()
                
        except Exception as e:
            if self.circuit_breaker:
                self.circuit_breaker.record_failure()
            # In a real scenario, we might want to log this or raise a specific domain exception.
            # For the model hook mock, we'll yield an error message so the stream doesn't fail silently.
            yield f"\n[Inference Error: {str(e)}]"
