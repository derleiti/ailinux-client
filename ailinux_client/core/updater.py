"""
AILinux Client Auto-Updater v2.0
================================

Prüft Server auf neue Versionen und installiert .deb Updates.

Features:
- Check beim Start
- Auto-Check alle 30 Minuten
- Manueller Check
- Download .deb Paket
- Frage: Jetzt installieren oder beim nächsten Start

Versionierung:
- x.x.NUM - Kleine Updates (Patches, Bugfixes)
- x.NUM.x - Größere Updates (Features)
- NUM.x.x - Komplette Überarbeitung (Major)
"""
import logging
import os
import sys
import subprocess
import hashlib
import tempfile
import shutil
from pathlib import Path
from typing import Optional, Dict, Tuple, Callable
from datetime import datetime
import threading
import time

logger = logging.getLogger("ailinux.updater")

# Update-Server
UPDATE_BASE_URL = "https://api.ailinux.me"
VERSION_ENDPOINT = "/v1/client/update/version"
DOWNLOAD_ENDPOINT = "/v1/client/update/download"

# Update-Interval (30 Minuten)
AUTO_CHECK_INTERVAL = 30 * 60

# Lokaler Download-Ordner
UPDATE_CACHE_DIR = Path.home() / ".cache" / "ailinux" / "updates"


class UpdateInfo:
    """Update-Informationen vom Server"""
    def __init__(self, version: str, checksum: str, build_date: str,
                 download_url: str, changelog: str = "", filename: str = ""):
        self.version = version
        self.checksum = checksum
        self.build_date = build_date
        self.download_url = download_url
        self.changelog = changelog
        self.filename = filename or f"ailinux-client_{version}_amd64.deb"
        
    def __repr__(self):
        return f"UpdateInfo(version={self.version}, build={self.build_date})"
    
    @property
    def is_patch(self) -> bool:
        """x.x.NUM - Kleines Update"""
        return self._version_type() == "patch"
    
    @property
    def is_minor(self) -> bool:
        """x.NUM.x - Größeres Update"""
        return self._version_type() == "minor"
    
    @property
    def is_major(self) -> bool:
        """NUM.x.x - Komplette Überarbeitung"""
        return self._version_type() == "major"
    
    def _version_type(self) -> str:
        """Bestimmt Update-Typ basierend auf Version"""
        # Wird vom Vergleich mit aktueller Version bestimmt
        return getattr(self, '_update_type', 'patch')


