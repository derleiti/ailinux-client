"""
AILinux Hardware Detection Module
==================================

Detects system hardware capabilities for optimal performance:
- CPU: Model, cores, frequency, instruction sets (SSE, AVX, AVX2, AVX-512)
- GPU: Vendor, model, VRAM, OpenGL/Vulkan support
- RAM: Total, available, speed
- Storage: Type (SSD/HDD), speed
"""

import os
import re
import logging
import subprocess
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from pathlib import Path

logger = logging.getLogger("ailinux.hardware")


@dataclass
class CPUInfo:
    """CPU information"""
    model: str = "Unknown"
    vendor: str = "Unknown"
    cores: int = 1
    threads: int = 1
    frequency_mhz: float = 0.0
    frequency_max_mhz: float = 0.0
    cache_l1: int = 0  # KB
    cache_l2: int = 0  # KB
    cache_l3: int = 0  # KB
    architecture: str = "unknown"

    # Instruction sets
    sse: bool = False
    sse2: bool = False
    sse3: bool = False
    ssse3: bool = False
    sse4_1: bool = False
    sse4_2: bool = False
    avx: bool = False
    avx2: bool = False
    avx512: bool = False
    aes: bool = False
    fma: bool = False

    # Additional features
    hyperthreading: bool = False
    virtualization: bool = False  # VT-x / AMD-V


@dataclass
class GPUInfo:
    """GPU information"""
    vendor: str = "Unknown"
    model: str = "Unknown"
    vram_mb: int = 0
    driver: str = "Unknown"
    driver_version: str = ""

    # Capabilities
    opengl_version: str = ""
    vulkan_version: str = ""
    cuda_version: str = ""
    opencl_version: str = ""

    # Acceleration support
    hardware_accel: bool = False
    video_decode: bool = False
    video_encode: bool = False


@dataclass
class MemoryInfo:
    """Memory information"""
    total_mb: int = 0
    available_mb: int = 0
    used_mb: int = 0
    swap_total_mb: int = 0
    swap_used_mb: int = 0
    speed_mhz: int = 0
    type: str = "Unknown"  # DDR4, DDR5, etc.


@dataclass
class StorageInfo:
    """Storage information"""
    device: str = ""
    model: str = ""
    size_gb: float = 0.0
    type: str = "Unknown"  # SSD, HDD, NVMe
    rotational: bool = True
    read_speed_mb: float = 0.0
    write_speed_mb: float = 0.0


@dataclass
class HardwareInfo:
    """Complete hardware information"""
    cpu: CPUInfo = field(default_factory=CPUInfo)
    gpus: List[GPUInfo] = field(default_factory=list)
    memory: MemoryInfo = field(default_factory=MemoryInfo)
    storage: List[StorageInfo] = field(default_factory=list)

    # System
    kernel: str = ""
    distro: str = ""
    hostname: str = ""

    # Performance recommendations
    recommended_threads: int = 1
    gpu_acceleration: bool = False
    opengl_available: bool = False
    vulkan_available: bool = False


