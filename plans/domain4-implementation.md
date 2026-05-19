# Domain 4: Inference Engine Implementation Plan

## Objective
Strictly implement Domain 4 based on the spec sheet (Section 6), featuring hardware-adaptive routing, an abstracted model runtime, and a request queue with backpressure. Code must be OOP, DRY, and have minimal comments.

## Architecture & Scope
*   **Target Directories:** `src/inference/` and `tests/inference/`.
*   **Modules:**
    *   `hardware.py`: `HardwareProfiler` using `psutil`. Defines system profiles (`cpu-small`, `cpu-large`, `gpu-single`, `gpu-dual`).
    *   `registry.py`: `ModelRegistry`. Maps tasks (e.g., "Single-function explanation" -> 7B) to models based on the active hardware profile.
    *   `runtime.py`: `InferenceRuntime` (ABC), `OllamaRuntime` (uses `httpx` for streaming), and `MockRuntime` (for tests).
    *   `queue.py`: `RequestQueue`. Enforces concurrent limits and queue depths, raising specific exceptions (equivalent to HTTP 503) for backpressure.

## Execution Steps
1.  **Hardware & Registry (6.2, 6.3):** Implement resource probing and deterministic model selection. 7B is always available; 14B/32B unlock based on thresholds.
2.  **Runtime & Streaming (6.1):** Build the Ollama integration supporting token-by-token streaming.
3.  **Queue & Backpressure (6.4):** Implement bounded queueing. Reject requests when queue depth exceeds the limit.
4.  **Testing:** Reach >95% coverage utilizing `MockRuntime` to simulate heavy Ollama responses.