class Updater:
    """
    Auto-Updater für AILinux Client (.deb Pakete).
    
    Usage:
        updater = Updater(api_client, current_version="3.0.0")
        updater.start_auto_check()
        
        # Manuell prüfen
        if updater.check_for_update():
            # UI zeigt Dialog: Jetzt oder später?
            updater.download_update()
            updater.install_update(restart_now=True)
    """
    
    def __init__(self, api_client=None, current_version: str = "0.0.0"):
        self.api_client = api_client
        self.current_version = current_version
        self.latest_update: Optional[UpdateInfo] = None
        self._auto_check_thread: Optional[threading.Thread] = None
        self._stop_auto_check = threading.Event()
        self._update_available = False
        self._update_downloaded = False
        self._downloaded_path: Optional[Path] = None
        self._update_callback: Optional[Callable] = None
        self._last_check: Optional[datetime] = None
        
        # Cache-Verzeichnis erstellen
        UPDATE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        
        # Prüfe auf wartende Updates
        self._check_pending_update()
        
    def set_update_callback(self, callback: Callable):
        """Callback wenn Update verfügbar (für UI-Dialog)"""
        self._update_callback = callback
        
    @property
    def update_available(self) -> bool:
        return self._update_available
    
    @property
    def update_downloaded(self) -> bool:
        return self._update_downloaded
        
    def _check_pending_update(self):
        """Prüft ob ein Update beim letzten Mal heruntergeladen wurde"""
        pending_file = UPDATE_CACHE_DIR / "pending_update.deb"
        if pending_file.exists():
            self._downloaded_path = pending_file
            self._update_downloaded = True
            logger.info(f"Pending update found: {pending_file}")
            
    def check_for_update(self, silent: bool = False) -> bool:
        """
        Prüft Server auf neue Version.
        
        Returns: True wenn Update verfügbar
        """
        try:
            if not self.api_client:
                # Fallback: Direct HTTP request
                import httpx
                response = httpx.get(f"{UPDATE_BASE_URL}{VERSION_ENDPOINT}", timeout=10)
                if response.status_code != 200:
                    return False
                result = response.json()
            else:
                result = self.api_client._request("GET", VERSION_ENDPOINT)
                
            if not result:
                return False
                
            server_version = result.get("version", "0.0.0")
            
            # Vergleiche Versionen
            update_type = self._compare_versions(server_version, self.current_version)
            
            if update_type:
                self.latest_update = UpdateInfo(
                    version=result.get("version"),
                    checksum=result.get("checksum", ""),
                    build_date=result.get("build_date", ""),
                    download_url=result.get("download_url", f"{UPDATE_BASE_URL}{DOWNLOAD_ENDPOINT}"),
                    changelog=result.get("changelog", ""),
                    filename=result.get("filename", "")
                )
                self.latest_update._update_type = update_type
                self._update_available = True
                
                if not silent:
                    logger.info(f"Update verfügbar: {self.current_version} → {server_version} ({update_type})")
                    
                # Callback für UI
                if self._update_callback:
                    self._update_callback(self.latest_update)
                    
                return True
            else:
                self._update_available = False
                if not silent:
                    logger.debug(f"Kein Update: {self.current_version} ist aktuell")
                return False
                
        except Exception as e:
            logger.error(f"Update-Check fehlgeschlagen: {e}")
            return False
        finally:
            self._last_check = datetime.now()
            
    def _compare_versions(self, server: str, local: str) -> Optional[str]:
        """
        Vergleicht Versionen und gibt Update-Typ zurück.
        
        Returns:
            "major" - NUM.x.x Änderung
            "minor" - x.NUM.x Änderung
            "patch" - x.x.NUM Änderung
            None - Keine Änderung oder älter
        """
        try:
            s_parts = [int(x) for x in server.split(".")[:3]]
            l_parts = [int(x) for x in local.split(".")[:3]]
            
            # Pad mit Nullen
            while len(s_parts) < 3: s_parts.append(0)
            while len(l_parts) < 3: l_parts.append(0)
            
            # Vergleiche
            if s_parts[0] > l_parts[0]:
                return "major"
            elif s_parts[0] == l_parts[0] and s_parts[1] > l_parts[1]:
                return "minor"
            elif s_parts[0] == l_parts[0] and s_parts[1] == l_parts[1] and s_parts[2] > l_parts[2]:
                return "patch"
            else:
                return None
        except:
            return "patch" if server != local else None
            
    def download_update(self, progress_callback: Optional[Callable] = None) -> Tuple[bool, str]:
        """
        Download .deb Paket vom Server.
        
        Args:
            progress_callback: callback(percent, status)
            
        Returns:
            (success, message)
        """
        if not self.latest_update:
            return False, "Kein Update verfügbar"
            
        try:
            import httpx
            
            if progress_callback:
                progress_callback(5, "Starte Download...")
                
            download_url = self.latest_update.download_url
            download_path = UPDATE_CACHE_DIR / self.latest_update.filename
            
            # Download mit Progress
            with httpx.stream("GET", download_url, timeout=300, follow_redirects=True) as response:
                if response.status_code != 200:
                    return False, f"Download fehlgeschlagen: HTTP {response.status_code}"
                    
                total_size = int(response.headers.get("content-length", 0))
                downloaded = 0
                
                with open(download_path, "wb") as f:
                    for chunk in response.iter_bytes(chunk_size=65536):
                        f.write(chunk)
                        downloaded += len(chunk)
                        if progress_callback and total_size > 0:
                            percent = int(downloaded / total_size * 80) + 10
                            progress_callback(percent, f"Download: {downloaded // 1024}KB / {total_size // 1024}KB")
                            
            if progress_callback:
                progress_callback(90, "Verifiziere Checksum...")
                
            # Checksum prüfen
            if self.latest_update.checksum:
                file_hash = hashlib.sha256(download_path.read_bytes()).hexdigest()
                if file_hash != self.latest_update.checksum:
                    download_path.unlink()
                    return False, "Checksum-Fehler - Download beschädigt"
                    
            # Als pending markieren
            pending_path = UPDATE_CACHE_DIR / "pending_update.deb"
            if pending_path.exists():
                pending_path.unlink()
            download_path.rename(pending_path)
            
            self._downloaded_path = pending_path
            self._update_downloaded = True
            
            if progress_callback:
                progress_callback(100, "Download abgeschlossen!")
                
            return True, f"Update {self.latest_update.version} heruntergeladen"
            
        except Exception as e:
            logger.error(f"Download fehlgeschlagen: {e}")
            return False, str(e)
            
    def install_update(self, restart_now: bool = True) -> Tuple[bool, str]:
        """
        Installiert das heruntergeladene .deb Paket.
        
        Args:
            restart_now: True = Sofort neu starten, False = Beim nächsten Start
            
        Returns:
            (success, message)
        """
        if not self._downloaded_path or not self._downloaded_path.exists():
            return False, "Kein Update zum Installieren"
            
        try:
            deb_path = str(self._downloaded_path)
            
            if restart_now:
                # Erstelle Install-Script das nach Beenden ausgeführt wird
                install_script = UPDATE_CACHE_DIR / "install_update.sh"
                with open(install_script, "w") as f:
                    f.write(f'''#!/bin/bash
sleep 2
echo "Installiere AILinux Client Update..."
sudo dpkg -i "{deb_path}"
rm -f "{deb_path}"
rm -f "$0"
echo "Update installiert. Starte AILinux Client..."
nohup ailinux-client &>/dev/null &
''')
                os.chmod(install_script, 0o755)
                
                # Starte Install-Script im Hintergrund
                subprocess.Popen(
                    ["/bin/bash", str(install_script)],
                    start_new_session=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                
                return True, "Update wird installiert. Client startet neu..."
            else:
                # Beim nächsten Start installieren
                # Markiere in Datei
                marker = UPDATE_CACHE_DIR / "install_on_next_start"
                marker.write_text(deb_path)
                
                return True, "Update wird beim nächsten Start installiert."
                
        except Exception as e:
            logger.error(f"Installation fehlgeschlagen: {e}")
            return False, str(e)
            
    def install_pending_on_startup(self) -> bool:
        """
        Prüft und installiert wartende Updates beim Start.
        Wird von main.py aufgerufen.
        
        Returns: True wenn Update installiert wurde (App sollte beenden)
        """
        marker = UPDATE_CACHE_DIR / "install_on_next_start"
        if not marker.exists():
            return False
            
        try:
            deb_path = marker.read_text().strip()
            if not Path(deb_path).exists():
                marker.unlink()
                return False
                
            # Installiere
            logger.info(f"Installiere wartendes Update: {deb_path}")
            result = subprocess.run(
                ["sudo", "dpkg", "-i", deb_path],
                capture_output=True,
                text=True
            )
            
            # Cleanup
            marker.unlink()
            Path(deb_path).unlink(missing_ok=True)
            
            if result.returncode == 0:
                logger.info("Update erfolgreich installiert")
                return True
            else:
                logger.error(f"Update-Installation fehlgeschlagen: {result.stderr}")
                return False
                
        except Exception as e:
            logger.error(f"Fehler bei Update-Installation: {e}")
            return False
            
    # =========================================================================
    # Auto-Check Background Thread
    # =========================================================================
    
    def start_auto_check(self, initial_check: bool = True):
        """Startet automatischen Update-Check alle 30 Minuten"""
        if self._auto_check_thread and self._auto_check_thread.is_alive():
            return
            
        self._stop_auto_check.clear()
        self._auto_check_thread = threading.Thread(
            target=self._auto_check_loop,
            args=(initial_check,),
            daemon=True,
            name="UpdateChecker"
        )
        self._auto_check_thread.start()
        logger.info("Auto-Update-Check gestartet (alle 30 Min)")
        
    def stop_auto_check(self):
        """Stoppt Auto-Check"""
        self._stop_auto_check.set()
        if self._auto_check_thread:
            self._auto_check_thread.join(timeout=5)
            
    def _auto_check_loop(self, initial_check: bool):
        """Background-Loop für Update-Checks"""
        if initial_check:
            time.sleep(10)  # Warte bis App initialisiert
            self.check_for_update(silent=True)
            
        while not self._stop_auto_check.is_set():
            self._stop_auto_check.wait(AUTO_CHECK_INTERVAL)
            
            if self._stop_auto_check.is_set():
                break
                
            self.check_for_update(silent=True)
            
    def get_update_info(self) -> Dict:
        """Info über Update-Status"""
        return {
            "last_check": self._last_check.isoformat() if self._last_check else None,
            "update_available": self._update_available,
            "update_downloaded": self._update_downloaded,
            "current_version": self.current_version,
            "latest_version": self.latest_update.version if self.latest_update else None,
            "update_type": self.latest_update._update_type if self.latest_update else None,
            "auto_check_running": self._auto_check_thread.is_alive() if self._auto_check_thread else False
        }
    
    def manual_check(self) -> Dict:
        """Manueller Check mit detailliertem Ergebnis"""
        has_update = self.check_for_update(silent=False)
        return {
            "has_update": has_update,
            "current_version": self.current_version,
            "latest_version": self.latest_update.version if self.latest_update else None,
            "update_type": self.latest_update._update_type if self.latest_update else None,
            "changelog": self.latest_update.changelog if self.latest_update else "",
            "download_url": self.latest_update.download_url if self.latest_update else None
        }


# Singleton
_updater: Optional[Updater] = None


def get_updater(api_client=None, version: str = None) -> Updater:
    """Updater Singleton"""
    global _updater
    
    if _updater is None:
        try:
            from .version import VERSION
            v = version or VERSION
        except:
            v = version or "3.0.0"
        _updater = Updater(api_client, v)
    elif api_client and _updater.api_client is None:
        _updater.api_client = api_client
        
    return _updater
