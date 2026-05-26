#!/bin/sh
set -eu

precision="${CIS_LLAMA_CPP_PRECISION:-fp16}"

case "$precision" in
    fp16)
        default_cache_type="f16"
        precision_model_path="${CIS_LLAMA_CPP_MODEL_FP16:-}"
        precision_model_key="CIS_LLAMA_CPP_MODEL_FP16"
        ;;
    fp8)
        default_cache_type="q8_0"
        precision_model_path="${CIS_LLAMA_CPP_MODEL_FP8:-}"
        precision_model_key="CIS_LLAMA_CPP_MODEL_FP8"
        ;;
    fp4)
        default_cache_type="q4_0"
        precision_model_path="${CIS_LLAMA_CPP_MODEL_FP4:-}"
        precision_model_key="CIS_LLAMA_CPP_MODEL_FP4"
        ;;
    *)
        echo "Unsupported CIS_LLAMA_CPP_PRECISION '$precision'. Use fp16, fp8, or fp4." >&2
        exit 64
        ;;
esac

model_path="${precision_model_path:-${CIS_LLAMA_CPP_MODEL_PATH:-}}"
if [ -z "$model_path" ]; then
    echo "Set CIS_LLAMA_CPP_MODEL_PATH or $precision_model_key to a GGUF file." >&2
    exit 64
fi

export LLAMA_ARG_MODEL="${LLAMA_ARG_MODEL:-$model_path}"
export LLAMA_ARG_HOST="${LLAMA_ARG_HOST:-0.0.0.0}"
export LLAMA_ARG_PORT="${LLAMA_ARG_PORT:-8080}"
context_window="${CIS_LLAMA_CPP_CONTEXT_WINDOW:-${CIS_LLAMA_CPP_CTX_SIZE:-4096}}"
case "$context_window" in
    ""|*[!0-9]*)
        echo "CIS_LLAMA_CPP_CONTEXT_WINDOW must be a positive integer." >&2
        exit 64
        ;;
esac
if [ "$context_window" -le 0 ]; then
    echo "CIS_LLAMA_CPP_CONTEXT_WINDOW must be a positive integer." >&2
    exit 64
fi
export LLAMA_ARG_CTX_SIZE="${LLAMA_ARG_CTX_SIZE:-$context_window}"
export LLAMA_ARG_BATCH="${LLAMA_ARG_BATCH:-${CIS_LLAMA_CPP_BATCH_SIZE:-1024}}"
export LLAMA_ARG_UBATCH="${LLAMA_ARG_UBATCH:-${CIS_LLAMA_CPP_UBATCH_SIZE:-256}}"
export LLAMA_ARG_N_GPU_LAYERS="${LLAMA_ARG_N_GPU_LAYERS:-${CIS_LLAMA_CPP_N_GPU_LAYERS:-auto}}"
export LLAMA_ARG_KV_OFFLOAD="${LLAMA_ARG_KV_OFFLOAD:-true}"
export LLAMA_ARG_CACHE_TYPE_K="${LLAMA_ARG_CACHE_TYPE_K:-${CIS_LLAMA_CPP_CACHE_TYPE:-$default_cache_type}}"
export LLAMA_ARG_CACHE_TYPE_V="${LLAMA_ARG_CACHE_TYPE_V:-${CIS_LLAMA_CPP_CACHE_TYPE:-$default_cache_type}}"
export LLAMA_ARG_CACHE_PROMPT="${LLAMA_ARG_CACHE_PROMPT:-true}"
export LLAMA_ARG_FLASH_ATTN="${LLAMA_ARG_FLASH_ATTN:-${CIS_LLAMA_CPP_FLASH_ATTN:-auto}}"
export LLAMA_ARG_MMAP="${LLAMA_ARG_MMAP:-true}"
export LLAMA_ARG_ENDPOINT_METRICS="${LLAMA_ARG_ENDPOINT_METRICS:-true}"

exec /app/llama-server "$@"
