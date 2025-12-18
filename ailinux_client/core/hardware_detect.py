"""
AILinux Hardware Detection Module
==================================

Detects system hardware capabilities for optimal performance:
- CPU: Model, cores, frequency, instruction sets (SSE, AVX, AVX2, AVX-512)
- GPU: Vendor, model, VRAM, OpenGL/Vulkan support
- RAM: Total, available, speed
- Storage: Type (SSD/HDD), speed

Hardened for binary deployment:
- Uses psutil as primary method (works in PyInstaller binaries)
- Graceful fallback to /proc filesystem
- Safe subprocess calls with proper error handling
- Works without root permissions
"""

import os
import re
import sys
import logging
import subprocess
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from pathlib import Path

logger = logging.getLogger("ailinux.hardware")

# Try to import psutil (primary method for binary compatibility)
try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False
    logger.warning("psutil not available - hardware detection may be limited")


def _safe_subprocess(cmd: List[str], timeout: int = 10) -> Optional[str]:
    """Safely run a subprocess command, returning stdout or None on failure."""
    try:
        # Check if command exists first
        if not _command_exists(cmd[0]):
            return None

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, 'LC_ALL': 'C'}  # Force consistent locale
        )
        if result.returncode == 0:
            return result.stdout
    except subprocess.TimeoutExpired:
        logger.debug(f"Command timed out: {cmd[0]}")
    except FileNotFoundError:
        logger.debug(f"Command not found: {cmd[0]}")
    except PermissionError:
        logger.debug(f"Permission denied: {cmd[0]}")
    except Exception as e:
        logger.debug(f"Subprocess error for {cmd[0]}: {e}")
    return None


def _command_exists(cmd: str) -> bool:
    """Check if a command exists in PATH."""
    try:
        # On Windows, use 'where', on Unix use 'which'
        check_cmd = 'where' if sys.platform == 'win32' else 'which'
        result = subprocess.run(
            [check_cmd, cmd],
            capture_output=True,
            timeout=5
        )
        return result.returncode == 0
    except Exception:
        return False


