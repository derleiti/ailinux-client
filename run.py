#!/usr/bin/env python3
"""
AILinux Client - Bootstrap & Hardware-Optimized Startup
=========================================================

Führt Hardware-Erkennung durch und startet Module mit optimalen Einstellungen.

Usage:
    ./run.py                    # Normal start with auto-detection
    ./run.py --desktop          # Desktop mode
    ./run.py --hwinfo           # Show hardware info only
    ./run.py --benchmark        # Run performance benchmark
"""
import sys
import os
import time
import logging
import signal
import atexit
from pathlib import Path

# Projektpfad hinzufügen
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger("ailinux.bootstrap")

# =============================================================================
# Global Cleanup Registry - handles SIGTERM, SIGINT, and atexit
# =============================================================================

_cleanup_handlers = []
_cleanup_done = False
_main_window = None  # Global reference for cleanup


def register_cleanup(handler):
    """Register a cleanup handler to be called on exit/crash"""
    global _cleanup_handlers
    if handler not in _cleanup_handlers:
        _cleanup_handlers.append(handler)
        logger.debug(f"Registered cleanup handler: {handler.__name__ if hasattr(handler, '__name__') else handler}")


def set_main_window(window):
    """Set main window reference for cleanup"""
    global _main_window
    _main_window = window


def _perform_cleanup():
    """Execute all registered cleanup handlers"""
    global _cleanup_done, _cleanup_handlers, _main_window
    
    if _cleanup_done:
        return
    _cleanup_done = True
    
    logger.info("Performing cleanup (MCP Node, Local MCP)...")
    
    # Cleanup MainWindow first (stops MCP Node thread)
    if _main_window:
        try:
            # Stop MCP Node thread
            if hasattr(_main_window, 'mcp_node_thread') and _main_window.mcp_node_thread:
                logger.info("Stopping MCP Node thread...")
                _main_window.mcp_node_thread.stop()
                _main_window.mcp_node_thread.wait(2000)
            
            # Stop local MCP server
            if hasattr(_main_window, '_stop_local_mcp_server'):
                _main_window._stop_local_mcp_server()
                
        except Exception as e:
            logger.error(f"MainWindow cleanup failed: {e}")
    
    # Run other registered handlers
    for handler in reversed(_cleanup_handlers):
        try:
            handler()
        except Exception as e:
            logger.error(f"Cleanup handler failed: {e}")
    
    logger.info("Cleanup completed")


def _signal_handler(signum, frame):
    """Handle termination signals (SIGTERM, SIGINT)"""
    sig_name = signal.Signals(signum).name
    logger.warning(f"Received {sig_name} - initiating graceful shutdown")
    _perform_cleanup()
    sys.exit(128 + signum)


# Register signal handlers for graceful shutdown
signal.signal(signal.SIGTERM, _signal_handler)
signal.signal(signal.SIGINT, _signal_handler)

# Register atexit handler (normal exit)
atexit.register(_perform_cleanup)



