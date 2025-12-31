"""
Tor Manager - Verwaltet Tor-Daemon und Proxy-Konfiguration

Features:
- Tor Daemon starten/stoppen
- SOCKS5 Proxy für Browser
- .onion Domain Support
- Circuit-Management
"""

import subprocess
import os
import logging
import tempfile
import time
import socket
from pathlib import Path
from typing import Optional, Callable
from PyQt6.QtCore import QObject, pyqtSignal, QThread

logger = logging.getLogger("ailinux.tor")


class TorProcess(QThread):
    """Tor-Daemon als Background-Thread"""
    
    started = pyqtSignal()
    stopped = pyqtSignal()
    error = pyqtSignal(str)
    circuit_ready = pyqtSignal()
    
    def __init__(self, data_dir: Path = None):
        super().__init__()
        self.data_dir = data_dir or Path.home() / ".config" / "ailinux" / "tor"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        self.process: Optional[subprocess.Popen] = None
        self._running = False
        self.socks_port = 9050
        self.control_port = 9051
        
    def run(self):
        """Tor-Daemon starten"""
        try:
            # Tor Konfiguration
            torrc_path = self.data_dir / "torrc"
            torrc_content = f"""
# AILinux Tor Configuration
SocksPort {self.socks_port}
ControlPort {self.control_port}
DataDirectory {self.data_dir}

# Performance
CircuitBuildTimeout 30
LearnCircuitBuildTimeout 0
MaxCircuitDirtiness 600

# Privacy
CookieAuthentication 1
SafeSocks 1

# Logging
Log notice file {self.data_dir}/tor.log
"""
            torrc_path.write_text(torrc_content)
            
            # Tor starten
            self.process = subprocess.Popen(
                ["tor", "-f", str(torrc_path)],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True
            )
            
            self._running = True
            logger.info(f"Tor started with PID {self.process.pid}")
            
            # Warten auf Bootstrap
            for line in iter(self.process.stdout.readline, ''):
                if not self._running:
                    break
                logger.debug(f"Tor: {line.strip()}")
                
                if "Bootstrapped 100%" in line:
                    self.circuit_ready.emit()
                    self.started.emit()
                    logger.info("Tor circuit ready!")
                    
            self.process.wait()
            self._running = False
            self.stopped.emit()
            
        except FileNotFoundError:
            self.error.emit("Tor nicht installiert! Bitte: sudo apt install tor")
            logger.error("Tor binary not found")
        except Exception as e:
            self.error.emit(str(e))
            logger.error(f"Tor error: {e}")
    
    def stop(self):
        """Tor-Daemon stoppen"""
        self._running = False
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
            self.process = None
            logger.info("Tor stopped")
    
    def is_running(self) -> bool:
        """Prüfe ob Tor läuft"""
        return self._running and self.process and self.process.poll() is None


