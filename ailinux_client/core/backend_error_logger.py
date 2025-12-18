"""
Backend Error Logger
====================

Protokolliert alle Backend-Routen-Fehler in eine Datei.
Die Logdatei wird im Hauptordner (neben run-ailinux.sh) gespeichert.
"""
import os
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass, asdict
from threading import Lock

logger = logging.getLogger("ailinux.backend_errors")


@dataclass
class BackendError:
    """Struktur für einen Backend-Fehler"""
    timestamp: str
    endpoint: str
    method: str
    status_code: int
    error_message: str
    response_body: Optional[str] = None
    request_data: Optional[Dict] = None
    user_id: Optional[str] = None
    tier: Optional[str] = None


class BackendErrorLogger:
    """
    Singleton-Logger für Backend-Fehler.
    
    Speichert alle HTTP-Fehler (4xx, 5xx) in eine JSON-Datei.
    """
    
    _instance = None
    _lock = Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._initialized = True
        self._file_lock = Lock()
        
        # Finde den Hauptordner (wo run-ailinux.sh liegt)
        self.base_dir = self._find_base_dir()
        self.log_file = self.base_dir / "backend_errors.log"
        self.json_file = self.base_dir / "backend_errors.json"
        
        # Erstelle Header in der Log-Datei
        self._init_log_file()
        
        logger.info(f"Backend error logger initialized: {self.log_file}")
    
    def _find_base_dir(self) -> Path:
        """Finde den Hauptordner des Projekts"""
        # Versuche verschiedene Methoden
        candidates = [
            Path(__file__).parent.parent.parent,  # ailinux_client/core -> ailinux_client -> root
            Path.cwd(),
            Path(os.environ.get("AILINUX_BASE_DIR", "")),
        ]
        
        for candidate in candidates:
            if candidate.exists() and (candidate / "run-ailinux.sh").exists():
                return candidate
        
        # Fallback: Aktuelles Verzeichnis oder Home
        return Path.cwd() if (Path.cwd() / "run-ailinux.sh").exists() else Path.home() / ".ailinux"
    
    def _init_log_file(self):
        """Initialisiere die Log-Datei mit Header"""
        if not self.log_file.exists():
            with open(self.log_file, "w") as f:
                f.write("=" * 80 + "\n")
                f.write("AILinux Backend Error Log\n")
                f.write(f"Started: {datetime.now().isoformat()}\n")
                f.write("=" * 80 + "\n\n")
    
    def log_error(
        self,
        endpoint: str,
        method: str,
        status_code: int,
        error_message: str,
        response_body: Optional[str] = None,
        request_data: Optional[Dict] = None,
        user_id: Optional[str] = None,
        tier: Optional[str] = None
    ):
        """
        Protokolliere einen Backend-Fehler.
        
        Args:
            endpoint: API-Endpunkt (z.B. /v1/chat)
            method: HTTP-Methode (GET, POST, etc.)
            status_code: HTTP-Statuscode
            error_message: Fehlermeldung
            response_body: Optional - Response-Body
            request_data: Optional - Request-Daten (ohne sensible Infos)
            user_id: Optional - User-ID
            tier: Optional - User-Tier
        """
        error = BackendError(
            timestamp=datetime.now().isoformat(),
            endpoint=endpoint,
            method=method,
            status_code=status_code,
            error_message=error_message,
            response_body=response_body[:500] if response_body else None,  # Limit size
            request_data=self._sanitize_request(request_data),
            user_id=user_id,
            tier=tier
        )
        
        # Log to file
        self._write_to_log(error)
        self._write_to_json(error)
        
        # Also log to standard logger
        logger.error(f"Backend error: {method} {endpoint} -> {status_code}: {error_message}")
    
    def _sanitize_request(self, data: Optional[Dict]) -> Optional[Dict]:
        """Entferne sensible Daten aus dem Request"""
        if not data:
            return None
        
        sanitized = dict(data)
        sensitive_keys = ["password", "token", "secret", "api_key", "authorization"]
        
        for key in list(sanitized.keys()):
            if any(s in key.lower() for s in sensitive_keys):
                sanitized[key] = "[REDACTED]"
        
        return sanitized
    
    def _write_to_log(self, error: BackendError):
        """Schreibe Fehler in die Text-Log-Datei"""
        with self._file_lock:
            try:
                with open(self.log_file, "a") as f:
                    f.write(f"\n{'─' * 60}\n")
                    f.write(f"[{error.timestamp}]\n")
                    f.write(f"  Endpoint: {error.method} {error.endpoint}\n")
                    f.write(f"  Status:   {error.status_code}\n")
                    f.write(f"  Error:    {error.error_message}\n")
                    if error.user_id:
                        f.write(f"  User:     {error.user_id} ({error.tier})\n")
                    if error.response_body:
                        f.write(f"  Response: {error.response_body[:200]}...\n")
            except Exception as e:
                logger.warning(f"Could not write to error log: {e}")
    
    def _write_to_json(self, error: BackendError):
        """Schreibe Fehler in die JSON-Datei"""
        with self._file_lock:
            try:
                # Lade existierende Fehler
                errors = []
                if self.json_file.exists():
                    try:
                        with open(self.json_file, "r") as f:
                            errors = json.load(f)
                    except json.JSONDecodeError:
                        errors = []
                
                # Füge neuen Fehler hinzu
                errors.append(asdict(error))
                
                # Behalte nur die letzten 1000 Fehler
                if len(errors) > 1000:
                    errors = errors[-1000:]
                
                # Speichere
                with open(self.json_file, "w") as f:
                    json.dump(errors, f, indent=2, ensure_ascii=False)
                    
            except Exception as e:
                logger.warning(f"Could not write to JSON error log: {e}")
    
    def get_recent_errors(self, count: int = 50) -> list:
        """Hole die letzten N Fehler"""
        if not self.json_file.exists():
            return []
        
        try:
            with open(self.json_file, "r") as f:
                errors = json.load(f)
            return errors[-count:]
        except Exception:
            return []
    
    def get_error_summary(self) -> Dict[str, Any]:
        """Erstelle eine Zusammenfassung der Fehler"""
        errors = self.get_recent_errors(1000)
        
        if not errors:
            return {"total": 0, "by_endpoint": {}, "by_status": {}}
        
        by_endpoint = {}
        by_status = {}
        
        for error in errors:
            endpoint = error.get("endpoint", "unknown")
            status = error.get("status_code", 0)
            
            by_endpoint[endpoint] = by_endpoint.get(endpoint, 0) + 1
            by_status[status] = by_status.get(status, 0) + 1
        
        return {
            "total": len(errors),
            "by_endpoint": dict(sorted(by_endpoint.items(), key=lambda x: -x[1])),
            "by_status": dict(sorted(by_status.items(), key=lambda x: -x[1])),
            "first_error": errors[0].get("timestamp") if errors else None,
            "last_error": errors[-1].get("timestamp") if errors else None,
        }
    
    def clear_logs(self):
        """Lösche alle Logs"""
        with self._file_lock:
            if self.log_file.exists():
                self.log_file.unlink()
            if self.json_file.exists():
                self.json_file.unlink()
            self._init_log_file()
            logger.info("Backend error logs cleared")


# Singleton-Instanz
_error_logger: Optional[BackendErrorLogger] = None


def get_backend_error_logger() -> BackendErrorLogger:
    """Hole die Singleton-Instanz des Error-Loggers"""
    global _error_logger
    if _error_logger is None:
        _error_logger = BackendErrorLogger()
    return _error_logger


def log_backend_error(
    endpoint: str,
    method: str,
    status_code: int,
    error_message: str,
    **kwargs
):
    """Convenience-Funktion zum Loggen eines Backend-Fehlers"""
    get_backend_error_logger().log_error(
        endpoint=endpoint,
        method=method,
        status_code=status_code,
        error_message=error_message,
        **kwargs
    )



