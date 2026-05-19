import pytest
from inference.hardware import HardwareProfiler

def test_hardware_profiler_gpu_dual(monkeypatch):
    profiler = HardwareProfiler()
    monkeypatch.setattr(profiler, "get_gpu_vram", lambda: 32)
    assert profiler.get_profile() == "gpu-dual"

def test_hardware_profiler_gpu_single(monkeypatch):
    profiler = HardwareProfiler()
    monkeypatch.setattr(profiler, "get_gpu_vram", lambda: 16)
    assert profiler.get_profile() == "gpu-single"

def test_hardware_profiler_cpu_large(monkeypatch):
    profiler = HardwareProfiler()
    monkeypatch.setattr(profiler, "get_gpu_vram", lambda: 0)
    monkeypatch.setattr(profiler, "get_system_ram", lambda: 32)
    assert profiler.get_profile() == "cpu-large"

def test_hardware_profiler_cpu_small(monkeypatch):
    profiler = HardwareProfiler()
    monkeypatch.setattr(profiler, "get_gpu_vram", lambda: 0)
    monkeypatch.setattr(profiler, "get_system_ram", lambda: 16)
    assert profiler.get_profile() == "cpu-small"

def test_hardware_profiler_real_ram():
    profiler = HardwareProfiler()
    ram = profiler.get_system_ram()
    assert isinstance(ram, int)
    assert ram >= 0
