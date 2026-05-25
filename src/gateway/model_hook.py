from __future__ import annotations

import json
import logging
import os
import time
from typing import AsyncGenerator, Optional

import httpx

from src.gateway.services import CircuitBreaker

logger = logging.getLogger(__name__)


class OllamaTextGenerationClient:
    def __init__(
        self,
        model: str = "qwen2.5-coder:7b",
        base_url: str = "http://127.0.0.1:11434",
        timeout_seconds: float = 60.0,
        max_stream_seconds: float = 300.0,
    ):
        self.model = os.environ.get("CIS_OLLAMA_MODEL", model)
        self.base_url = os.environ.get("CIS_OLLAMA_BASE_URL", base_url).rstrip("/")
        self.timeout_seconds = float(os.environ.get("CIS_OLLAMA_TIMEOUT_SECONDS", timeout_seconds))
        self.max_stream_seconds = float(os.environ.get("CIS_OLLAMA_MAX_STREAM_SECONDS", max_stream_seconds))

    async def text_generation(
        self,
        prompt: str,
        max_new_tokens: int = 512,
        stream: bool = True,
        details: bool = False,
    ) -> AsyncGenerator[str, None]:
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": stream,
            "options": {"num_predict": max_new_tokens, "temperature": 0.1},
        }
        timeout = httpx.Timeout(
            timeout=self.timeout_seconds,
            connect=min(10.0, self.timeout_seconds),
            pool=min(10.0, self.timeout_seconds),
        )
        started_at = time.monotonic()
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream("POST", f"{self.base_url}/api/generate", json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if time.monotonic() - started_at > self.max_stream_seconds:
                        raise TimeoutError("Ollama stream exceeded maximum duration")
                    if not line:
                        continue
                    data = json.loads(line)
                    token = data.get("response", "")
                    if token:
                        yield token
                    if data.get("done"):
                        break


class ModelHook:
    def __init__(
        self,
        model_id: str = "qwen2.5-coder:7b",
        circuit_breaker: Optional[CircuitBreaker] = None,
        client: Optional[OllamaTextGenerationClient] = None,
    ):
        self.model_id = model_id
        self.client = client or OllamaTextGenerationClient(model=model_id)
        self.circuit_breaker = circuit_breaker

    async def generate_stream(self, prompt: str) -> AsyncGenerator[str, None]:
        try:
            formatted_prompt = f"<|im_start|>user\n{prompt}<|im_end|>\n<|im_start|>assistant\n"
            async for chunk in self.client.text_generation(
                formatted_prompt,
                max_new_tokens=512,
                stream=True,
                details=False,
            ):
                yield chunk
            if self.circuit_breaker:
                self.circuit_breaker.record_success()
        except Exception as exc:
            if self.circuit_breaker:
                self.circuit_breaker.record_failure()
            logger.exception("Local inference request failed")
            yield "\n[Inference Error: local inference engine unavailable]"
