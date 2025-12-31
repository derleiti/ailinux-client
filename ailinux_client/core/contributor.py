"""
AILinux Contributor Mode v1.0
=============================

Ermöglicht Clients, Hardware-Ressourcen mit dem Mesh zu teilen.

Features:
- Ollama-Modelle teilen
- GPU/CPU zur Verfügung stellen
- Credits verdienen

Architektur:
┌─────────────────────────────────────────────────────────────┐
│                    CONTRIBUTOR MODE                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   ┌─────────────┐                    ┌─────────────┐       │
│   │   Client    │───Registration───▶│   Server    │       │
│   │  (Ollama)   │                    │    (Hub)    │       │
│   └──────┬──────┘                    └──────┬──────┘       │
│          │                                  │               │
│          │◀──────── Task Request ──────────│               │
│          │                                  │               │
│          │────────── Response ────────────▶│               │
│          │                                  │               │
│          │◀──────── Credits ───────────────│               │
│                                                             │
└─────────────────────────────────────────────────────────────┘
"""
import asyncio
import json
import logging
import os
import platform
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

logger = logging.getLogger("ailinux.contributor")


@dataclass
class HardwareInfo:
    """Hardware-Informationen des Clients"""
    cpu_cores: int = 0
    ram_gb: float = 0
    gpu_name: str = ""
    gpu_vram_gb: float = 0
    os_name: str = ""
    hostname: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "cpu_cores": self.cpu_cores,
            "ram_gb": self.ram_gb,
            "gpu_name": self.gpu_name,
            "gpu_vram_gb": self.gpu_vram_gb,
            "os_name": self.os_name,
            "hostname": self.hostname,
        }


@dataclass
class ContributorStats:
    """Contributor-Statistiken"""
    registered_at: Optional[datetime] = None
    total_requests: int = 0
    total_tokens: int = 0
    credits_earned: float = 0
    uptime_hours: float = 0