class HardwareOptimizedBootstrap:
    """
    Bootstrap-Klasse für hardware-optimierten Start.

    Führt sequentiell aus:
    1. Hardware-Erkennung
    2. Ressourcen-Optimierung
    3. Modul-Initialisierung
    4. Application-Start
    """

    def __init__(self):
        self.hw_info = None
        self.qt_hints = None
        self.start_time = time.time()

    def run(self):
        """Haupteinstiegspunkt - führt alle Schritte sequentiell aus"""
        try:
            # Phase 0: Early performance optimizations (before Qt import)
            self._early_optimizations()

            # Phase 1: Hardware-Erkennung
            logger.info("=" * 60)
            logger.info("AILinux Client Bootstrap")
            logger.info("=" * 60)

            self._detect_hardware()

            # Phase 2: Ressourcen-Optimierung
            self._optimize_resources()

            # Phase 3: Qt-Umgebung vorbereiten
            self._setup_qt_environment()

            # Phase 4: Module initialisieren
            self._init_modules()

            # Phase 5: Application starten
            return self._start_application()

        except Exception as e:
            logger.error(f"Bootstrap failed: {e}")
            import traceback
            traceback.print_exc()
            return 1

    def _early_optimizations(self):
        """Phase 0: Performance optimizations before Qt import"""
        try:
            from ailinux_client.core.ram_cache import (
                optimize_python_gc,
                optimize_qt_for_performance,
                preload_modules,
                get_ram_cache
            )

            # Optimize GC for GUI (disable during startup)
            optimize_python_gc()

            # Set Qt environment for performance
            optimize_qt_for_performance()

            # Initialize RAM cache (256MB default)
            self.ram_cache = get_ram_cache(256)

            # Preload common modules
            preload_modules()

            logger.info("[Phase 0] Early optimizations applied")

        except ImportError as e:
            logger.debug(f"RAM cache module not available: {e}")
        except Exception as e:
            logger.warning(f"Early optimizations failed: {e}")

    def _detect_hardware(self):
        """Phase 1: Hardware erkennen und analysieren"""
        logger.info("")
        logger.info("[Phase 1/5] Hardware-Erkennung...")
        logger.info("-" * 40)

        try:
            from ailinux_client.core.hardware_detect import (
                hardware_detector, get_qt_hints, HardwareInfo
            )

            # Hardware erkennen
            self.hw_info = hardware_detector.detect_all()
            self.qt_hints = get_qt_hints()

            # Zusammenfassung ausgeben
            cpu = self.hw_info.cpu
            logger.info(f"CPU: {cpu.model}")
            logger.info(f"  Kerne: {cpu.cores} physisch, {cpu.threads} Threads")
            logger.info(f"  Frequenz: {cpu.frequency_mhz:.0f} MHz (max {cpu.frequency_max_mhz:.0f} MHz)")

            # Befehlssätze
            features = []
            if cpu.avx512:
                features.append("AVX-512")
            elif cpu.avx2:
                features.append("AVX2")
            elif cpu.avx:
                features.append("AVX")
            if cpu.sse4_2:
                features.append("SSE4.2")
            if cpu.aes:
                features.append("AES-NI")
            if cpu.fma:
                features.append("FMA")

            logger.info(f"  Befehlssätze: {', '.join(features) if features else 'Basis'}")

            # Memory
            mem = self.hw_info.memory
            logger.info(f"RAM: {mem.total_mb} MB total, {mem.available_mb} MB verfügbar")
            if mem.type != "Unknown":
                logger.info(f"  Typ: {mem.type} @ {mem.speed_mhz} MHz")

            # GPU(s)
            for i, gpu in enumerate(self.hw_info.gpus):
                logger.info(f"GPU {i+1}: {gpu.vendor} {gpu.model}")
                if gpu.vram_mb:
                    logger.info(f"  VRAM: {gpu.vram_mb} MB")
                if gpu.opengl_version:
                    logger.info(f"  OpenGL: {gpu.opengl_version}")
                if gpu.vulkan_version:
                    logger.info(f"  Vulkan: {gpu.vulkan_version}")
                if gpu.cuda_version:
                    logger.info(f"  CUDA: {gpu.cuda_version}")

            # Storage
            for storage in self.hw_info.storage[:2]:  # Max 2 anzeigen
                logger.info(f"Storage: {storage.type} {storage.size_gb:.0f}GB ({storage.model or storage.device})")

            logger.info(f"System: {self.hw_info.distro}")
            logger.info(f"Kernel: {self.hw_info.kernel}")

        except Exception as e:
            logger.warning(f"Hardware-Erkennung fehlgeschlagen: {e}")
            logger.warning("Verwende Standard-Einstellungen")
            self.hw_info = None
            self.qt_hints = {}

    def _optimize_resources(self):
        """Phase 2: Ressourcen basierend auf Hardware optimieren"""
        logger.info("")
        logger.info("[Phase 2/5] Ressourcen-Optimierung...")
        logger.info("-" * 40)

        if not self.hw_info:
            logger.info("Keine Hardware-Info verfügbar, überspringe Optimierung")
            return

        # Performance-Tier bestimmen
        tier = self.qt_hints.get('performance_tier', 'medium')
        logger.info(f"Performance-Tier: {tier.upper()}")

        # Thread-Anzahl
        threads = self.qt_hints.get('thread_count', 4)
        logger.info(f"Empfohlene Threads: {threads}")

        # GPU-Beschleunigung
        gpu_accel = self.hw_info.gpu_acceleration
        logger.info(f"GPU-Beschleunigung: {'Ja' if gpu_accel else 'Nein'}")

        # Cache-Größe basierend auf verfügbarem RAM
        cache_mb = self.qt_hints.get('cache_size_mb', 128)
        logger.info(f"Cache-Größe: {cache_mb} MB")

        # Speichere Optimierungen in Umgebungsvariablen für Module
        os.environ['AILINUX_PERF_TIER'] = tier
        os.environ['AILINUX_THREADS'] = str(threads)
        os.environ['AILINUX_GPU_ACCEL'] = '1' if gpu_accel else '0'
        os.environ['AILINUX_CACHE_MB'] = str(cache_mb)

        # CPU-spezifische Optimierungen
        cpu = self.hw_info.cpu
        if cpu.avx2:
            os.environ['AILINUX_SIMD'] = 'avx2'
            logger.info("SIMD-Optimierung: AVX2 aktiviert")
        elif cpu.avx:
            os.environ['AILINUX_SIMD'] = 'avx'
            logger.info("SIMD-Optimierung: AVX aktiviert")
        elif cpu.sse4_2:
            os.environ['AILINUX_SIMD'] = 'sse4'
            logger.info("SIMD-Optimierung: SSE4.2 aktiviert")

    def _setup_qt_environment(self):
        """Phase 3: Qt-Umgebungsvariablen setzen"""
        logger.info("")
        logger.info("[Phase 3/5] Qt-Umgebung konfigurieren...")
        logger.info("-" * 40)

        # Basis Qt-Einstellungen
        use_opengl = self.qt_hints.get('use_opengl', False)

        if use_opengl:
            # OpenGL-Beschleunigung aktivieren
            os.environ.setdefault('QT_QUICK_BACKEND', 'opengl')
            os.environ.setdefault('QSG_RENDER_LOOP', 'basic')
            logger.info("Qt Backend: OpenGL (Hardware-beschleunigt)")

            # WebEngine GPU-Flags
            chromium_flags = [
                '--enable-gpu-rasterization',
                '--enable-native-gpu-memory-buffers',
                '--enable-accelerated-video-decode',
                '--enable-accelerated-mjpeg-decode',
                '--enable-zero-copy',
            ]

            # NVIDIA-spezifische Optimierungen
            if self.hw_info and any(g.vendor == 'NVIDIA' for g in self.hw_info.gpus):
                chromium_flags.append('--enable-features=VaapiVideoDecoder')
                logger.info("NVIDIA-Optimierungen aktiviert")

            os.environ.setdefault('QTWEBENGINE_CHROMIUM_FLAGS', ' '.join(chromium_flags))

        else:
            # Software-Rendering
            os.environ.setdefault('QT_QUICK_BACKEND', 'software')
            os.environ.setdefault('LIBGL_ALWAYS_SOFTWARE', '1')
            os.environ.setdefault('QTWEBENGINE_CHROMIUM_FLAGS', '--disable-gpu')
            logger.info("Qt Backend: Software (kein GPU)")

        # Thread-Pool
        thread_count = self.qt_hints.get('thread_count', 4)
        os.environ.setdefault('QT_THREAD_COUNT', str(thread_count))
        logger.info(f"Qt Thread-Pool: {thread_count} Threads")

        # Performance-Tier spezifische Einstellungen
        tier = self.qt_hints.get('performance_tier', 'medium')

        if tier == 'high':
            os.environ.setdefault('QT_ENABLE_HIGHDPI_SCALING', '1')
            os.environ.setdefault('QT_SCALE_FACTOR_ROUNDING_POLICY', 'PassThrough')
            os.environ.setdefault('QSG_RENDER_TIMING', '1')
            logger.info("High-Performance Modus: Alle Effekte aktiviert")

        elif tier == 'low':
            os.environ.setdefault('QT_QUICK_CONTROLS_STYLE', 'Basic')
            os.environ.setdefault('QT_ENABLE_GLYPH_CACHE_WORKAROUND', '1')
            os.environ.setdefault('QT_REDUCE_ANIMATION', '1')
            logger.info("Low-Performance Modus: Effekte reduziert")

        else:
            logger.info("Medium-Performance Modus: Standard-Einstellungen")

    def _init_modules(self):
        """Phase 4: Module initialisieren"""
        logger.info("")
        logger.info("[Phase 4/5] Module initialisieren...")
        logger.info("-" * 40)

        # Core-Module prüfen
        modules_status = {}

        # API Client
        try:
            from ailinux_client.core.api_client import APIClient
            modules_status['API Client'] = 'OK'
        except ImportError as e:
            modules_status['API Client'] = f'FEHLER: {e}'

        # Hardware Detect
        try:
            from ailinux_client.core.hardware_detect import hardware_detector
            modules_status['Hardware Detect'] = 'OK'
        except ImportError as e:
            modules_status['Hardware Detect'] = f'FEHLER: {e}'

        # Tier Manager
        try:
            from ailinux_client.core.tier_manager import get_tier_manager
            modules_status['Tier Manager'] = 'OK'
        except ImportError as e:
            modules_status['Tier Manager'] = f'FEHLER: {e}'

        # CLI Agents
        try:
            from ailinux_client.core.cli_agents import agent_detector
            modules_status['CLI Agents'] = 'OK'
        except ImportError as e:
            modules_status['CLI Agents'] = f'FEHLER: {e}'

        # UI Module
        try:
            from ailinux_client.ui.main_window import MainWindow
            modules_status['Main Window'] = 'OK'
        except ImportError as e:
            modules_status['Main Window'] = f'FEHLER: {e}'

        # Status ausgeben
        for module, status in modules_status.items():
            icon = "✓" if status == 'OK' else "✗"
            logger.info(f"  {icon} {module}: {status}")

        # Prüfen ob kritische Module fehlen
        critical = ['API Client', 'Main Window']
        for mod in critical:
            if modules_status.get(mod, '').startswith('FEHLER'):
                raise ImportError(f"Kritisches Modul fehlt: {mod}")

    def _start_application(self):
        """Phase 5: Application starten"""
        logger.info("")
        logger.info("[Phase 5/5] Application starten...")
        logger.info("-" * 40)

        elapsed = time.time() - self.start_time
        logger.info(f"Bootstrap-Zeit: {elapsed:.2f}s")

        # Re-enable GC after startup
        try:
            from ailinux_client.core.ram_cache import enable_gc
            enable_gc()
            logger.info("GC re-enabled after startup")
        except ImportError:
            pass

        logger.info("")
        logger.info("=" * 60)
        logger.info("Starte AILinux Client...")
        logger.info("=" * 60)
        logger.info("")

        # Jetzt main() aufrufen mit vorbereiteter Umgebung
        from ailinux_client.main import main
        return main()


