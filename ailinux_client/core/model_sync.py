"""
AILinux Model Sync Manager v2.1
===============================
Synchronisiert Modellliste dynamisch vom Server.
Cached lokal für Offline-Nutzung.
"""
import json
import logging
import asyncio
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field

logger = logging.getLogger("ailinux.model_sync")


@dataclass
class ModelInfo:
    """Model-Informationen"""
    id: str
    name: str
    provider: str
    category: str  # local, free_cloud, premium
    free: bool = True
    
    def __hash__(self):
        return hash(self.id)


@dataclass
class ModelCache:
    """Lokaler Model-Cache"""
    tier: str = "guest"
    models: List[ModelInfo] = field(default_factory=list)
    categories: Dict[str, int] = field(default_factory=dict)
    sync_timestamp: str = ""
    version: str = "2.1"


class ModelSyncManager:
    """Verwaltet Model-Synchronisation mit Server"""
    
    CACHE_FILE = "models_cache.json"
    CACHE_DURATION = timedelta(hours=1)  # Re-sync nach 1 Stunde
    
    def __init__(self, config_dir: Path = None, api_client = None):
        self.config_dir = config_dir or Path.home() / ".ailinux"
        self.cache_file = self.config_dir / self.CACHE_FILE
        self.api_client = api_client
        self._cache: Optional[ModelCache] = None
        self._load_cache()
    
    def _load_cache(self):
        """Lade Cache von Disk"""
        if self.cache_file.exists():
            try:
                data = json.loads(self.cache_file.read_text())
                models = [ModelInfo(**m) for m in data.get("models", [])]
                self._cache = ModelCache(
                    tier=data.get("tier", "guest"),
                    models=models,
                    categories=data.get("categories", {}),
                    sync_timestamp=data.get("sync_timestamp", ""),
                    version=data.get("version", "2.1")
                )
                logger.info(f"Loaded {len(models)} models from cache")
            except Exception as e:
                logger.warning(f"Cache load failed: {e}")
                self._cache = ModelCache()
        else:
            self._cache = ModelCache()
    
    def _save_cache(self):
        """Speichere Cache auf Disk"""
        self.config_dir.mkdir(parents=True, exist_ok=True)
        data = {
            "tier": self._cache.tier,
            "models": [
                {"id": m.id, "name": m.name, "provider": m.provider, 
                 "category": m.category, "free": m.free}
                for m in self._cache.models
            ],
            "categories": self._cache.categories,
            "sync_timestamp": self._cache.sync_timestamp,
            "version": self._cache.version
        }
        self.cache_file.write_text(json.dumps(data, indent=2))
        logger.info(f"Saved {len(self._cache.models)} models to cache")
    
    def _needs_sync(self) -> bool:
        """Prüfe ob Sync nötig ist"""
        if not self._cache.sync_timestamp:
            return True
        try:
            last_sync = datetime.fromisoformat(self._cache.sync_timestamp)
            return datetime.now() - last_sync > self.CACHE_DURATION
        except:
            return True
    
    async def sync(self, force: bool = False) -> bool:
        """
        Synchronisiere Modelle vom Server
        
        Args:
            force: Erzwinge Sync auch wenn Cache aktuell
            
        Returns:
            True wenn Sync erfolgreich
        """
        if not force and not self._needs_sync():
            logger.debug("Cache is current, skipping sync")
            return True
        
        if not self.api_client:
            logger.warning("No API client configured")
            return False
        
        try:
            response = await self.api_client.get("/client/models/sync")
            
            if response and "models" in response:
                models = [ModelInfo(**m) for m in response["models"]]
                self._cache = ModelCache(
                    tier=response.get("tier", "guest"),
                    models=models,
                    categories=response.get("categories", {}),
                    sync_timestamp=response.get("sync_timestamp", datetime.now().isoformat()),
                    version=response.get("version", "2.1")
                )
                self._save_cache()
                logger.info(f"Synced {len(models)} models from server")
                return True
            else:
                logger.warning("Invalid sync response")
                return False
                
        except Exception as e:
            logger.error(f"Sync failed: {e}")
            return False
    
    def sync_blocking(self, force: bool = False) -> bool:
        """Blocking-Version von sync()"""
        try:
            return asyncio.get_event_loop().run_until_complete(self.sync(force))
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(self.sync(force))
            finally:
                loop.close()
    
    @property
    def models(self) -> List[ModelInfo]:
        """Alle verfügbaren Modelle"""
        return self._cache.models if self._cache else []
    
    @property
    def model_count(self) -> int:
        """Anzahl verfügbarer Modelle"""
        return len(self.models)
    
    @property
    def tier(self) -> str:
        """Aktueller Tier"""
        return self._cache.tier if self._cache else "guest"
    
    @property
    def categories(self) -> Dict[str, int]:
        """Modelle pro Kategorie"""
        return self._cache.categories if self._cache else {}
    
    def get_models_by_category(self, category: str) -> List[ModelInfo]:
        """Modelle einer Kategorie"""
        return [m for m in self.models if m.category == category]
    
    def get_models_by_provider(self, provider: str) -> List[ModelInfo]:
        """Modelle eines Providers"""
        return [m for m in self.models if m.provider == provider]
    
    def get_free_models(self) -> List[ModelInfo]:
        """Alle kostenlosen Modelle"""
        return [m for m in self.models if m.free]
    
    def get_premium_models(self) -> List[ModelInfo]:
        """Alle Premium-Modelle"""
        return [m for m in self.models if not m.free]
    
    def search_models(self, query: str) -> List[ModelInfo]:
        """Suche Modelle nach Name/ID"""
        q = query.lower()
        return [m for m in self.models if q in m.id.lower() or q in m.name.lower()]
    
    def get_model(self, model_id: str) -> Optional[ModelInfo]:
        """Hole spezifisches Modell"""
        for m in self.models:
            if m.id == model_id:
                return m
        return None
    
    def get_providers(self) -> List[str]:
        """Liste aller Provider"""
        return sorted(set(m.provider for m in self.models))
    
    def get_model_ids(self) -> List[str]:
        """Liste aller Model-IDs (für Autocomplete)"""
        return [m.id for m in self.models]


# Singleton
_model_sync: Optional[ModelSyncManager] = None


def get_model_sync(api_client=None) -> ModelSyncManager:
    """Hole ModelSyncManager Singleton"""
    global _model_sync
    if _model_sync is None:
        _model_sync = ModelSyncManager(api_client=api_client)
    return _model_sync


def init_model_sync(api_client):
    """Initialisiere mit API Client"""
    global _model_sync
    _model_sync = ModelSyncManager(api_client=api_client)
    return _model_sync