class ContributorMode:
    """
    Verwaltet den Contributor Mode.
    
    Erlaubt dem Client, Ollama-Modelle und Hardware
    mit dem AILinux Mesh zu teilen.
    """
    
    CONFIG_FILE = "contributor.json"
    
    def __init__(self, api_client=None, config_dir: Path = None):
        self.api_client = api_client
        self.config_dir = config_dir or Path.home() / ".config" / "ailinux"
        self.config_file = self.config_dir / self.CONFIG_FILE
        
        self.enabled = False
        self.node_id: Optional[str] = None
        self.hardware = HardwareInfo()
        self.available_models: List[str] = []
        self.stats = ContributorStats()
        
        self._running = False
        self._task: Optional[asyncio.Task] = None
        
        self._load_config()
    
    def _load_config(self):
        """Lade Contributor-Konfiguration"""
        if self.config_file.exists():
            try:
                data = json.loads(self.config_file.read_text())
                self.enabled = data.get("enabled", False)
                self.node_id = data.get("node_id")
                self.available_models = data.get("available_models", [])
                
                if data.get("stats"):
                    self.stats.total_requests = data["stats"].get("total_requests", 0)
                    self.stats.credits_earned = data["stats"].get("credits_earned", 0)
                    
                logger.info(f"Contributor config loaded: enabled={self.enabled}")
            except Exception as e:
                logger.warning(f"Could not load contributor config: {e}")
    
    def _save_config(self):
        """Speichere Contributor-Konfiguration"""
        self.config_dir.mkdir(parents=True, exist_ok=True)
        data = {
            "enabled": self.enabled,
            "node_id": self.node_id,
            "available_models": self.available_models,
            "stats": {
                "total_requests": self.stats.total_requests,
                "credits_earned": self.stats.credits_earned,
            }
        }
        self.config_file.write_text(json.dumps(data, indent=2))
    
    def detect_hardware(self) -> HardwareInfo:
        """Erkenne Hardware des Systems"""
        import psutil
        
        hw = HardwareInfo()
        
        # CPU & RAM
        hw.cpu_cores = psutil.cpu_count(logical=True) or 0
        hw.ram_gb = round(psutil.virtual_memory().total / (1024**3), 1)
        hw.os_name = f"{platform.system()} {platform.release()}"
        hw.hostname = platform.node()
        
        # GPU (nvidia-smi)
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0 and result.stdout.strip():
                parts = result.stdout.strip().split(",")
                hw.gpu_name = parts[0].strip()
                hw.gpu_vram_gb = round(float(parts[1].strip()) / 1024, 1)
        except:
            pass
        
        self.hardware = hw
        return hw
    
    def detect_ollama_models(self) -> List[str]:
        """Erkenne installierte Ollama-Modelle"""
        models = []
        
        try:
            result = subprocess.run(
                ["ollama", "list"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                lines = result.stdout.strip().split("\n")[1:]  # Skip header
                for line in lines:
                    if line.strip():
                        model_name = line.split()[0]
                        models.append(model_name)
        except Exception as e:
            logger.warning(f"Could not detect Ollama models: {e}")
        
        self.available_models = models
        return models
    
    async def register(self) -> bool:
        """Registriere als Contributor beim Server"""
        if not self.api_client:
            logger.error("No API client configured")
            return False
        
        # Detect hardware & models
        self.detect_hardware()
        self.detect_ollama_models()
        
        if not self.available_models:
            logger.warning("No Ollama models available - cannot register as contributor")
            return False
        
        try:
            response = self.api_client._request(
                "POST",
                "/v1/federation/contributor/register",
                data={
                    "hardware": self.hardware.to_dict(),
                    "capabilities": self.available_models
                }
            )
            
            if response and response.get("status") == "registered":
                self.node_id = response.get("node_id")
                self.enabled = True
                self.stats.registered_at = datetime.now()
                self._save_config()
                
                logger.info(f"Registered as contributor: {self.node_id}")
                logger.info(f"  Hardware: {self.hardware.cpu_cores} cores, {self.hardware.ram_gb}GB RAM")
                logger.info(f"  GPU: {self.hardware.gpu_name} ({self.hardware.gpu_vram_gb}GB)")
                logger.info(f"  Models: {len(self.available_models)}")
                
                return True
            else:
                logger.error(f"Registration failed: {response}")
                return False
                
        except Exception as e:
            logger.error(f"Registration error: {e}")
            return False
    
    async def unregister(self) -> bool:
        """Abmelden als Contributor"""
        self.enabled = False
        self.node_id = None
        self._save_config()
        logger.info("Unregistered as contributor")
        return True
    
    async def start(self):
        """Starte Contributor Mode"""
        if not self.enabled:
            logger.warning("Contributor mode not enabled - register first")
            return
        
        self._running = True
        self._task = asyncio.create_task(self._main_loop())
        logger.info("Contributor mode started")
    
    async def stop(self):
        """Stoppe Contributor Mode"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Contributor mode stopped")
    
    async def _main_loop(self):
        """Hauptschleife - wartet auf Tasks vom Server"""
        while self._running:
            try:
                # TODO: WebSocket-Verbindung zum Server für Tasks
                # Aktuell nur Heartbeat
                await asyncio.sleep(30)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Contributor loop error: {e}")
                await asyncio.sleep(5)
    
    def get_status(self) -> Dict[str, Any]:
        """Aktueller Contributor-Status"""
        return {
            "enabled": self.enabled,
            "node_id": self.node_id,
            "hardware": self.hardware.to_dict(),
            "models": self.available_models,
            "stats": {
                "total_requests": self.stats.total_requests,
                "credits_earned": self.stats.credits_earned,
            }
        }


# Singleton
_contributor: Optional[ContributorMode] = None


def get_contributor(api_client=None) -> ContributorMode:
    """Hole Contributor Singleton"""
    global _contributor
    if _contributor is None:
        _contributor = ContributorMode(api_client=api_client)
    return _contributor
