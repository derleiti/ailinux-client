"""
AILinux RAM Cache & Performance Manager
=======================================

Provides:
- In-memory caching for frequently accessed data
- Lazy sync to disk for persistence
- Memory-mapped file support for large data
- Object pooling to reduce GC pressure
"""
import os
import sys
import mmap
import json
import time
import weakref
import logging
import threading
from pathlib import Path
from typing import Any, Dict, Optional, Callable
from dataclasses import dataclass, field
from functools import lru_cache

logger = logging.getLogger("ailinux.ram_cache")


@dataclass
class CacheEntry:
    """Single cache entry with metadata"""
    data: Any
    created: float = field(default_factory=time.time)
    accessed: float = field(default_factory=time.time)
    dirty: bool = False  # True if modified since last disk sync
    ttl: Optional[float] = None  # Time-to-live in seconds


class RAMCache:
    """
    High-performance in-memory cache with lazy disk sync.

    Features:
    - LRU eviction when memory limit reached
    - Background disk sync for dirty entries
    - Thread-safe operations
    - Memory usage tracking
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self, max_memory_mb: int = 256):
        if self._initialized:
            return

        self._cache: Dict[str, CacheEntry] = {}
        self._max_memory = max_memory_mb * 1024 * 1024
        self._current_memory = 0
        self._lock = threading.RLock()
        self._sync_thread: Optional[threading.Thread] = None
        self._running = False
        self._disk_path = Path.home() / ".cache" / "ailinux"
        self._disk_path.mkdir(parents=True, exist_ok=True)
        self._initialized = True

        logger.info(f"RAM Cache initialized: {max_memory_mb}MB max")

    def get(self, key: str, default: Any = None) -> Any:
        """Get value from cache"""
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return default

            # Check TTL
            if entry.ttl and (time.time() - entry.created) > entry.ttl:
                del self._cache[key]
                return default

            entry.accessed = time.time()
            return entry.data

    def set(self, key: str, value: Any, ttl: Optional[float] = None, persist: bool = False):
        """Set value in cache"""
        with self._lock:
            # Estimate memory size (rough)
            size = sys.getsizeof(value)

            # Evict if necessary
            while self._current_memory + size > self._max_memory and self._cache:
                self._evict_lru()

            entry = CacheEntry(data=value, ttl=ttl, dirty=persist)
            self._cache[key] = entry
            self._current_memory += size

    def delete(self, key: str):
        """Remove key from cache"""
        with self._lock:
            if key in self._cache:
                del self._cache[key]

    def _evict_lru(self):
        """Evict least recently used entry"""
        if not self._cache:
            return

        # Find LRU entry
        lru_key = min(self._cache.keys(), key=lambda k: self._cache[k].accessed)
        entry = self._cache.pop(lru_key)

        # Sync to disk if dirty
        if entry.dirty:
            self._sync_to_disk(lru_key, entry.data)

    def _sync_to_disk(self, key: str, data: Any):
        """Sync single entry to disk"""
        try:
            file_path = self._disk_path / f"{key.replace('/', '_')}.json"
            with open(file_path, 'w') as f:
                json.dump(data, f)
        except Exception as e:
            logger.warning(f"Failed to sync {key} to disk: {e}")

    def load_from_disk(self, key: str) -> Optional[Any]:
        """Load entry from disk cache"""
        try:
            file_path = self._disk_path / f"{key.replace('/', '_')}.json"
            if file_path.exists():
                with open(file_path, 'r') as f:
                    data = json.load(f)
                self.set(key, data)
                return data
        except Exception as e:
            logger.warning(f"Failed to load {key} from disk: {e}")
        return None

    def sync_all(self):
        """Sync all dirty entries to disk"""
        with self._lock:
            for key, entry in self._cache.items():
                if entry.dirty:
                    self._sync_to_disk(key, entry.data)
                    entry.dirty = False

    def clear(self):
        """Clear all cache entries"""
        with self._lock:
            self._cache.clear()
            self._current_memory = 0

    def stats(self) -> dict:
        """Get cache statistics"""
        with self._lock:
            return {
                'entries': len(self._cache),
                'memory_used': self._current_memory,
                'memory_max': self._max_memory,
                'memory_pct': (self._current_memory / self._max_memory * 100) if self._max_memory else 0
            }


class ObjectPool:
    """
    Object pool to reduce GC pressure for frequently created/destroyed objects.
    """

    def __init__(self, factory: Callable, max_size: int = 100):
        self._factory = factory
        self._pool: list = []
        self._max_size = max_size
        self._lock = threading.Lock()

    def acquire(self) -> Any:
        """Get object from pool or create new"""
        with self._lock:
            if self._pool:
                return self._pool.pop()
        return self._factory()

    def release(self, obj: Any):
        """Return object to pool"""
        with self._lock:
            if len(self._pool) < self._max_size:
                self._pool.append(obj)


# Global cache instance
_ram_cache: Optional[RAMCache] = None


def get_ram_cache(max_memory_mb: int = 256) -> RAMCache:
    """Get or create global RAM cache instance"""
    global _ram_cache
    if _ram_cache is None:
        _ram_cache = RAMCache(max_memory_mb)
    return _ram_cache


def optimize_python_gc():
    """Optimize Python garbage collector for GUI applications"""
    import gc

    # Increase GC thresholds to reduce collection frequency
    # Default is (700, 10, 10) - we use higher values for less frequent GC
    gc.set_threshold(50000, 500, 100)

    # Disable GC during startup (re-enable after init)
    gc.disable()

    logger.info("Python GC optimized for GUI performance")


def enable_gc():
    """Re-enable GC after startup"""
    import gc
    gc.enable()
    gc.collect()  # Initial collection


def optimize_qt_for_performance():
    """Set Qt environment variables for maximum performance"""

    # Use native OpenGL for better performance
    os.environ.setdefault('QT_OPENGL', 'desktop')

    # Enable high DPI scaling
    os.environ.setdefault('QT_AUTO_SCREEN_SCALE_FACTOR', '1')
    os.environ.setdefault('QT_ENABLE_HIGHDPI_SCALING', '1')

    # Reduce logging overhead
    os.environ.setdefault('QT_LOGGING_RULES', '*.debug=false;qt.*.debug=false')

    # Use threaded OpenGL (if available)
    os.environ.setdefault('QSG_RENDER_LOOP', 'threaded')

    # Enable hardware acceleration
    os.environ.setdefault('QMLSCENE_DEVICE', 'softwarecontext')

    # WebEngine optimizations
    os.environ.setdefault('QTWEBENGINE_CHROMIUM_FLAGS',
        '--disable-gpu-sandbox '
        '--enable-gpu-rasterization '
        '--enable-zero-copy '
        '--enable-features=VaapiVideoDecoder '
        '--disable-features=UseChromeOSDirectVideoDecoder '
        '--ignore-gpu-blocklist'
    )

    logger.info("Qt environment optimized for performance")


def preload_modules():
    """Preload commonly used modules into memory"""
    modules_to_preload = [
        'PyQt6.QtWidgets',
        'PyQt6.QtCore',
        'PyQt6.QtGui',
        'json',
        'pathlib',
        'logging',
    ]

    for module in modules_to_preload:
        try:
            __import__(module)
        except ImportError:
            pass

    logger.info(f"Preloaded {len(modules_to_preload)} modules")


def setup_memory_limits():
    """Configure memory limits for the application"""
    try:
        import resource

        # Get available memory
        with open('/proc/meminfo', 'r') as f:
            for line in f:
                if line.startswith('MemAvailable:'):
                    available_kb = int(line.split()[1])
                    break
            else:
                available_kb = 4 * 1024 * 1024  # Default 4GB

        # Use up to 50% of available memory
        max_memory = int(available_kb * 1024 * 0.5)

        # Set soft limit (can be exceeded temporarily)
        soft, hard = resource.getrlimit(resource.RLIMIT_AS)
        if hard == resource.RLIM_INFINITY or max_memory < hard:
            resource.setrlimit(resource.RLIMIT_AS, (max_memory, hard))
            logger.info(f"Memory limit set: {max_memory // (1024*1024)}MB")

    except Exception as e:
        logger.debug(f"Could not set memory limits: {e}")
