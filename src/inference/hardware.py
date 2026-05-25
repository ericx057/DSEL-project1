import os
import sys

class HardwareProfiler:
    def get_gpu_vram(self) -> int:
        return 0

    def get_system_ram(self) -> int:
        if sys.platform == "win32":
            try:
                import ctypes

                class MemoryStatus(ctypes.Structure):
                    _fields_ = [
                        ("dwLength", ctypes.c_ulong),
                        ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong),
                        ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong),
                        ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong),
                        ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                    ]

                status = MemoryStatus()
                status.dwLength = ctypes.sizeof(MemoryStatus)
                ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
                return int(status.ullTotalPhys // (1024 ** 3))
            except Exception:
                return 0
        pages = os.sysconf("SC_PHYS_PAGES") if hasattr(os, "sysconf") else 0
        page_size = os.sysconf("SC_PAGE_SIZE") if hasattr(os, "sysconf") else 0
        return int((pages * page_size) // (1024 ** 3)) if pages and page_size else 0

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
