"""
AILinux Client - DevOps Syslogger
=================================
Zentrales Logging für Client-App mit:
- Lokales Rotating File Log
- Remote-Syslog an TriForce Backend
- Strukturierte JSON-Logs
- Log-Level Filtering
- Crash-Reports

Version: 1.0.0
"""

import logging
import logging.handlers
import json
import socket
import sys
import traceback
import platform
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any
from dataclasses import dataclass, asdict
from enum import Enum
import threading
import queue
import atexit


class LogLevel(Enum):
    DEBUG = 10
    INFO = 20
    WARNING = 30
    ERROR = 40
    CRITICAL = 50


@dataclass
class LogEntry:
    """Strukturierter Log-Eintrag"""
    timestamp: str
    level: str
    source: str
    message: str
    client_id: Optional[str] = None
    user_id: Optional[str] = None
    tier: Optional[str] = None
    version: Optional[str] = None
    platform: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    traceback: Optional[str] = None
    
    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, default=str)
    
    def to_syslog(self) -> str:
        """RFC 5424 Syslog Format"""
        pri = 14  # user.info
        if self.level == "ERROR":
            pri = 11  # user.err
        elif self.level == "WARNING":
            pri = 12  # user.warning
        elif self.level == "CRITICAL":
            pri = 10  # user.crit
        elif self.level == "DEBUG":
            pri = 15  # user.debug
            
        hostname = socket.gethostname()
        app = "ailinux-client"
        
        # RFC 5424 Format
        return f"<{pri}>1 {self.timestamp} {hostname} {app} - - - {self.message}"


class RemoteSyslogHandler(logging.Handler):
    """Async Remote Syslog Handler für TriForce Backend"""
    
    def __init__(
        self,
        backend_url: str = "https://api.ailinux.me",
        endpoint: str = "/v1/client/logs",
        buffer_size: int = 100,
        flush_interval: float = 5.0
    ):
        super().__init__()
        self.backend_url = backend_url.rstrip("/")
        self.endpoint = endpoint
        self.buffer_size = buffer_size
        self.flush_interval = flush_interval
        
        self._queue: queue.Queue = queue.Queue(maxsize=1000)
        self._shutdown = threading.Event()
        self._flush_thread: Optional[threading.Thread] = None
        self._token: Optional[str] = None
        self._client_info: Dict[str, Any] = {}
        
        self._start_flush_thread()
        atexit.register(self.close)
    
    def set_auth(self, token: str, client_info: Dict[str, Any] = None):
        """Setzt Auth-Token und Client-Info"""
        self._token = token
        self._client_info = client_info or {}
    
    def _start_flush_thread(self):
        """Startet Background-Thread für Log-Flushing"""
        self._flush_thread = threading.Thread(
            target=self._flush_loop,
            daemon=True,
            name="SyslogFlush"
        )
        self._flush_thread.start()
    
    def _flush_loop(self):
        """Background-Loop für periodisches Flushing"""
        buffer = []
        
        while not self._shutdown.is_set():
            try:
                # Sammle Logs aus Queue
                try:
                    while len(buffer) < self.buffer_size:
                        entry = self._queue.get(timeout=self.flush_interval)
                        buffer.append(entry)
                except queue.Empty:
                    pass
                
                # Flush wenn Buffer nicht leer
                if buffer:
                    self._send_logs(buffer)
                    buffer = []
                    
            except Exception as e:
                # Logging-Fehler nicht propagieren
                sys.stderr.write(f"SyslogFlush error: {e}\n")
    
    def _send_logs(self, entries: list):
        """Sendet Logs an Backend"""
        if not self._token:
            return
            
        try:
            import httpx
            
            payload = {
                "logs": [e.to_json() if hasattr(e, 'to_json') else str(e) for e in entries],
                "client_info": self._client_info
            }
            
            with httpx.Client(timeout=10.0) as client:
                response = client.post(
                    f"{self.backend_url}{self.endpoint}",
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {self._token}",
                        "Content-Type": "application/json"
                    }
                )
                
                if response.status_code not in (200, 201, 202):
                    sys.stderr.write(f"Syslog send failed: {response.status_code}\n")
                    
        except ImportError:
            # httpx nicht verfügbar - fallback zu requests
            try:
                import requests
                response = requests.post(
                    f"{self.backend_url}{self.endpoint}",
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {self._token}",
                        "Content-Type": "application/json"
                    },
                    timeout=10
                )
            except Exception:
                pass
        except Exception as e:
            sys.stderr.write(f"Syslog send error: {e}\n")
    
    def emit(self, record: logging.LogRecord):
        """Verarbeitet Log-Record"""
        try:
            entry = LogEntry(
                timestamp=datetime.utcnow().isoformat() + "Z",
                level=record.levelname,
                source=record.name,
                message=self.format(record),
                client_id=self._client_info.get("client_id"),
                user_id=self._client_info.get("user_id"),
                tier=self._client_info.get("tier"),
                version=self._client_info.get("version"),
                platform=platform.system(),
                metadata={
                    "filename": record.filename,
                    "lineno": record.lineno,
                    "funcName": record.funcName
                },
                traceback=record.exc_text if record.exc_info else None
            )
            
            self._queue.put_nowait(entry)
            
        except queue.Full:
            sys.stderr.write("Syslog queue full, dropping log\n")
        except Exception as e:
            sys.stderr.write(f"Syslog emit error: {e}\n")
    
    def close(self):
        """Cleanup"""
        self._shutdown.set()
        if self._flush_thread and self._flush_thread.is_alive():
            self._flush_thread.join(timeout=2.0)
        super().close()