def _safe_read_file(path: str) -> Optional[str]:
    """Safely read a file, returning content or None on failure."""
    try:
        with open(path, 'r') as f:
            return f.read()
    except FileNotFoundError:
        pass
    except PermissionError:
        logger.debug(f"Permission denied reading: {path}")
    except Exception as e:
        logger.debug(f"Error reading {path}: {e}")
    return None


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
        """Detect CPU information using psutil (primary) or /proc/cpuinfo (fallback)"""
        cpu = CPUInfo()

        # Method 1: Use psutil (works in binary deployments)
        if HAS_PSUTIL:
            try:
                cpu.cores = psutil.cpu_count(logical=False) or 1
                cpu.threads = psutil.cpu_count(logical=True) or cpu.cores

                # Get CPU frequency
                freq = psutil.cpu_freq()
                if freq:
                    cpu.frequency_mhz = freq.current or 0
                    cpu.frequency_max_mhz = freq.max or cpu.frequency_mhz

                # Hyperthreading detection
                cpu.hyperthreading = cpu.threads > cpu.cores

                logger.debug("CPU info retrieved via psutil")
            except Exception as e:
                logger.debug(f"psutil CPU detection partial: {e}")

        # Method 2: Read /proc/cpuinfo for detailed info (Linux)
        content = _safe_read_file('/proc/cpuinfo')
        if content:
            try:
                lines = content.split('\n')
                flags = ""

                for line in lines:
                    if ':' not in line:
                        continue

                    key, value = line.split(':', 1)
                    key = key.strip().lower()
                    value = value.strip()

                    if key == 'model name' and cpu.model == "Unknown":
                        cpu.model = value
                    elif key == 'vendor_id' and cpu.vendor == "Unknown":
                        cpu.vendor = value
                    elif key == 'cpu cores' and cpu.cores == 1:
                        cpu.cores = int(value)
                    elif key == 'siblings' and cpu.threads == 1:
                        cpu.threads = int(value)
                    elif key == 'cpu mhz' and cpu.frequency_mhz == 0:
                        cpu.frequency_mhz = float(value)
                    elif key == 'cache size':
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
                    cpu.hyperthreading = 'ht' in flag_list or cpu.threads > cpu.cores
                    cpu.virtualization = 'vmx' in flag_list or 'svm' in flag_list
            except Exception as e:
                logger.debug(f"/proc/cpuinfo parsing error: {e}")

        # Method 3: Try lscpu as fallback for model name
        if cpu.model == "Unknown":
            output = _safe_subprocess(['lscpu'])
            if output:
                for line in output.split('\n'):
                    if 'Model name:' in line:
                        cpu.model = line.split(':', 1)[1].strip()
                        break
                    elif 'Vendor ID:' in line and cpu.vendor == "Unknown":
                        cpu.vendor = line.split(':', 1)[1].strip()

        # Get max frequency from sysfs
        max_freq_content = _safe_read_file('/sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq')
        if max_freq_content and cpu.frequency_max_mhz == 0:
            try:
                cpu.frequency_max_mhz = int(max_freq_content.strip()) / 1000
            except ValueError:
                pass

        # Detect architecture
        try:
            cpu.architecture = os.uname().machine
        except Exception:
            cpu.architecture = "x86_64"  # Safe default

        # Final fallback for missing values
        if cpu.cores == 0:
            cpu.cores = 1
        if cpu.threads == 0:
            cpu.threads = cpu.cores

        return cpu

    def _detect_gpus(self) -> List[GPUInfo]:
        """Detect GPU information using multiple methods for binary compatibility"""
        gpus = []

        # Method 1: Try lspci (most reliable on Linux)
        output = _safe_subprocess(['lspci', '-v', '-nn'])
        if output:
            try:
                current_gpu = None
                for line in output.split('\n'):
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
                logger.debug(f"lspci parsing error: {e}")

        # Method 2: Check /sys/class/drm for GPU info
        if not gpus:
            try:
                drm_path = Path('/sys/class/drm')
                if drm_path.exists():
                    for card in drm_path.iterdir():
                        if card.name.startswith('card') and not '-' in card.name:
                            gpu = GPUInfo()
                            # Try to read device info
                            device_path = card / 'device'
                            if (device_path / 'vendor').exists():
                                vendor_id = _safe_read_file(str(device_path / 'vendor'))
                                if vendor_id:
                                    vendor_id = vendor_id.strip()
                                    if vendor_id == '0x10de':
                                        gpu.vendor = "NVIDIA"
                                    elif vendor_id == '0x1002':
                                        gpu.vendor = "AMD"
                                    elif vendor_id == '0x8086':
                                        gpu.vendor = "Intel"
                            gpus.append(gpu)
            except Exception as e:
                logger.debug(f"/sys/class/drm read error: {e}")

        # Method 3: Check environment variable for Mesa/DRI info
        if not gpus:
            dri_prime = os.environ.get('DRI_PRIME', '')
            if dri_prime:
                gpu = GPUInfo()
                gpu.model = "DRI Device"
                gpus.append(gpu)

        # Enhance NVIDIA GPUs with nvidia-smi
        for gpu in gpus:
            if gpu.vendor == "NVIDIA":
                self._enhance_nvidia_info(gpu)

        # Check OpenGL/Vulkan capabilities
        self._detect_graphics_apis(gpus)

        # If no GPUs found, create a basic entry
        if not gpus:
            gpu = GPUInfo()
            gpu.model = "Integrated/Unknown"
            self._detect_graphics_apis([gpu])
            gpus.append(gpu)

        return gpus

    def _enhance_nvidia_info(self, gpu: GPUInfo):
        """Get additional info for NVIDIA GPUs using nvidia-smi"""
        output = _safe_subprocess([
            'nvidia-smi',
            '--query-gpu=name,memory.total,driver_version,cuda_version',
            '--format=csv,noheader,nounits'
        ])

        if output:
            try:
                parts = output.strip().split(',')
                if len(parts) >= 4:
                    gpu.model = parts[0].strip()
                    gpu.vram_mb = int(float(parts[1].strip()))
                    gpu.driver_version = parts[2].strip()
                    gpu.cuda_version = parts[3].strip()
                    gpu.hardware_accel = True
                    gpu.video_decode = True
                    gpu.video_encode = True
            except (ValueError, IndexError) as e:
                logger.debug(f"nvidia-smi output parsing error: {e}")

    def _detect_graphics_apis(self, gpus: List[GPUInfo]):
        """Detect OpenGL and Vulkan versions using safe subprocess calls"""
        # OpenGL version via glxinfo
        output = _safe_subprocess(['glxinfo'])
        if output:
            for line in output.split('\n'):
                if 'OpenGL version' in line:
                    match = re.search(r'(\d+\.\d+)', line)
                    if match:
                        for gpu in gpus:
                            gpu.opengl_version = match.group(1)
                            gpu.hardware_accel = True
                    break

        # Vulkan version via vulkaninfo
        output = _safe_subprocess(['vulkaninfo', '--summary'])
        if output:
            for line in output.split('\n'):
                if 'apiVersion' in line:
                    match = re.search(r'(\d+\.\d+\.\d+)', line)
                    if match:
                        for gpu in gpus:
                            gpu.vulkan_version = match.group(1)
                    break

        # Fallback: Check for Vulkan ICD files
        if not any(g.vulkan_version for g in gpus):
            vulkan_icd_paths = [
                '/etc/vulkan/icd.d',
                '/usr/share/vulkan/icd.d',
                str(Path.home() / '.local/share/vulkan/icd.d')
            ]
            for icd_path in vulkan_icd_paths:
                if Path(icd_path).exists():
                    for gpu in gpus:
                        gpu.vulkan_version = "available"
                    break

    def _detect_memory(self) -> MemoryInfo:
        """Detect memory information using psutil (primary) or /proc/meminfo (fallback)"""
        mem = MemoryInfo()

        # Method 1: Use psutil (works in binary deployments)
        if HAS_PSUTIL:
            try:
                vmem = psutil.virtual_memory()
                mem.total_mb = vmem.total // (1024 * 1024)
                mem.available_mb = vmem.available // (1024 * 1024)
                mem.used_mb = vmem.used // (1024 * 1024)

                swap = psutil.swap_memory()
                mem.swap_total_mb = swap.total // (1024 * 1024)
                mem.swap_used_mb = swap.used // (1024 * 1024)

                logger.debug("Memory info retrieved via psutil")
            except Exception as e:
                logger.debug(f"psutil memory detection error: {e}")

        # Method 2: Read /proc/meminfo for additional/fallback info
        content = _safe_read_file('/proc/meminfo')
        if content:
            try:
                for line in content.split('\n'):
                    parts = line.split()
                    if len(parts) >= 2:
                        key = parts[0].rstrip(':')
                        value = int(parts[1])  # KB

                        if key == 'MemTotal' and mem.total_mb == 0:
                            mem.total_mb = value // 1024
                        elif key == 'MemAvailable' and mem.available_mb == 0:
                            mem.available_mb = value // 1024
                        elif key == 'SwapTotal' and mem.swap_total_mb == 0:
                            mem.swap_total_mb = value // 1024
                        elif key == 'SwapFree' and mem.swap_used_mb == 0:
                            mem.swap_used_mb = mem.swap_total_mb - (value // 1024)

                if mem.used_mb == 0:
                    mem.used_mb = mem.total_mb - mem.available_mb
            except Exception as e:
                logger.debug(f"/proc/meminfo parsing error: {e}")

        # Method 3: Try to get memory speed/type from dmidecode (requires root, skip silently if fails)
        # Note: We don't use sudo in binary deployments - only try if already running as root
        if os.geteuid() == 0:
            output = _safe_subprocess(['dmidecode', '-t', 'memory'])
            if output:
                for line in output.split('\n'):
                    if 'Speed:' in line and 'MHz' in line and mem.speed_mhz == 0:
                        match = re.search(r'(\d+)\s*MHz', line)
                        if match:
                            mem.speed_mhz = int(match.group(1))
                    if 'Type:' in line and 'DDR' in line and mem.type == "Unknown":
                        match = re.search(r'(DDR\d?)', line)
                        if match:
                            mem.type = match.group(1)

        # Final fallback for missing values
        if mem.total_mb == 0:
            mem.total_mb = 4096  # Assume 4GB minimum
        if mem.available_mb == 0:
            mem.available_mb = mem.total_mb // 2

        return mem

    def _detect_storage(self) -> List[StorageInfo]:
        """Detect storage devices using psutil (primary) or lsblk (fallback)"""
        storage_list = []

        # Method 1: Use psutil for disk partitions
        if HAS_PSUTIL:
            try:
                partitions = psutil.disk_partitions(all=False)
                seen_devices = set()

                for part in partitions:
                    # Extract base device name (e.g., /dev/sda from /dev/sda1)
                    device = part.device
                    base_device = re.sub(r'p?\d+$', '', device)

                    if base_device in seen_devices:
                        continue
                    seen_devices.add(base_device)

                    storage = StorageInfo()
                    storage.device = base_device

                    # Get disk usage for this mountpoint
                    try:
                        usage = psutil.disk_usage(part.mountpoint)
                        storage.size_gb = usage.total / (1024**3)
                    except Exception:
                        pass

                    # Determine type from device name
                    if 'nvme' in device:
                        storage.type = "NVMe"
                        storage.rotational = False
                    elif 'sd' in device or 'vd' in device:
                        # Check rotational flag from sysfs
                        rotational_path = f'/sys/block/{Path(base_device).name}/queue/rotational'
                        rot_content = _safe_read_file(rotational_path)
                        if rot_content:
                            storage.rotational = rot_content.strip() == '1'
                            storage.type = "HDD" if storage.rotational else "SSD"
                        else:
                            storage.type = "SSD"  # Assume SSD if can't determine
                            storage.rotational = False

                    storage_list.append(storage)
            except Exception as e:
                logger.debug(f"psutil disk detection error: {e}")

        # Method 2: Use lsblk for more detailed info
        if not storage_list:
            output = _safe_subprocess(['lsblk', '-d', '-o', 'NAME,SIZE,ROTA,MODEL', '-n', '-b'])
            if output:
                try:
                    for line in output.strip().split('\n'):
                        if not line.strip():
                            continue
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
                    logger.debug(f"lsblk parsing error: {e}")

        # Method 3: Fall back to reading /sys/block directly
        if not storage_list:
            try:
                sys_block = Path('/sys/block')
                if sys_block.exists():
                    for device_dir in sys_block.iterdir():
                        name = device_dir.name
                        if name.startswith(('sd', 'nvme', 'vd', 'hd')):
                            storage = StorageInfo()
                            storage.device = f"/dev/{name}"

                            # Try to get size
                            size_content = _safe_read_file(str(device_dir / 'size'))
                            if size_content:
                                try:
                                    # Size is in 512-byte sectors
                                    storage.size_gb = (int(size_content.strip()) * 512) / (1024**3)
                                except ValueError:
                                    pass

                            # Check rotational
                            rot_content = _safe_read_file(str(device_dir / 'queue/rotational'))
                            if rot_content:
                                storage.rotational = rot_content.strip() == '1'
                                storage.type = "HDD" if storage.rotational else "SSD"
                            elif 'nvme' in name:
                                storage.type = "NVMe"
                                storage.rotational = False

                            # Try to get model
                            model_content = _safe_read_file(str(device_dir / 'device/model'))
                            if model_content:
                                storage.model = model_content.strip()

                            storage_list.append(storage)
            except Exception as e:
                logger.debug(f"/sys/block read error: {e}")

        return storage_list

    def _get_kernel_version(self) -> str:
        """Get kernel version safely"""
        try:
            return os.uname().release
        except Exception:
            # Try reading from /proc/version
            content = _safe_read_file('/proc/version')
            if content:
                match = re.search(r'Linux version (\S+)', content)
                if match:
                    return match.group(1)
            return "Unknown"

    def _get_distro(self) -> str:
        """Get Linux distribution name safely"""
        # Method 1: Read /etc/os-release (most reliable)
        content = _safe_read_file('/etc/os-release')
        if content:
            for line in content.split('\n'):
                if line.startswith('PRETTY_NAME='):
                    return line.split('=', 1)[1].strip().strip('"')

        # Method 2: Try /etc/lsb-release
        content = _safe_read_file('/etc/lsb-release')
        if content:
            for line in content.split('\n'):
                if line.startswith('DISTRIB_DESCRIPTION='):
                    return line.split('=', 1)[1].strip().strip('"')

        # Method 3: Try lsb_release command
        output = _safe_subprocess(['lsb_release', '-d'])
        if output:
            parts = output.split(':', 1)
            if len(parts) > 1:
                return parts[1].strip()

        # Method 4: Check for specific distro files
        distro_files = [
            ('/etc/debian_version', 'Debian'),
            ('/etc/redhat-release', None),  # Read content
            ('/etc/fedora-release', None),
            ('/etc/arch-release', 'Arch Linux'),
            ('/etc/gentoo-release', None),
        ]
        for path, default_name in distro_files:
            if Path(path).exists():
                if default_name:
                    return default_name
                content = _safe_read_file(path)
                if content:
                    return content.strip()[:50]  # Limit length

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
