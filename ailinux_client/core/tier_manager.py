"""
AILinux Tier Manager v3.0
=========================

Synchronisiert Tier-Informationen mit dem Server.

Tiers:
- GUEST: Ollama only, 50k/Tag, kein MCP
- REGISTERED: Ollama only, 100k/Tag, MCP ✓
- PRO: Alle Modelle, 250k Cloud / Ollama ∞
- ENTERPRISE: Unlimited
"""
import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import json
from datetime import datetime

logger = logging.getLogger("ailinux.tier_manager")


class Tier(str, Enum):
    """Tier levels - Mapping zu Server-Tiers"""
    GUEST = "guest"
    REGISTERED = "registered"
    PRO = "pro"
    ENTERPRISE = "enterprise"
    
    # Aliases für Kompatibilität
    FREE = "guest"
    TIER_0 = "guest"
    TIER_0_5 = "registered"
    TIER_1 = "pro"
    TIER_2 = "enterprise"


@dataclass
class TierConfig:
    """Tier-Konfiguration (wird vom Server geladen)"""
    name: str
    display_name: str
    price_monthly: float = 0.0
    price_yearly: float = 0.0
    
    # Model access
    ollama_models: bool = True
    cloud_models: bool = False
    model_count: int = 20
    
    # Features
    mcp_access: bool = False
    cli_agents: bool = False
    priority_queue: bool = False
    
    # Limits
    daily_token_limit: int = 50000
    ollama_unlimited: bool = False
    
    # UI
    color: str = "#888888"
    features: List[str] = None


# Server-kompatibles Tier Mapping
TIER_MAP = {
    "guest": Tier.GUEST,
    "free": Tier.GUEST,
    "registered": Tier.REGISTERED,
    "pro": Tier.PRO,
    "enterprise": Tier.ENTERPRISE,
    "unlimited": Tier.ENTERPRISE,
    # Numeric aliases
    "0": Tier.GUEST,
    "0.5": Tier.REGISTERED,
    "1": Tier.PRO,
    "2": Tier.ENTERPRISE,
}


# Default Configs (werden vom Server überschrieben)
DEFAULT_CONFIGS: Dict[Tier, TierConfig] = {
    Tier.GUEST: TierConfig(
        name="guest", display_name="Gast",
        price_monthly=0.0, ollama_models=True, cloud_models=False,
        mcp_access=False, cli_agents=False, daily_token_limit=50000,
        ollama_unlimited=False, color="#888888",
        features=["20 Ollama Cloud-Modelle", "50k Tokens/Tag", "Kein MCP"]
    ),
    Tier.REGISTERED: TierConfig(
        name="registered", display_name="Registriert",
        price_monthly=0.0, ollama_models=True, cloud_models=False,
        mcp_access=True, cli_agents=True, daily_token_limit=100000,
        ollama_unlimited=False, color="#22c55e",
        features=["20 Ollama Cloud-Modelle", "MCP Tools ✓", "100k Tokens/Tag"]
    ),
    Tier.PRO: TierConfig(
        name="pro", display_name="Pro",
        price_monthly=18.99, price_yearly=189.99,
        ollama_models=True, cloud_models=True, model_count=600,
        mcp_access=True, cli_agents=True, daily_token_limit=250000,
        ollama_unlimited=True, color="#3b82f6",
        features=["600+ KI-Modelle", "250k Tokens/Tag (Cloud)", "Ollama ∞ unlimited"]
    ),
    Tier.ENTERPRISE: TierConfig(
        name="enterprise", display_name="Unlimited",
        price_monthly=59.99, price_yearly=599.99,
        ollama_models=True, cloud_models=True, model_count=600,
        mcp_access=True, cli_agents=True, daily_token_limit=0,
        ollama_unlimited=True, priority_queue=True, color="#a855f7",
        features=["600+ KI-Modelle", "Unlimited Tokens", "Priority Queue ✓"]
    ),
}