def show_hardware_info():
    """Zeigt nur Hardware-Info und beendet"""
    try:
        from ailinux_client.core.hardware_detect import hardware_detector
        print(hardware_detector.get_summary())
        return 0
    except Exception as e:
        print(f"Hardware-Erkennung fehlgeschlagen: {e}")
        return 1


def _benchmark_cpu_task(_):
    """CPU-intensive task for benchmarking (module-level for pickling)"""
    total = 0
    for i in range(1000000):
        total += i * i
    return total


def run_benchmark():
    """Führt einen kurzen Performance-Benchmark durch"""
    import time
    import multiprocessing

    print("AILinux Performance Benchmark")
    print("=" * 50)

    # CPU Benchmark
    print("\n[CPU Benchmark]")

    # Single-threaded
    start = time.time()
    _benchmark_cpu_task(0)
    single_time = time.time() - start
    print(f"  Single-Thread: {single_time:.3f}s")

    # Multi-threaded
    cpu_count = multiprocessing.cpu_count()
    start = time.time()
    with multiprocessing.Pool(cpu_count) as pool:
        pool.map(_benchmark_cpu_task, range(cpu_count))
    multi_time = time.time() - start
    print(f"  Multi-Thread ({cpu_count} cores): {multi_time:.3f}s")
    print(f"  Speedup: {single_time / multi_time:.2f}x")

    # Memory Benchmark
    print("\n[Memory Benchmark]")
    start = time.time()
    data = [0] * 10000000  # 10M integers
    alloc_time = time.time() - start
    print(f"  Allokation (10M items): {alloc_time:.3f}s")

    start = time.time()
    total = sum(data)
    sum_time = time.time() - start
    print(f"  Summierung: {sum_time:.3f}s")
    del data

    # Disk I/O (simple)
    print("\n[Disk I/O Benchmark]")
    import tempfile
    test_data = b"x" * (1024 * 1024)  # 1MB

    with tempfile.NamedTemporaryFile(delete=True) as f:
        start = time.time()
        for _ in range(10):
            f.write(test_data)
        f.flush()
        write_time = time.time() - start
        print(f"  Write (10MB): {write_time:.3f}s ({10/write_time:.1f} MB/s)")

        f.seek(0)
        start = time.time()
        while f.read(1024 * 1024):
            pass
        read_time = time.time() - start
        print(f"  Read (10MB): {read_time:.3f}s ({10/read_time:.1f} MB/s)")

    print("\nBenchmark abgeschlossen!")
    return 0


if __name__ == "__main__":
    # Schnelle Argument-Prüfung vor Bootstrap
    if '--hwinfo' in sys.argv:
        sys.exit(show_hardware_info())

    if '--benchmark' in sys.argv:
        sys.exit(run_benchmark())

    # Normaler Start mit Bootstrap
    bootstrap = HardwareOptimizedBootstrap()
    sys.exit(bootstrap.run())
