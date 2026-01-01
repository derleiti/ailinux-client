"""
AILinux Client Auto-Updater v3.0
================================

Prüft update.ailinux.me auf neue Versionen und installiert .deb Updates.

Features:
- Check beim Start
- Auto-Check alle 30 Minuten
- Manueller Check
- Download .deb Paket
- SHA256 Checksum Verification
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

# Update-Server - NEU: Eigenes Update-System
UPDATE_BASE_URL = "https://update.ailinux.me"
MANIFEST_URL = f"{UPDATE_BASE_URL}/client/manifest.json"
RELEASES_URL = f"{UPDATE_BASE_URL}/client/releases"

# Fallback zu API
API_FALLBACK_URL = "https://api.ailinux.me/v1/client/update/version"

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
        return self._version_type() == "patch"
    
    @property
    def is_minor(self) -> bool:
        return self._version_type() == "minor"
    
    @property
    def is_major(self) -> bool:
        return self._version_type() == "major"
    
    def _version_type(self) -> str:
        return getattr(self, '_update_type', 'patch')


class Updater:
    """
    Auto-Updater für AILinux Client (.deb Pakete).
    
    Usage:
        updater = Updater(api_client, current_version="4.3.0")
        updater.start_auto_check()
        
        if updater.check_for_update():
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
        
        UPDATE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
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
            
    def _parse_version(self, version_str: str) -> Tuple[int, int, int]:
        """Parse version string to tuple"""
        parts = version_str.replace("-beta", "").replace("-alpha", "").split(".")
        try:
            return (int(parts[0]), int(parts[1] if len(parts) > 1 else 0), 
                    int(parts[2] if len(parts) > 2 else 0))
        except (ValueError, IndexError):
            return (0, 0, 0)
            
    def _is_newer_version(self, remote: str, local: str) -> bool:
        """Check if remote version is newer than local"""
        return self._parse_version(remote) > self._parse_version(local)
            
    def check_for_update(self, silent: bool = False) -> bool:
        """
        Prüft update.ailinux.me auf neue Version.
        Returns: True wenn Update verfügbar
        """
        try:
            import httpx
            
            # Primär: Manifest von update.ailinux.me
            try:
                response = httpx.get(MANIFEST_URL, timeout=10, follow_redirects=True)
                if response.status_code == 200:
                    manifest = response.json()
                    remote_version = manifest.get("version", "0.0.0")
                    
                    if self._is_newer_version(remote_version, self.current_version):
                        self.latest_update = UpdateInfo(
                            version=remote_version,
                            checksum=manifest.get("checksum", ""),
                            build_date=manifest.get("release_date", ""),
                            download_url=manifest.get("download_url", f"{RELEASES_URL}/ailinux-client_{remote_version}_amd64.deb"),
                            changelog=manifest.get("changelog", ""),
                            filename=f"ailinux-client_{remote_version}_amd64.deb"
                        )
                        
                        # Determine update type
                        current = self._parse_version(self.current_version)
                        remote = self._parse_version(remote_version)
                        if remote[0] > current[0]:
                            self.latest_update._update_type = "major"
                        elif remote[1] > current[1]:
                            self.latest_update._update_type = "minor"
                        else:
                            self.latest_update._update_type = "patch"
                            
                        self._update_available = True
                        self._last_check = datetime.now()
                        
                        if not silent:
                            logger.info(f"Update available: {self.current_version} → {remote_version}")
                        
                        if self._update_callback:
                            self._update_callback(self.latest_update)
                            
                        return True
                    else:
                        if not silent:
                            logger.debug(f"Already up to date: {self.current_version}")
                        self._last_check = datetime.now()
                        return False
                        
            except Exception as e:
                logger.warning(f"Manifest check failed, trying API fallback: {e}")
                
            # Fallback: API Endpoint
            if self.api_client:
                result = self.api_client._request("GET", "/v1/client/update/version")
                if result and "version" in result:
                    remote_version = result["version"]
                    if self._is_newer_version(remote_version, self.current_version):
                        self.latest_update = UpdateInfo(
                            version=remote_version,
                            checksum=result.get("checksum", ""),
                            build_date=result.get("build_date", ""),
                            download_url=result.get("download_url", ""),
                            changelog=result.get("changelog", "")
                        )
                        self._update_available = True
                        return True
                        
            return False
            
        except Exception as e:
            if not silent:
                logger.error(f"Update check failed: {e}")
            return False
            
    def download_update(self, progress_callback: Optional[Callable] = None) -> bool:
        """
        Lädt Update herunter und verifiziert Checksum.
        Returns: True wenn erfolgreich
        """
        if not self.latest_update:
            logger.error("No update info available")
            return False
            
        try:
            import httpx
            
            download_url = self.latest_update.download_url
            target_file = UPDATE_CACHE_DIR / self.latest_update.filename
            
            logger.info(f"Downloading {download_url}")
            
            with httpx.stream("GET", download_url, timeout=300, follow_redirects=True) as response:
                if response.status_code != 200:
                    logger.error(f"Download failed: HTTP {response.status_code}")
                    return False
                    
                total_size = int(response.headers.get("content-length", 0))
                downloaded = 0
                
                with open(target_file, "wb") as f:
                    for chunk in response.iter_bytes(chunk_size=8192):
                        f.write(chunk)
                        downloaded += len(chunk)
                        if progress_callback and total_size:
                            progress_callback(downloaded / total_size * 100)
                            
            # Verify checksum if available
            if self.latest_update.checksum:
                sha256 = hashlib.sha256()
                with open(target_file, "rb") as f:
                    for chunk in iter(lambda: f.read(8192), b""):
                        sha256.update(chunk)
                        
                if sha256.hexdigest() != self.latest_update.checksum:
                    logger.error("Checksum mismatch!")
                    target_file.unlink()
                    return False
                    
                logger.info("Checksum verified")
                
            # Move to pending
            pending_file = UPDATE_CACHE_DIR / "pending_update.deb"
            shutil.move(str(target_file), str(pending_file))
            
            self._downloaded_path = pending_file
            self._update_downloaded = True
            
            logger.info(f"Update downloaded: {pending_file}")
            return True
            
        except Exception as e:
            logger.error(f"Download failed: {e}")
            return False
            
    def install_update(self, restart_now: bool = True) -> bool:
        """
        Installiert heruntergeladenes Update.
        Returns: True wenn erfolgreich
        """
        if not self._downloaded_path or not self._downloaded_path.exists():
            logger.error("No downloaded update found")
            return False
            
        try:
            deb_path = str(self._downloaded_path)
            logger.info(f"Installing {deb_path}")
            
            # Installation mit pkexec für grafisches sudo
            result = subprocess.run(
                ["pkexec", "dpkg", "-i", deb_path],
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                # Fallback: sudo
                result = subprocess.run(
                    ["sudo", "dpkg", "-i", deb_path],
                    capture_output=True,
                    text=True
                )
                
            if result.returncode == 0:
                logger.info("Update installed successfully")
                self._downloaded_path.unlink()
                self._update_downloaded = False
                
                if restart_now:
                    logger.info("Restarting application...")
                    os.execv(sys.executable, [sys.executable] + sys.argv)
                    
                return True
            else:
                logger.error(f"Installation failed: {result.stderr}")
                return False
                
        except Exception as e:
            logger.error(f"Installation failed: {e}")
            return False
            
    def start_auto_check(self):
        """Startet automatischen Update-Check im Hintergrund"""
        if self._auto_check_thread and self._auto_check_thread.is_alive():
            return
            
        self._stop_auto_check.clear()
        self._auto_check_thread = threading.Thread(
            target=self._auto_check_loop, 
            daemon=True,
            name="UpdateChecker"
        )
        self._auto_check_thread.start()
        logger.info("Auto-update check started (30 min interval)")
        
    def stop_auto_check(self):
        """Stoppt automatischen Update-Check"""
        self._stop_auto_check.set()
        if self._auto_check_thread:
            self._auto_check_thread.join(timeout=2)
            
    def _auto_check_loop(self):
        """Hintergrund-Loop für Update-Checks"""
        # Initialer Check nach 60 Sekunden
        if not self._stop_auto_check.wait(60):
            self.check_for_update(silent=True)
            
        while not self._stop_auto_check.wait(AUTO_CHECK_INTERVAL):
            self.check_for_update(silent=True)
