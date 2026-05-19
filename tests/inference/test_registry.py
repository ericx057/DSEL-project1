import pytest
from inference.hardware import HardwareProfiler
from inference.registry import ModelRegistry

class MockProfiler:
    def __init__(self, profile):
        self.profile = profile
    def get_profile(self):
        return self.profile

def test_model_registry_gpu_dual():
    registry = ModelRegistry(MockProfiler("gpu-dual"))
    assert registry.get_available_models() == ["7b", "14b", "32b"]
    assert registry.get_model_for_task("repo-analysis") == "32b"
    assert registry.get_model_for_task("unknown") == "7b"

def test_model_registry_gpu_single():
    registry = ModelRegistry(MockProfiler("gpu-single"))
    assert registry.get_available_models() == ["7b", "14b"]
    assert registry.get_model_for_task("repo-analysis") == "14b"
    assert registry.get_model_for_task("complex-task") == "14b"

def test_model_registry_cpu_large():
    registry = ModelRegistry(MockProfiler("cpu-large"))
    assert registry.get_available_models() == ["7b", "14b"]

def test_model_registry_cpu_small():
    registry = ModelRegistry(MockProfiler("cpu-small"))
    assert registry.get_available_models() == ["7b"]
    assert registry.get_model_for_task("repo-analysis") == "7b"
