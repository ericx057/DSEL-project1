from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from typing import Mapping, Optional


class LlamaCppPrecision(str, Enum):
    FP16 = "fp16"
    FP8 = "fp8"
    FP4 = "fp4"

    @classmethod
    def parse(cls, value: str) -> "LlamaCppPrecision":
        try:
            return cls(value.strip().lower())
        except ValueError as exc:
            allowed = ", ".join(mode.value for mode in cls)
            raise ValueError(f"Unsupported llama.cpp precision '{value}'. Allowed values: {allowed}") from exc

    @property
    def cache_type(self) -> str:
        # llama.cpp exposes low precision KV cache as q8_0/q4_0, not IEEE fp8/fp4.
        return {
            LlamaCppPrecision.FP16: "f16",
            LlamaCppPrecision.FP8: "q8_0",
            LlamaCppPrecision.FP4: "q4_0",
        }[self]


@dataclass(frozen=True)
class LlamaCppEndpointConfig:
    base_url: str = "http://127.0.0.1:8080"

    @classmethod
    def from_env(cls, env: Optional[Mapping[str, str]] = None) -> "LlamaCppEndpointConfig":
        values = env if env is not None else os.environ
        return cls(base_url=values.get("CIS_LLAMA_CPP_BASE_URL", cls.base_url))

    @property
    def normalized_base_url(self) -> str:
        base_url = self.base_url.strip().rstrip("/")
        if not base_url:
            raise ValueError("llama.cpp base url is not configured")
        if base_url.endswith("/completion"):
            base_url = base_url[: -len("/completion")]
        return base_url

    @property
    def completion_url(self) -> str:
        return f"{self.normalized_base_url}/completion"

    @property
    def health_url(self) -> str:
        return f"{self.normalized_base_url}/health"


@dataclass(frozen=True)
class LlamaCppServerSettings:
    precision: str = LlamaCppPrecision.FP16.value
    vram_gb: int = 6
    system_ram_gb: int = 64
    n_gpu_layers: str = "auto"
    kv_offload: bool = True
    context_window: int = 4096
    batch_size: int = 1024
    ubatch_size: int = 256
    flash_attention: str = "auto"
    mmap: bool = True
    cache_prompt: bool = True

    def __post_init__(self) -> None:
        self.precision_mode
        if self.context_window <= 0:
            raise ValueError("context_window must be greater than 0")

    @classmethod
    def from_env(cls, env: Optional[Mapping[str, str]] = None) -> "LlamaCppServerSettings":
        values = env if env is not None else os.environ
        return cls(
            precision=values.get("CIS_LLAMA_CPP_PRECISION", cls.precision),
            vram_gb=int(values.get("CIS_LLAMA_CPP_VRAM_GB", cls.vram_gb)),
            system_ram_gb=int(values.get("CIS_LLAMA_CPP_SYSTEM_RAM_GB", cls.system_ram_gb)),
            n_gpu_layers=values.get("CIS_LLAMA_CPP_N_GPU_LAYERS", cls.n_gpu_layers),
            context_window=int(
                values.get(
                    "CIS_LLAMA_CPP_CONTEXT_WINDOW",
                    values.get("CIS_LLAMA_CPP_CTX_SIZE", cls.context_window),
                )
            ),
            batch_size=int(values.get("CIS_LLAMA_CPP_BATCH_SIZE", cls.batch_size)),
            ubatch_size=int(values.get("CIS_LLAMA_CPP_UBATCH_SIZE", cls.ubatch_size)),
            flash_attention=values.get("CIS_LLAMA_CPP_FLASH_ATTN", cls.flash_attention),
        )

    @property
    def precision_mode(self) -> LlamaCppPrecision:
        return LlamaCppPrecision.parse(self.precision)

    @property
    def cache_type_k(self) -> str:
        return self.precision_mode.cache_type

    @property
    def cache_type_v(self) -> str:
        return self.precision_mode.cache_type

    def resolve_model_path(self, env: Optional[Mapping[str, str]] = None) -> str:
        values = env if env is not None else os.environ
        precision_key = f"CIS_LLAMA_CPP_MODEL_{self.precision_mode.value.upper()}"
        return values.get(precision_key) or values.get("CIS_LLAMA_CPP_MODEL_PATH", "")

    def to_llama_env(self) -> dict[str, str]:
        return {
            "LLAMA_ARG_CACHE_TYPE_K": self.cache_type_k,
            "LLAMA_ARG_CACHE_TYPE_V": self.cache_type_v,
            "LLAMA_ARG_KV_OFFLOAD": _bool_env(self.kv_offload),
            "LLAMA_ARG_N_GPU_LAYERS": self.n_gpu_layers,
            "LLAMA_ARG_CTX_SIZE": str(self.context_window),
            "LLAMA_ARG_BATCH": str(self.batch_size),
            "LLAMA_ARG_UBATCH": str(self.ubatch_size),
            "LLAMA_ARG_FLASH_ATTN": self.flash_attention,
            "LLAMA_ARG_MMAP": _bool_env(self.mmap),
            "LLAMA_ARG_CACHE_PROMPT": _bool_env(self.cache_prompt),
        }


def _bool_env(value: bool) -> str:
    return "true" if value else "false"