class TierManager:
    """
    Tier Manager - Synchronisiert mit Server.
    
    Holt Tier-Info und Modelle vom Server statt lokaler Konfiguration.
    """
    
    def __init__(self, api_client=None):
        self.api_client = api_client
        self._tier = Tier.GUEST
        self._config: Optional[TierConfig] = None
        self._server_models: List[str] = []
        self._server_backend = "ollama"
        self._token_usage = 0
        self._token_limit = 50000
        self._ollama_unlimited = False
        self._last_sync = None
        
    @property
    def tier(self) -> Tier:
        """Aktueller Tier"""
        if self.api_client:
            tier_str = self.api_client.tier.lower()
            return TIER_MAP.get(tier_str, Tier.GUEST)
        return self._tier
    
    @tier.setter
    def tier(self, value: Tier):
        self._tier = value
        
    @property
    def config(self) -> TierConfig:
        """Tier-Konfiguration"""
        if self._config:
            return self._config
        return DEFAULT_CONFIGS.get(self.tier, DEFAULT_CONFIGS[Tier.GUEST])
    
    # =========================================================================
    # Server Sync
    # =========================================================================
    
    def sync_from_server(self) -> bool:
        """
        Synchronisiert Tier-Info und Modelle vom Server.
        
        Endpoints:
        - GET /v1/client/tier - Tier-Infos
        - GET /v1/client/models - Verfügbare Modelle
        - GET /v1/client/tokens/usage - Token-Verbrauch
        """
        if not self.api_client:
            logger.warning("No API client, using defaults")
            return False
            
        success = True
        
        # 1. Tier-Info vom Server
        try:
            tier_info = self.api_client._request("GET", "/v1/client/tier")
            if tier_info:
                self._parse_tier_info(tier_info)
                logger.info(f"Tier synced: {self.tier.value} (ollama_unlimited={self._ollama_unlimited})")
        except Exception as e:
            logger.error(f"Failed to sync tier: {e}")
            success = False
            
        # 2. Modelle vom Server
        try:
            models_info = self.api_client._request("GET", "/v1/client/models")
            if models_info:
                self._server_models = models_info.get("models", [])
                self._server_backend = models_info.get("backend", "ollama")
                logger.info(f"Models synced: {len(self._server_models)} models (backend={self._server_backend})")
        except Exception as e:
            logger.error(f"Failed to sync models: {e}")
            success = False
            
        self._last_sync = datetime.now()
        return success
    
    def _parse_tier_info(self, info: Dict):
        """Parst Server Tier-Info in lokale Config"""
        tier_name = info.get("tier", "guest").lower()
        self._tier = TIER_MAP.get(tier_name, Tier.GUEST)
        
        self._config = TierConfig(
            name=info.get("tier", "guest"),
            display_name=info.get("name", "Gast"),
            price_monthly=info.get("price_monthly", 0.0),
            price_yearly=info.get("price_yearly", 0.0),
            ollama_models=True,
            cloud_models=info.get("model_count") == "all",
            model_count=info.get("model_count", 20) if isinstance(info.get("model_count"), int) else 600,
            mcp_access=info.get("mcp_access", False),
            cli_agents=info.get("cli_agents", False),
            priority_queue=info.get("priority_queue", False),
            daily_token_limit=info.get("daily_token_limit", 50000),
            ollama_unlimited=info.get("ollama_unlimited", False),
            features=info.get("features", []),
        )
        
        self._ollama_unlimited = info.get("ollama_unlimited", False)
        self._token_limit = info.get("daily_token_limit", 50000)
        
    def sync_models_from_server(self) -> List[str]:
        """Holt Modelle vom Server"""
        if not self.api_client:
            return []
            
        try:
            result = self.api_client._request("GET", "/v1/client/models")
            if result and "models" in result:
                self._server_models = result.get("models", [])
                self._server_backend = result.get("backend", "ollama")
                return self._server_models
        except Exception as e:
            logger.error(f"Failed to sync models: {e}")
            
        return []
    
    def get_server_models(self) -> List[str]:
        """Cached Server-Modelle oder sync wenn leer"""
        if not self._server_models:
            self.sync_models_from_server()
        return self._server_models
    
    def get_server_backend(self) -> str:
        """Backend-Typ vom Server"""
        return self._server_backend
    
    # =========================================================================
    # Feature Access (basiert auf Server-Config)
    # =========================================================================
    
    def can_use_ollama(self) -> bool:
        return True  # Ollama immer verfügbar
    
    def can_use_cloud_models(self) -> bool:
        return self.config.cloud_models
    
    def can_use_cli_agents(self) -> bool:
        return self.config.cli_agents
    
    def can_use_mcp_tools(self) -> bool:
        return self.config.mcp_access
    
    def is_ollama_unlimited(self) -> bool:
        """Pro/Enterprise: Ollama ohne Token-Limit"""
        return self._ollama_unlimited or self.tier in (Tier.PRO, Tier.ENTERPRISE)
    
    # =========================================================================
    # Model Access
    # =========================================================================
    
    def get_available_models(self, ollama_models: List[Dict] = None) -> List[Dict]:
        """
        Verfügbare Modelle - PRIMÄR vom Server.
        
        Fallback auf lokale Ollama-Modelle wenn Server nicht erreichbar.
        """
        models = []
        
        # Server-Modelle haben Priorität
        if self.api_client and self.api_client.is_authenticated():
            server_models = self.get_server_models()
            
            if server_models:
                for model_id in server_models:
                    if "/" in model_id:
                        provider, name = model_id.split("/", 1)
                    else:
                        provider = self._server_backend
                        name = model_id
                    
                    models.append({
                        "id": model_id,
                        "name": name,
                        "provider": provider,
                        "available": True,
                        "local": (provider == "ollama"),
                    })
                
                logger.debug(f"Using {len(models)} models from server")
                return models
        
        # Fallback: Lokale Ollama-Modelle
        if ollama_models:
            for model in ollama_models:
                model_name = model.get("name", model.get("id", "unknown"))
                models.append({
                    "id": f"ollama/{model_name}",
                    "name": model_name,
                    "provider": "ollama",
                    "available": True,
                    "local": True,
                })
        
        return models
    
    def get_model_groups(self, ollama_models: List[Dict] = None) -> Dict[str, List[Dict]]:
        """Modelle nach Provider gruppiert"""
        all_models = self.get_available_models(ollama_models)
        
        groups = {"ollama": [], "cloud": []}
        
        for model in all_models:
            if model["provider"] == "ollama":
                groups["ollama"].append(model)
            else:
                groups["cloud"].append(model)
        
        return groups
    
    # =========================================================================
    # Token Tracking (lokal + Server)
    # =========================================================================
    
    def track_tokens(self, tokens: int, model: str = None):
        """Token-Usage tracken (nur für Cloud-Modelle bei Pro)"""
        # Ollama unlimited für Pro? Nicht tracken.
        if self._ollama_unlimited and model and "ollama" in model.lower():
            logger.debug(f"Skipping token tracking for Ollama model (unlimited)")
            return
            
        self._token_usage += tokens
        logger.debug(f"Token usage: {self._token_usage}/{self._token_limit}")
    
    def get_remaining_tokens(self) -> int:
        """Verbleibende Tokens (-1 = unlimited)"""
        if self._token_limit == 0 or self._ollama_unlimited:
            return -1
        return max(0, self._token_limit - self._token_usage)
    
    def get_usage_info(self) -> Dict[str, Any]:
        """Usage-Informationen"""
        return {
            "tier": self.tier.value,
            "tier_name": self.config.display_name,
            "token_usage": self._token_usage,
            "token_limit": self._token_limit,
            "remaining_tokens": self.get_remaining_tokens(),
            "ollama_unlimited": self._ollama_unlimited,
        }
    
    # =========================================================================
    # UI Helpers
    # =========================================================================
    
    def get_status_text(self) -> str:
        """Status-Text für Statusbar"""
        text = f"{self.config.display_name}"
        
        # Token-Info nur wenn nicht unlimited
        if not self._ollama_unlimited and self._token_limit > 0:
            remaining = self.get_remaining_tokens()
            if remaining >= 0:
                text += f" | {remaining:,} tokens"
        elif self._ollama_unlimited:
            text += " | Ollama ∞"
        
        return text
    
    def get_status_color(self) -> str:
        """Tier-Farbe für Statusbar"""
        colors = {
            Tier.GUEST: "#888888",
            Tier.REGISTERED: "#22c55e",
            Tier.PRO: "#3b82f6",
            Tier.ENTERPRISE: "#a855f7",
        }
        return colors.get(self.tier, "#888888")
    
    def get_upgrade_info(self) -> Dict[str, Any]:
        """Upgrade-Informationen"""
        if self.tier == Tier.GUEST:
            return {
                "next_tier": "registered",
                "next_tier_name": "Registriert (Kostenlos)",
                "benefits": ["MCP Tools", "CLI Agents", "100k Tokens/Tag"],
                "action": "Kostenlos registrieren",
            }
        elif self.tier == Tier.REGISTERED:
            return {
                "next_tier": "pro",
                "next_tier_name": "Pro (18,99€/Monat)",
                "benefits": ["600+ KI-Modelle", "Ollama unlimited", "250k Cloud-Tokens"],
                "action": "Upgrade auf Pro",
            }
        elif self.tier == Tier.PRO:
            return {
                "next_tier": "enterprise",
                "next_tier_name": "Unlimited (59,99€/Monat)",
                "benefits": ["Unlimited Tokens", "Priority Queue", "Priority Support"],
                "action": "Upgrade auf Unlimited",
            }
        return {"next_tier": None, "benefits": [], "action": None}


# Singleton
_tier_manager: Optional[TierManager] = None


def get_tier_manager(api_client=None) -> TierManager:
    """TierManager Singleton"""
    global _tier_manager
    
    if _tier_manager is None:
        _tier_manager = TierManager(api_client)
    elif api_client and _tier_manager.api_client is None:
        _tier_manager.api_client = api_client
    
    return _tier_manager
