from __future__ import annotations

from abc import ABC, abstractmethod
import json
from typing import Iterable, Optional

import httpx

from src.inference.llamacpp import LlamaCppEndpointConfig


class InferenceRuntime(ABC):
    @abstractmethod
    def generate_stream(self, prompt: str):
        pass


class LlamaCppRuntime(InferenceRuntime):
    def __init__(
        self,
        base_url: Optional[str] = None,
        endpoint_url: Optional[str] = None,
        timeout_seconds: float = 60.0,
    ):
        if endpoint_url is not None:
            if not endpoint_url.strip():
                raise ValueError("Inference engine endpoint is not configured")
            self.endpoint_url = endpoint_url.strip()
        else:
            self.endpoint_url = LlamaCppEndpointConfig(base_url=base_url or LlamaCppEndpointConfig.base_url).completion_url
        self.timeout_seconds = timeout_seconds

    def generate_stream(self, prompt: str):
        payload = {"prompt": prompt, "stream": True, "cache_prompt": True}
        timeout = httpx.Timeout(
            timeout=self.timeout_seconds,
            connect=min(10.0, self.timeout_seconds),
            pool=min(10.0, self.timeout_seconds),
        )
        with httpx.stream("POST", self.endpoint_url, json=payload, timeout=timeout) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                token, done = decode_stream_line(line)
                if token:
                    yield token
                if done:
                    break


class HttpInferenceRuntime(LlamaCppRuntime):
    def __init__(self, endpoint_url: str, timeout_seconds: float = 60.0):
        super().__init__(endpoint_url=endpoint_url, timeout_seconds=timeout_seconds)


class MockRuntime(InferenceRuntime):
    def __init__(self, responses: Optional[Iterable[str]] = None):
        self.responses = list(responses) if responses is not None else ["Mock", " response", " stream."]

    def generate_stream(self, prompt: str):
        for token in self.responses:
            yield token


def decode_stream_line(line) -> tuple[str, bool]:
    if not line:
        return "", False
    if isinstance(line, bytes):
        line = line.decode("utf-8")
    line = line.strip()
    if not line:
        return "", False
    if line.startswith("data:"):
        line = line[5:].strip()
        if line == "[DONE]":
            return "", True
    try:
        data = json.loads(line)
    except json.JSONDecodeError:
        return line, False
    done = bool(data.get("done", False) or data.get("stop", False))
    choices = data.get("choices")
    if choices:
        choice = choices[0]
        text = choice.get("text")
        if text:
            return str(text), bool(done or choice.get("finish_reason"))
        delta = choice.get("delta")
        if isinstance(delta, dict):
            content = delta.get("content")
            if content:
                return str(content), bool(done or choice.get("finish_reason"))
        if choice.get("finish_reason"):
            return "", True
    for key in ("content", "response", "token", "text", "delta"):
        value = data.get(key)
        if value:
            return str(value), done
    return "", done
