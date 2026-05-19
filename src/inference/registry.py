from .hardware import HardwareProfiler

class ModelRegistry:
    def __init__(self, profiler: HardwareProfiler):
        self.profiler = profiler
        self.task_requirements = {
            "single-function": "7b",
            "complex-task": "14b",
            "repo-analysis": "32b"
        }

    def get_available_models(self) -> list[str]:
        profile = self.profiler.get_profile()
        if profile == "gpu-dual":
            return ["7b", "14b", "32b"]
        if profile in ("gpu-single", "cpu-large"):
            return ["7b", "14b"]
        return ["7b"]

    def get_model_for_task(self, task_type: str) -> str:
        req = self.task_requirements.get(task_type, "7b")
        available = self.get_available_models()
        if req in available:
            return req
        return available[-1]
