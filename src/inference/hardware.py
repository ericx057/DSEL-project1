import psutil

class HardwareProfiler:
    def get_gpu_vram(self) -> int:
        return 0

    def get_system_ram(self) -> int:
        return psutil.virtual_memory().total // (1024 ** 3)

    def get_profile(self) -> str:
        vram = self.get_gpu_vram()
        if vram >= 32:
            return "gpu-dual"
        if vram >= 16:
            return "gpu-single"
        
        ram = self.get_system_ram()
        if ram >= 32:
            return "cpu-large"
        return "cpu-small"
