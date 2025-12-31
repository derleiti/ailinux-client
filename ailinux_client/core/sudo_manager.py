"""
AILinux Sudo Manager - Sichere sudo-Integration
"""
import subprocess
import getpass
import logging
from typing import Optional, Tuple, List
import os
import time

logger = logging.getLogger("ailinux.sudo_manager")

class SudoManager:
    def __init__(self):
        self._cached_password: Optional[str] = None
        self._cache_timeout: int = 300
        self._last_auth_time: float = 0
    
    def _is_cache_valid(self) -> bool:
        if self._cached_password is None:
            return False
        return (time.time() - self._last_auth_time) < self._cache_timeout
    
    def _prompt_password(self, reason: str = "") -> Optional[str]:
        print("\n" + "=" * 50)
        print("ROOT-BERECHTIGUNG ERFORDERLICH")
        if reason:
            print(f"   Grund: {reason}")
        print("=" * 50)
        try:
            password = getpass.getpass("Lokales Root-Passwort: ")
            return password
        except (KeyboardInterrupt, EOFError):
            print("\nAbgebrochen")
            return None
    
    def _verify_password(self, password: str) -> bool:
        try:
            result = subprocess.run(
                ["sudo", "-S", "-v"],
                input=password + "\n",
                capture_output=True, text=True, timeout=10
            )
            return result.returncode == 0
        except:
            return False
    
    def get_password(self, reason: str = "") -> Optional[str]:
        if self._is_cache_valid():
            return self._cached_password
        password = self._prompt_password(reason)
        if password and self._verify_password(password):
            self._cached_password = password
            self._last_auth_time = time.time()
            print("Authentifizierung erfolgreich")
            return password
        print("Falsches Passwort")
        return None
    
    def clear_cache(self):
        self._cached_password = None
        self._last_auth_time = 0
    
    def run_sudo(self, command: List[str], reason: str = "") -> Tuple[bool, str, str]:
        password = self.get_password(reason)
        if not password:
            return False, "", "Keine Berechtigung"
        try:
            result = subprocess.run(
                ["sudo", "-S"] + command,
                input=password + "\n",
                capture_output=True, text=True, timeout=60
            )
            return result.returncode == 0, result.stdout, result.stderr
        except Exception as e:
            return False, "", str(e)
    
    def restart_service(self, service: str) -> bool:
        success, _, stderr = self.run_sudo(
            ["systemctl", "restart", service],
            reason=f"Service {service} neustarten"
        )
        print(f"Service {service} neugestartet" if success else f"Fehler: {stderr}")
        return success
    
    def write_protected_file(self, path: str, content: str) -> bool:
        import tempfile
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            f.write(content)
            temp_path = f.name
        try:
            success, _, _ = self.run_sudo(["cp", temp_path, path], f"Datei {path} schreiben")
            return success
        finally:
            os.unlink(temp_path)

_sudo_manager = None

def get_sudo_manager() -> SudoManager:
    global _sudo_manager
    if _sudo_manager is None:
        _sudo_manager = SudoManager()
    return _sudo_manager

def sudo_run(cmd, reason=""): return get_sudo_manager().run_sudo(cmd, reason)
def sudo_restart_service(svc): return get_sudo_manager().restart_service(svc)
def sudo_write_file(path, content): return get_sudo_manager().write_protected_file(path, content)