class DevOpsSyslogger:
    """
    Zentrale Syslogger-Klasse für AILinux Client
    
    Usage:
        from core.syslogger import syslog
        
        syslog.info("App gestartet")
        syslog.error("Verbindung fehlgeschlagen", exc_info=True)
        syslog.devops("Deployment-Event", metadata={"version": "4.2.0"})
    """
    
    _instance: Optional['DevOpsSyslogger'] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
            
        self._initialized = True
        self._logger = logging.getLogger("ailinux.client")
        self._logger.setLevel(logging.DEBUG)
        
        # Verhindere doppelte Handler
        self._logger.handlers.clear()
        
        # Log-Verzeichnis
        self._log_dir = Path.home() / ".ailinux" / "logs"
        self._log_dir.mkdir(parents=True, exist_ok=True)
        
        # 1. Rotating File Handler (lokal)
        self._file_handler = logging.handlers.RotatingFileHandler(
            self._log_dir / "client.log",
            maxBytes=5 * 1024 * 1024,  # 5 MB
            backupCount=5,
            encoding="utf-8"
        )
        self._file_handler.setLevel(logging.DEBUG)
        self._file_handler.setFormatter(logging.Formatter(
            "%(asctime)s|%(levelname)-8s|%(name)-25s|%(filename)s:%(lineno)d|%(message)s"
        ))
        self._logger.addHandler(self._file_handler)
        
        # 2. Console Handler (stderr)
        self._console_handler = logging.StreamHandler(sys.stderr)
        self._console_handler.setLevel(logging.INFO)
        self._console_handler.setFormatter(logging.Formatter(
            "%(levelname)s: %(message)s"
        ))
        self._logger.addHandler(self._console_handler)
        
        # 3. Remote Syslog Handler (async)
        self._remote_handler = RemoteSyslogHandler()
        self._remote_handler.setLevel(logging.WARNING)  # Nur WARNING+ remote
        self._remote_handler.setFormatter(logging.Formatter("%(message)s"))
        self._logger.addHandler(self._remote_handler)
        
        # 4. JSON Log File (für structured logging)
        self._json_handler = logging.handlers.RotatingFileHandler(
            self._log_dir / "client.json.log",
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=3,
            encoding="utf-8"
        )
        self._json_handler.setLevel(logging.DEBUG)
        self._json_handler.setFormatter(JsonFormatter())
        self._logger.addHandler(self._json_handler)
        
        # Crash Handler
        sys.excepthook = self._crash_handler
    
    def set_auth(self, token: str, user_id: str = None, tier: str = None):
        """Setzt Auth für Remote-Logging"""
        import uuid
        
        client_info = {
            "client_id": str(uuid.uuid4())[:8],
            "user_id": user_id,
            "tier": tier,
            "version": self._get_version(),
            "platform": platform.system(),
            "python": platform.python_version()
        }
        
        self._remote_handler.set_auth(token, client_info)
        self.info(f"Syslogger authenticated: user={user_id}, tier={tier}")
    
    def _get_version(self) -> str:
        """Holt Client-Version"""
        try:
            from . import __version__
            return __version__
        except ImportError:
            try:
                from version import VERSION
                return VERSION
            except ImportError:
                return "unknown"
    
    def _crash_handler(self, exc_type, exc_value, exc_tb):
        """Globaler Exception Handler"""
        tb_str = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        
        self._logger.critical(
            f"CRASH: {exc_type.__name__}: {exc_value}",
            extra={"traceback": tb_str}
        )
        
        # Crash-Report speichern
        crash_file = self._log_dir / f"crash_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        crash_file.write_text(tb_str, encoding="utf-8")
        
        # Original excepthook aufrufen
        sys.__excepthook__(exc_type, exc_value, exc_tb)
    
    # === Logging Methods ===
    
    def debug(self, msg: str, **kwargs):
        self._logger.debug(msg, **kwargs)
    
    def info(self, msg: str, **kwargs):
        self._logger.info(msg, **kwargs)
    
    def warning(self, msg: str, **kwargs):
        self._logger.warning(msg, **kwargs)
    
    def error(self, msg: str, exc_info: bool = False, **kwargs):
        self._logger.error(msg, exc_info=exc_info, **kwargs)
    
    def critical(self, msg: str, exc_info: bool = True, **kwargs):
        self._logger.critical(msg, exc_info=exc_info, **kwargs)
    
    def devops(self, msg: str, metadata: Dict[str, Any] = None, level: str = "INFO"):
        """Spezieller DevOps-Log mit Metadaten"""
        extra = {"devops": True, "metadata": metadata or {}}
        getattr(self._logger, level.lower())(f"[DEVOPS] {msg}", extra=extra)
    
    def metric(self, name: str, value: float, unit: str = "", tags: Dict[str, str] = None):
        """Log einer Metrik"""
        self._logger.info(
            f"[METRIC] {name}={value}{unit}",
            extra={"metric": {"name": name, "value": value, "unit": unit, "tags": tags or {}}}
        )
    
    def audit(self, action: str, user: str = None, details: Dict[str, Any] = None):
        """Audit-Log für sicherheitsrelevante Events"""
        self._logger.info(
            f"[AUDIT] {action}",
            extra={"audit": {"action": action, "user": user, "details": details or {}}}
        )
    
    def get_log_path(self) -> Path:
        """Gibt Log-Verzeichnis zurück"""
        return self._log_dir
    
    def get_recent_logs(self, lines: int = 100) -> list:
        """Holt letzte Log-Zeilen"""
        log_file = self._log_dir / "client.log"
        if not log_file.exists():
            return []
        
        with open(log_file, "r", encoding="utf-8") as f:
            return f.readlines()[-lines:]
    
    def set_console_level(self, level: str):
        """Ändert Console-Log-Level"""
        self._console_handler.setLevel(getattr(logging, level.upper()))
    
    def set_remote_level(self, level: str):
        """Ändert Remote-Log-Level"""
        self._remote_handler.setLevel(getattr(logging, level.upper()))


class JsonFormatter(logging.Formatter):
    """JSON Log Formatter"""
    
    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "source": record.name,
            "message": record.getMessage(),
            "filename": record.filename,
            "lineno": record.lineno,
            "funcName": record.funcName
        }
        
        # Extra-Felder hinzufügen
        for key in ["devops", "metadata", "metric", "audit", "traceback"]:
            if hasattr(record, key):
                log_data[key] = getattr(record, key)
        
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        
        return json.dumps(log_data, ensure_ascii=False, default=str)


# === Singleton Export ===
syslog = DevOpsSyslogger()


# === Convenience Functions ===
def get_logger(name: str) -> logging.Logger:
    """Holt einen Child-Logger"""
    return logging.getLogger(f"ailinux.client.{name}")


def log_function_call(func):
    """Decorator für Function-Call Logging"""
    import functools
    
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        syslog.debug(f"CALL: {func.__name__}({args}, {kwargs})")
        try:
            result = func(*args, **kwargs)
            syslog.debug(f"RETURN: {func.__name__} -> {type(result).__name__}")
            return result
        except Exception as e:
            syslog.error(f"EXCEPTION: {func.__name__} -> {e}", exc_info=True)
            raise
    
    return wrapper