class HardwareDetector:
    """Detects system hardware capabilities"""

    _instance: Optional['HardwareDetector'] = None
    _cached_info: Optional[HardwareInfo] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def detect_all(self, force_refresh: bool = False) -> HardwareInfo:
        """Detect all hardware information"""
        if self._cached_info and not force_refresh:
            return self._cached_info

        info = HardwareInfo()

        # Detect components
        info.cpu = self._detect_cpu()
        info.gpus = self._detect_gpus()
        info.memory = self._detect_memory()
        info.storage = self._detect_storage()

        # System info
        info.kernel = self._get_kernel_version()
        info.distro = self._get_distro()
        info.hostname = os.uname().nodename

        # Calculate recommendations
        info.recommended_threads = self._calc_recommended_threads(info.cpu)
        info.gpu_acceleration = any(g.hardware_accel for g in info.gpus)
        info.opengl_available = any(g.opengl_version for g in info.gpus)
        info.vulkan_available = any(g.vulkan_version for g in info.gpus)

        self._cached_info = info
        logger.info(f"Hardware detected: {info.cpu.model}, {len(info.gpus)} GPU(s), "
                   f"{info.memory.total_mb}MB RAM")

        return info

    def _detect_cpu(self) -> CPUInfo:
        """Detect CPU information from /proc/cpuinfo"""
        cpu = CPUInfo()

        try:
            with open('/proc/cpuinfo', 'r') as f:
                content = f.read()

            # Parse cpuinfo
            lines = content.split('\n')
            flags = ""

            for line in lines:
                if ':' not in line:
                    continue

                key, value = line.split(':', 1)
                key = key.strip().lower()
                value = value.strip()

                if key == 'model name':
                    cpu.model = value
                elif key == 'vendor_id':
                    cpu.vendor = value
                elif key == 'cpu cores':
                    cpu.cores = int(value)
                elif key == 'siblings':
                    cpu.threads = int(value)
                elif key == 'cpu mhz':
                    cpu.frequency_mhz = float(value)
                elif key == 'cache size':
                    # Usually L2 or L3
                    match = re.search(r'(\d+)', value)
                    if match:
                        cpu.cache_l3 = int(match.group(1))
                elif key == 'flags':
                    flags = value

            # Parse CPU flags for instruction sets
            if flags:
                flag_list = flags.split()
                cpu.sse = 'sse' in flag_list
                cpu.sse2 = 'sse2' in flag_list
                cpu.sse3 = 'sse3' in flag_list or 'pni' in flag_list
                cpu.ssse3 = 'ssse3' in flag_list
                cpu.sse4_1 = 'sse4_1' in flag_list
                cpu.sse4_2 = 'sse4_2' in flag_list
                cpu.avx = 'avx' in flag_list
                cpu.avx2 = 'avx2' in flag_list
                cpu.avx512 = any(f.startswith('avx512') for f in flag_list)
                cpu.aes = 'aes' in flag_list or 'aes-ni' in flag_list
                cpu.fma = 'fma' in flag_list or 'fma3' in flag_list
                cpu.hyperthreading = 'ht' in flag_list
                cpu.virtualization = 'vmx' in flag_list or 'svm' in flag_list

            # Get max frequency
            try:
                max_freq_path = '/sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq'
                if os.path.exists(max_freq_path):
                    with open(max_freq_path) as f:
                        cpu.frequency_max_mhz = int(f.read().strip()) / 1000
            except Exception:
                pass

            # Detect architecture
            cpu.architecture = os.uname().machine

        except Exception as e:
            logger.error(f"CPU detection failed: {e}")

        return cpu

    def _detect_gpus(self) -> List[GPUInfo]:
        """Detect GPU information"""
        gpus = []

        # Try lspci first
        try:
            result = subprocess.run(
                ['lspci', '-v', '-nn'],
                capture_output=True, text=True, timeout=10
            )

            if result.returncode == 0:
                current_gpu = None
                for line in result.stdout.split('\n'):
                    # VGA compatible controller or 3D controller
                    if 'VGA' in line or '3D controller' in line or 'Display controller' in line:
                        if current_gpu:
                            gpus.append(current_gpu)
                        current_gpu = GPUInfo()

                        # Parse vendor and model
                        if 'NVIDIA' in line:
                            current_gpu.vendor = "NVIDIA"
                        elif 'AMD' in line or 'ATI' in line:
                            current_gpu.vendor = "AMD"
                        elif 'Intel' in line:
                            current_gpu.vendor = "Intel"

                        # Extract model name
                        match = re.search(r'\[([^\]]+)\]', line)
                        if match:
                            current_gpu.model = match.group(1)

                    elif current_gpu and 'Kernel driver' in line:
                        match = re.search(r'Kernel driver in use: (\w+)', line)
                        if match:
                            current_gpu.driver = match.group(1)

                if current_gpu:
                    gpus.append(current_gpu)

        except Exception as e:
            logger.warning(f"lspci failed: {e}")

        # Enhance with nvidia-smi for NVIDIA cards
        for gpu in gpus:
            if gpu.vendor == "NVIDIA":
                self._enhance_nvidia_info(gpu)

        # Check OpenGL/Vulkan
        self._detect_graphics_apis(gpus)

        # If no GPUs found, create a basic entry
        if not gpus:
            gpu = GPUInfo()
            gpu.model = "Integrated/Unknown"
            self._detect_graphics_apis([gpu])
            gpus.append(gpu)

        return gpus

    def _enhance_nvidia_info(self, gpu: GPUInfo):
        """Get additional info for NVIDIA GPUs"""
        try:
            result = subprocess.run(
                ['nvidia-smi', '--query-gpu=name,memory.total,driver_version,cuda_version',
                 '--format=csv,noheader,nounits'],
                capture_output=True, text=True, timeout=10
            )

            if result.returncode == 0:
                parts = result.stdout.strip().split(',')
                if len(parts) >= 4:
                    gpu.model = parts[0].strip()
                    gpu.vram_mb = int(float(parts[1].strip()))
                    gpu.driver_version = parts[2].strip()
                    gpu.cuda_version = parts[3].strip()
                    gpu.hardware_accel = True
                    gpu.video_decode = True
                    gpu.video_encode = True

        except Exception as e:
            logger.debug(f"nvidia-smi not available: {e}")

    def _detect_graphics_apis(self, gpus: List[GPUInfo]):
        """Detect OpenGL and Vulkan versions"""
        # OpenGL version
        try:
            result = subprocess.run(
                ['glxinfo'], capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if 'OpenGL version' in line:
                        match = re.search(r'(\d+\.\d+)', line)
                        if match:
                            for gpu in gpus:
                                gpu.opengl_version = match.group(1)
                                gpu.hardware_accel = True
                        break
        except Exception:
            pass

        # Vulkan version
        try:
            result = subprocess.run(
                ['vulkaninfo', '--summary'], capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if 'apiVersion' in line:
                        match = re.search(r'(\d+\.\d+\.\d+)', line)
                        if match:
                            for gpu in gpus:
                                gpu.vulkan_version = match.group(1)
                        break
        except Exception:
            pass

    def _detect_memory(self) -> MemoryInfo:
        """Detect memory information from /proc/meminfo"""
        mem = MemoryInfo()

        try:
            with open('/proc/meminfo', 'r') as f:
                for line in f:
                    parts = line.split()
                    if len(parts) >= 2:
                        key = parts[0].rstrip(':')
                        value = int(parts[1])  # KB

                        if key == 'MemTotal':
                            mem.total_mb = value // 1024
                        elif key == 'MemAvailable':
                            mem.available_mb = value // 1024
                        elif key == 'SwapTotal':
                            mem.swap_total_mb = value // 1024
                        elif key == 'SwapFree':
                            mem.swap_used_mb = mem.swap_total_mb - (value // 1024)

            mem.used_mb = mem.total_mb - mem.available_mb

            # Try to get memory speed from dmidecode
            try:
                result = subprocess.run(
                    ['sudo', 'dmidecode', '-t', 'memory'],
                    capture_output=True, text=True, timeout=10
                )
                if result.returncode == 0:
                    for line in result.stdout.split('\n'):
                        if 'Speed:' in line and 'MHz' in line:
                            match = re.search(r'(\d+)\s*MHz', line)
                            if match:
                                mem.speed_mhz = int(match.group(1))
                                break
                        if 'Type:' in line and 'DDR' in line:
                            match = re.search(r'(DDR\d?)', line)
                            if match:
                                mem.type = match.group(1)
            except Exception:
                pass

        except Exception as e:
            logger.error(f"Memory detection failed: {e}")

        return mem

    def _detect_storage(self) -> List[StorageInfo]:
        """Detect storage devices"""
        storage_list = []

        try:
            # List block devices
            result = subprocess.run(
                ['lsblk', '-d', '-o', 'NAME,SIZE,ROTA,MODEL', '-n', '-b'],
                capture_output=True, text=True, timeout=10
            )

            if result.returncode == 0:
                for line in result.stdout.strip().split('\n'):
                    parts = line.split(None, 3)
                    if len(parts) >= 3:
                        storage = StorageInfo()
                        storage.device = f"/dev/{parts[0]}"

                        try:
                            storage.size_gb = int(parts[1]) / (1024**3)
                        except ValueError:
                            pass

                        storage.rotational = parts[2] == '1'
                        storage.type = "HDD" if storage.rotational else "SSD"

                        # Check for NVMe
                        if 'nvme' in parts[0]:
                            storage.type = "NVMe"

                        if len(parts) > 3:
                            storage.model = parts[3]

                        # Only add real storage devices (skip loop, dm, etc)
                        if parts[0].startswith(('sd', 'nvme', 'vd', 'hd')):
                            storage_list.append(storage)

        except Exception as e:
            logger.error(f"Storage detection failed: {e}")

        return storage_list

    def _get_kernel_version(self) -> str:
        """Get kernel version"""
        return os.uname().release

    def _get_distro(self) -> str:
        """Get Linux distribution name"""
        try:
            with open('/etc/os-release', 'r') as f:
                for line in f:
                    if line.startswith('PRETTY_NAME='):
                        return line.split('=', 1)[1].strip().strip('"')
        except Exception:
            pass
        return "Unknown Linux"

    def _calc_recommended_threads(self, cpu: CPUInfo) -> int:
        """Calculate recommended thread count for parallel operations"""
        # Use physical cores for CPU-bound, threads for I/O-bound
        # Leave some headroom for system
        if cpu.threads > 4:
            return max(1, cpu.threads - 2)
        elif cpu.threads > 2:
            return max(1, cpu.threads - 1)
        return cpu.threads

    def get_qt_render_hints(self) -> Dict[str, Any]:
        """Get recommended Qt rendering settings based on hardware"""
        info = self.detect_all()

        hints = {
            'use_opengl': info.opengl_available,
            'use_software_rendering': not info.gpu_acceleration,
            'antialiasing': info.gpu_acceleration,
            'smooth_pixmap_transform': info.gpu_acceleration,
            'high_quality_antialiasing': info.memory.total_mb > 4096 and info.gpu_acceleration,
            'thread_count': info.recommended_threads,
            'enable_vsync': info.gpu_acceleration,
            'cache_size_mb': min(256, info.memory.total_mb // 16),
        }

        # Performance tier
        if info.memory.total_mb >= 16384 and info.gpu_acceleration:
            hints['performance_tier'] = 'high'
        elif info.memory.total_mb >= 8192:
            hints['performance_tier'] = 'medium'
        else:
            hints['performance_tier'] = 'low'

        return hints

    def get_summary(self) -> str:
        """Get human-readable hardware summary"""
        info = self.detect_all()

        # CPU instruction sets
        cpu_features = []
        if info.cpu.avx512:
            cpu_features.append("AVX-512")
        elif info.cpu.avx2:
            cpu_features.append("AVX2")
        elif info.cpu.avx:
            cpu_features.append("AVX")
        if info.cpu.aes:
            cpu_features.append("AES-NI")
        if info.cpu.fma:
            cpu_features.append("FMA")

        lines = [
            f"CPU: {info.cpu.model}",
            f"  Cores: {info.cpu.cores} ({info.cpu.threads} threads)",
            f"  Frequency: {info.cpu.frequency_mhz:.0f} MHz (max {info.cpu.frequency_max_mhz:.0f} MHz)",
            f"  Features: {', '.join(cpu_features) if cpu_features else 'Basic'}",
            f"  Virtualization: {'Yes' if info.cpu.virtualization else 'No'}",
            "",
            f"Memory: {info.memory.total_mb} MB ({info.memory.type} @ {info.memory.speed_mhz} MHz)",
            f"  Available: {info.memory.available_mb} MB",
            "",
        ]

        for i, gpu in enumerate(info.gpus):
            lines.append(f"GPU {i+1}: {gpu.vendor} {gpu.model}")
            if gpu.vram_mb:
                lines.append(f"  VRAM: {gpu.vram_mb} MB")
            lines.append(f"  Driver: {gpu.driver} {gpu.driver_version}")
            if gpu.opengl_version:
                lines.append(f"  OpenGL: {gpu.opengl_version}")
            if gpu.vulkan_version:
                lines.append(f"  Vulkan: {gpu.vulkan_version}")
            if gpu.cuda_version:
                lines.append(f"  CUDA: {gpu.cuda_version}")
            lines.append("")

        for storage in info.storage:
            lines.append(f"Storage: {storage.model or storage.device}")
            lines.append(f"  Type: {storage.type}, Size: {storage.size_gb:.1f} GB")

        lines.extend([
            "",
            f"System: {info.distro}",
            f"Kernel: {info.kernel}",
            f"Recommended threads: {info.recommended_threads}",
            f"GPU Acceleration: {'Available' if info.gpu_acceleration else 'Not available'}",
        ])

        return '\n'.join(lines)


# Global instance
hardware_detector = HardwareDetector()


def get_hardware_info() -> HardwareInfo:
    """Get cached hardware information"""
    return hardware_detector.detect_all()


def get_qt_hints() -> Dict[str, Any]:
    """Get Qt rendering hints based on hardware"""
    return hardware_detector.get_qt_render_hints()
