from __future__ import annotations

import logging
import os
import time
from typing import AsyncGenerator, Optional, Protocol

import httpx

from src.gateway.services import CircuitBreaker
from src.inference.llamacpp import LlamaCppEndpointConfig
from src.inference.runtime import decode_stream_line

logger = logging.getLogger(__name__)


class TextGenerationClient(Protocol):
    async def text_generation(
        self,
        prompt: str,
        max_new_tokens: int = 512,
        stream: bool = True,
        details: bool = False,
    ) -> AsyncGenerator[str, None]:
        pass


class LlamaCppCompletionClient:
    def __init__(
        self,
        base_url: Optional[str] = None,
        endpoint_url: Optional[str] = None,
        timeout_seconds: float = 60.0,
        max_stream_seconds: float = 300.0,
    ):
        if endpoint_url is not None:
            self.endpoint_url = endpoint_url
        else:
            configured_base_url = base_url or os.environ.get("CIS_LLAMA_CPP_BASE_URL", LlamaCppEndpointConfig.base_url)
            self.endpoint_url = LlamaCppEndpointConfig(base_url=configured_base_url).completion_url
        self.timeout_seconds = float(os.environ.get("CIS_INFERENCE_TIMEOUT_SECONDS", timeout_seconds))
        self.max_stream_seconds = float(os.environ.get("CIS_INFERENCE_MAX_STREAM_SECONDS", max_stream_seconds))

    async def text_generation(
        self,
        prompt: str,
        max_new_tokens: int = 512,
        stream: bool = True,
        details: bool = False,
    ) -> AsyncGenerator[str, None]:
        endpoint_url = self.endpoint_url.strip()
        if not endpoint_url:
            raise ValueError("Inference engine endpoint is not configured")
        payload = {"prompt": prompt, "stream": stream, "n_predict": max_new_tokens, "cache_prompt": True}
        timeout = httpx.Timeout(
            timeout=self.timeout_seconds,
            connect=min(10.0, self.timeout_seconds),
            pool=min(10.0, self.timeout_seconds),
        )
        started_at = time.monotonic()
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream("POST", endpoint_url, json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if time.monotonic() - started_at > self.max_stream_seconds:
                        raise TimeoutError("Inference engine stream exceeded maximum duration")
                    token, done = decode_stream_line(line)
                    if token:
                        yield token
                    if done:
                        break


HttpInferenceEngineClient = LlamaCppCompletionClient


class ModelHook:
    def __init__(
        self,
        inference_engine_id: str = "llama.cpp",
        endpoint_url: Optional[str] = None,
        circuit_breaker: Optional[CircuitBreaker] = None,
        client: Optional[TextGenerationClient] = None,
    ):
        self.inference_engine_id = os.environ.get("CIS_INFERENCE_ENGINE_ID", inference_engine_id)
        self.client = client or LlamaCppCompletionClient(endpoint_url=endpoint_url)
        self.circuit_breaker = circuit_breaker

    async def generate_stream(self, prompt: str) -> AsyncGenerator[str, None]:
        try:
            async for chunk in self.client.text_generation(
                prompt,
                max_new_tokens=512,
                stream=True,
                details=False,
            ):
                yield chunk
            if self.circuit_breaker:
                self.circuit_breaker.record_success()
        except Exception:
            if self.circuit_breaker:
                self.circuit_breaker.record_failure()
            logger.exception("Inference engine request failed")
            yield "\n[Inference Error: local inference engine unavailable]"
