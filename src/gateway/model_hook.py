from __future__ import annotations

from dataclasses import dataclass
import json
import logging
import os
import time
from typing import AsyncGenerator, Optional, Protocol

import httpx

from src.gateway.services import CircuitBreaker
from src.inference.llamacpp import LlamaCppEndpointConfig
from src.inference.runtime import decode_stream_line

logger = logging.getLogger(__name__)

DEFAULT_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_OPENROUTER_MODEL = "~openai/gpt-latest"
OPENROUTER_UNAVAILABLE_MESSAGE = "OpenRouter inference provider unavailable"


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


@dataclass(frozen=True)
class OpenRouterConfig:
    api_key: str
    model: str = DEFAULT_OPENROUTER_MODEL
    base_url: str = DEFAULT_OPENROUTER_BASE_URL
    app_referer: Optional[str] = None
    app_title: Optional[str] = None
    timeout_seconds: float = 60.0
    max_stream_seconds: float = 300.0

    @classmethod
    def from_env(cls) -> "OpenRouterConfig":
        return cls(
            api_key=os.environ.get("CIS_OPENROUTER_API_KEY") or os.environ.get("OPENROUTER_API_KEY", ""),
            model=os.environ.get("CIS_OPENROUTER_MODEL", DEFAULT_OPENROUTER_MODEL),
            base_url=os.environ.get("CIS_OPENROUTER_BASE_URL", DEFAULT_OPENROUTER_BASE_URL),
            app_referer=os.environ.get("CIS_OPENROUTER_REFERER"),
            app_title=os.environ.get("CIS_OPENROUTER_TITLE", "Codebase Intelligence System"),
            timeout_seconds=float(os.environ.get("CIS_INFERENCE_TIMEOUT_SECONDS", "60.0")),
            max_stream_seconds=float(os.environ.get("CIS_INFERENCE_MAX_STREAM_SECONDS", "300.0")),
        )

    @property
    def chat_completions_url(self) -> str:
        return f"{self.base_url.rstrip('/')}/chat/completions"


class OpenRouterStreamError(RuntimeError):
    pass


class OpenRouterChatCompletionClient:
    def __init__(self, config: Optional[OpenRouterConfig] = None):
        self.config = config or OpenRouterConfig.from_env()

    async def text_generation(
        self,
        prompt: str,
        max_new_tokens: int = 512,
        stream: bool = True,
        details: bool = False,
    ) -> AsyncGenerator[str, None]:
        if not self.config.api_key.strip():
            raise OpenRouterStreamError(OPENROUTER_UNAVAILABLE_MESSAGE)
        if not self.config.model.strip():
            raise OpenRouterStreamError(OPENROUTER_UNAVAILABLE_MESSAGE)

        payload = {
            "model": self.config.model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": stream,
            "max_tokens": max_new_tokens,
        }
        timeout = httpx.Timeout(
            timeout=self.config.timeout_seconds,
            connect=min(10.0, self.config.timeout_seconds),
            pool=min(10.0, self.config.timeout_seconds),
        )
        started_at = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                if not stream:
                    response = await client.post(
                        self.config.chat_completions_url,
                        headers=self._headers(),
                        json=payload,
                    )
                    response.raise_for_status()
                    content = self._message_content(response.json())
                    if content:
                        yield content
                    return

                async with client.stream(
                    "POST",
                    self.config.chat_completions_url,
                    headers=self._headers(),
                    json=payload,
                ) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if time.monotonic() - started_at > self.config.max_stream_seconds:
                            raise TimeoutError("OpenRouter stream exceeded maximum duration")
                        token, done = self._decode_stream_line(line)
                        if token:
                            yield token
                        if done:
                            break
        except OpenRouterStreamError:
            raise
        except (httpx.HTTPError, TimeoutError) as exc:
            raise OpenRouterStreamError(OPENROUTER_UNAVAILABLE_MESSAGE) from exc

    def _headers(self) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }
        if self.config.app_referer:
            headers["HTTP-Referer"] = self.config.app_referer
        if self.config.app_title:
            headers["X-OpenRouter-Title"] = self.config.app_title
        return headers

    @classmethod
    def _decode_stream_line(cls, line) -> tuple[str, bool]:
        if not line:
            return "", False
        if isinstance(line, bytes):
            line = line.decode("utf-8")
        line = line.strip()
        if not line or line.startswith(":"):
            return "", False
        if line.startswith("data:"):
            line = line[5:].strip()
        if line == "[DONE]":
            return "", True
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            return "", False
        error = data.get("error")
        if error:
            raise OpenRouterStreamError(OPENROUTER_UNAVAILABLE_MESSAGE)
        return cls._choice_content(data)

    @classmethod
    def _choice_content(cls, data: dict) -> tuple[str, bool]:
        choices = data.get("choices") or []
        if not choices:
            return "", False
        choice = choices[0]
        finish_reason = choice.get("finish_reason")
        delta = choice.get("delta")
        if isinstance(delta, dict) and delta.get("content"):
            return str(delta["content"]), bool(finish_reason)
        message = choice.get("message")
        if isinstance(message, dict) and message.get("content"):
            return str(message["content"]), bool(finish_reason)
        if finish_reason:
            return "", True
        return "", False

    @classmethod
    def _message_content(cls, data: dict) -> str:
        token, _ = cls._choice_content(data)
        return token


