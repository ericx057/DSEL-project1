from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from src.inference.llamacpp import LlamaCppEndpointConfig


@dataclass(frozen=True)
class InferenceEngineEndpoint:
    url: str
    health_url: str
    engine_id: str = "llama.cpp"


class InferenceEngineRegistry:
    def __init__(
        self,
        endpoint_url: Optional[str] = None,
        base_url: Optional[str] = None,
        engine_id: Optional[str] = None,
    ):
        self._endpoint_url = endpoint_url or ""
        self._base_url = base_url if base_url is not None else os.environ.get("CIS_LLAMA_CPP_BASE_URL", LlamaCppEndpointConfig.base_url)
        self._engine_id = engine_id or os.environ.get("CIS_INFERENCE_ENGINE_ID", "llama.cpp")

    def get_engine_endpoint(self) -> InferenceEngineEndpoint:
        endpoint_url = self._endpoint_url.strip()
        if endpoint_url:
            config = LlamaCppEndpointConfig(base_url=endpoint_url)
            return InferenceEngineEndpoint(url=config.completion_url, health_url=config.health_url, engine_id=self._engine_id)
        config = LlamaCppEndpointConfig(base_url=self._base_url)
        return InferenceEngineEndpoint(url=config.completion_url, health_url=config.health_url, engine_id=self._engine_id)