class TorManager(QObject):
    """
    Hauptklasse für Tor-Integration im AILinux Browser.
    
    Features:
    - Tor Ein/Aus Toggle
    - .onion Support
    - New Identity (neuer Circuit)
    - Status-Monitoring
    """
    
    # Signals
    tor_started = pyqtSignal()
    tor_stopped = pyqtSignal()
    tor_error = pyqtSignal(str)
    status_changed = pyqtSignal(str)  # "connected", "connecting", "disconnected", "error"
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.tor_process: Optional[TorProcess] = None
        self._enabled = False
        self._status = "disconnected"
        
        # Proxy Settings
        self.socks_host = "127.0.0.1"
        self.socks_port = 9050
        
    @property
    def enabled(self) -> bool:
        return self._enabled
    
    @property
    def status(self) -> str:
        return self._status
    
    def _set_status(self, status: str):
        self._status = status
        self.status_changed.emit(status)
        logger.info(f"Tor status: {status}")
    
    def start_tor(self) -> bool:
        """Tor-Daemon starten"""
        if self.tor_process and self.tor_process.is_running():
            logger.warning("Tor already running")
            return True
        
        self._set_status("connecting")
        
        self.tor_process = TorProcess()
        self.tor_process.started.connect(self._on_tor_started)
        self.tor_process.stopped.connect(self._on_tor_stopped)
        self.tor_process.error.connect(self._on_tor_error)
        self.tor_process.circuit_ready.connect(self._on_circuit_ready)
        self.tor_process.start()
        
        return True
    
    def stop_tor(self):
        """Tor-Daemon stoppen"""
        if self.tor_process:
            self.tor_process.stop()
            self.tor_process = None
        self._enabled = False
        self._set_status("disconnected")
        self.tor_stopped.emit()
    
    def toggle(self) -> bool:
        """Tor Ein/Aus umschalten"""
        if self._enabled:
            self.stop_tor()
            return False
        else:
            self.start_tor()
            return True
    
    def _on_tor_started(self):
        self._enabled = True
        self._set_status("connected")
        self.tor_started.emit()
    
    def _on_tor_stopped(self):
        self._enabled = False
        self._set_status("disconnected")
    
    def _on_tor_error(self, error: str):
        self._set_status("error")
        self.tor_error.emit(error)
    
    def _on_circuit_ready(self):
        self._set_status("connected")
    
    def new_identity(self):
        """Neuen Tor-Circuit anfordern (neue IP)"""
        try:
            import socket
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.connect((self.socks_host, 9051))  # Control Port
                s.sendall(b'AUTHENTICATE ""\r\n')
                s.recv(1024)
                s.sendall(b'SIGNAL NEWNYM\r\n')
                response = s.recv(1024)
                if b"250 OK" in response:
                    logger.info("New Tor identity requested")
                    return True
        except Exception as e:
            logger.error(f"Failed to request new identity: {e}")
        return False
    
    def check_connection(self) -> bool:
        """Prüfe ob Tor-Verbindung funktioniert"""
        try:
            import socks
            import socket
            
            s = socks.socksocket()
            s.set_proxy(socks.SOCKS5, self.socks_host, self.socks_port)
            s.settimeout(10)
            s.connect(("check.torproject.org", 80))
            s.close()
            return True
        except ImportError:
            # PySocks nicht installiert - manueller Check
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(5)
                result = sock.connect_ex((self.socks_host, self.socks_port))
                sock.close()
                return result == 0
            except:
                return False
        except Exception as e:
            logger.error(f"Tor connection check failed: {e}")
            return False
    
    def get_proxy_config(self) -> dict:
        """Proxy-Konfiguration für Qt6 WebEngine"""
        if not self._enabled:
            return {"type": "direct"}
        
        return {
            "type": "socks5",
            "host": self.socks_host,
            "port": self.socks_port
        }


def apply_tor_proxy_to_browser(browser_widget, tor_manager: TorManager):
    """
    Wendet Tor-Proxy auf einen BrowserWidget an.
    
    WICHTIG: Für .onion-Support muss DNS über Tor gehen!
    Qt6 WebEngine nutzt Chromium, das SOCKS5h (mit DNS) unterstützt.
    """
    from PyQt6.QtNetwork import QNetworkProxy
    
    if tor_manager.enabled:
        # SOCKS5 Proxy mit Remote-DNS (WICHTIG für .onion!)
        proxy = QNetworkProxy()
        proxy.setType(QNetworkProxy.ProxyType.Socks5Proxy)
        proxy.setHostName(tor_manager.socks_host)
        proxy.setPort(tor_manager.socks_port)
        
        # Setze Proxy global für alle Qt-Netzwerk-Anfragen
        QNetworkProxy.setApplicationProxy(proxy)
        
        # Für WebEngine brauchen wir zusätzlich Chromium-Flags
        import os
        os.environ['QTWEBENGINE_CHROMIUM_FLAGS'] = (
            os.environ.get('QTWEBENGINE_CHROMIUM_FLAGS', '') +
            f' --proxy-server=socks5://{tor_manager.socks_host}:{tor_manager.socks_port}'
            ' --host-resolver-rules="MAP * ~NOTFOUND , EXCLUDE 127.0.0.1"'
        )
        
        logger.info("Tor proxy applied to browser (SOCKS5 with remote DNS)")
    else:
        # Direktverbindung
        QNetworkProxy.setApplicationProxy(QNetworkProxy(QNetworkProxy.ProxyType.NoProxy))
        logger.info("Direct connection (no proxy)")


# Singleton für globalen Zugriff
_tor_manager_instance: Optional[TorManager] = None

def get_tor_manager() -> TorManager:
    """Globalen TorManager abrufen"""
    global _tor_manager_instance
    if _tor_manager_instance is None:
        _tor_manager_instance = TorManager()
    return _tor_manager_instance