HttpInferenceEngineClient = LlamaCppCompletionClient


class ModelHook:
    def __init__(
        self,
        inference_engine_id: Optional[str] = None,
        endpoint_url: Optional[str] = None,
        circuit_breaker: Optional[CircuitBreaker] = None,
        client: Optional[TextGenerationClient] = None,
        provider: Optional[str] = None,
    ):
        self.circuit_breaker = circuit_breaker
        if client is not None:
            self.inference_engine_id = os.environ.get("CIS_INFERENCE_ENGINE_ID") or inference_engine_id or "custom"
            self.client = client
            return

        provider_name = self._resolve_provider(provider, inference_engine_id, endpoint_url)
        if provider_name == "openrouter":
            config = OpenRouterConfig.from_env()
            self.inference_engine_id = os.environ.get("CIS_INFERENCE_ENGINE_ID", f"openrouter:{config.model}")
            self.client = OpenRouterChatCompletionClient(config)
            return
        if provider_name == "llama.cpp":
            self.inference_engine_id = os.environ.get("CIS_INFERENCE_ENGINE_ID") or inference_engine_id or "llama.cpp"
            self.client = LlamaCppCompletionClient(endpoint_url=endpoint_url)
            return
        raise ValueError(f"Unsupported inference provider: {provider_name}")

    @staticmethod
    def _resolve_provider(
        provider: Optional[str],
        inference_engine_id: Optional[str],
        endpoint_url: Optional[str],
    ) -> str:
        configured_provider = provider or os.environ.get("CIS_INFERENCE_PROVIDER")
        if configured_provider:
            return ModelHook._normalize_provider(configured_provider)

        configured_engine = os.environ.get("CIS_INFERENCE_ENGINE_ID") or inference_engine_id or ""
        engine_provider = ModelHook._provider_from_engine_id(configured_engine)
        if engine_provider:
            return engine_provider
        if endpoint_url:
            return "llama.cpp"
        return "openrouter"

    @staticmethod
    def _provider_from_engine_id(engine_id: str) -> Optional[str]:
        normalized = engine_id.strip().lower()
        if normalized.startswith("openrouter"):
            return "openrouter"
        if normalized in {"llama.cpp", "llamacpp", "llama"}:
            return "llama.cpp"
        return None

    @staticmethod
    def _normalize_provider(provider: str) -> str:
        normalized = provider.strip().lower()
        if normalized in {"openrouter", "openrouter.ai"}:
            return "openrouter"
        if normalized in {"llama.cpp", "llamacpp", "llama"}:
            return "llama.cpp"
        return normalized

    async def generate_stream(self, prompt: str) -> AsyncGenerator[str, None]:
        if self.circuit_breaker and not self.circuit_breaker.is_allowed():
            yield "\n[Inference Error: inference provider unavailable]"
            return
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
            yield "\n[Inference Error: inference provider unavailable]"
