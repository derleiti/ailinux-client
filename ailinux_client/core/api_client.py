"""
AILinux API Client
==================

HTTP client for communicating with AILinux server.
"""
import os
import json
import logging
from typing import Optional, Dict, Any, List
from pathlib import Path

try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    import requests
    HAS_HTTPX = False

logger = logging.getLogger("ailinux.api_client")


class APIClient:
    """
    HTTP client for AILinux API

    Handles:
    - Authentication
    - Chat requests
    - MCP tool calls
    - Settings sync
    """

    # Fixed server URL
    BASE_URL = "https://api.ailinux.me"

    def __init__(self):
        self.base_url = self.BASE_URL
        self.user_id = ""
        self.token = ""
        self.tier = "free"
        self.client_id = ""

        # Load saved credentials
        self._load_credentials()

    def _load_credentials(self):
        """Load saved credentials from config file"""
        config_path = Path.home() / ".config" / "ailinux" / "credentials.json"

        if config_path.exists():
            try:
                with open(config_path) as f:
                    data = json.load(f)
                    self.user_id = self.user_id or data.get("user_id", "")
                    self.token = self.token or data.get("token", "")
                    self.tier = data.get("tier", "free")
                    self.client_id = data.get("client_id", "")
            except Exception as e:
                logger.warning(f"Failed to load credentials: {e}")

    def _save_credentials(self):
        """Save credentials to config file"""
        config_dir = Path.home() / ".config" / "ailinux"
        config_dir.mkdir(parents=True, exist_ok=True)

        config_path = config_dir / "credentials.json"

        try:
            with open(config_path, "w") as f:
                json.dump({
                    "user_id": self.user_id,
                    "token": self.token,
                    "tier": self.tier,
                    "client_id": self.client_id,
                }, f)
            config_path.chmod(0o600)  # Secure permissions
        except Exception as e:
            logger.error(f"Failed to save credentials: {e}")

    def logout(self):
        """Logout - clear credentials"""
        self.user_id = ""
        self.token = ""
        self.tier = "free"
        self.client_id = ""

        # Delete credentials file
        config_path = Path.home() / ".config" / "ailinux" / "credentials.json"
        if config_path.exists():
            config_path.unlink()

        logger.info("Logged out")

    def _headers(self) -> Dict[str, str]:
        """Get request headers"""
        headers = {
            "Content-Type": "application/json",
            "X-User-ID": self.user_id,
            "X-Client-ID": self.client_id,
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _request(
        self,
        method: str,
        endpoint: str,
        data: Dict = None,
        timeout: float = 60.0
    ) -> Dict[str, Any]:
        """Make HTTP request"""
        url = f"{self.base_url}{endpoint}"

        if HAS_HTTPX:
            with httpx.Client(timeout=timeout) as client:
                response = client.request(
                    method,
                    url,
                    headers=self._headers(),
                    json=data
                )
                response.raise_for_status()
                return response.json()
        else:
            response = requests.request(
                method,
                url,
                headers=self._headers(),
                json=data,
                timeout=timeout
            )
            response.raise_for_status()
            return response.json()

    # =========================================================================
    # Authentication
    # =========================================================================

    def login(self, email: str, password: str) -> bool:
        """Login with email/password - server assigns client_id"""
        try:
            if HAS_HTTPX:
                with httpx.Client(timeout=30.0) as client:
                    response = client.post(
                        f"{self.base_url}/v1/auth/login",
                        json={"email": email, "password": password}
                    )
                    response.raise_for_status()
                    result = response.json()
            else:
                response = requests.post(
                    f"{self.base_url}/v1/auth/login",
                    json={"email": email, "password": password},
                    timeout=30.0
                )
                response.raise_for_status()
                result = response.json()

            # Server returns: user_id, token, tier, client_id
            self.user_id = result.get("user_id", "")
            self.token = result.get("token", "")
            self.tier = result.get("tier", "free")
            self.client_id = result.get("client_id", "")

            self._save_credentials()
            logger.info(f"Logged in: {self.user_id} ({self.tier})")
            return True

        except Exception as e:
            logger.error(f"Login failed: {e}")
            return False

    def register_device(self, device_name: str, device_type: str = "desktop") -> bool:
        """Register this device"""
        try:
            result = self._request("POST", f"/v1/users/{self.user_id}/devices", {
                "user_id": self.user_id,
                "device_name": device_name,
                "device_type": device_type
            })

            self.client_id = result.get("client_id", "")
            self._save_credentials()
            logger.info(f"Device registered: {self.client_id}")
            return True

        except Exception as e:
            logger.error(f"Device registration failed: {e}")
            return False

    def get_auth_token(self, client_id: str, client_secret: str) -> Optional[Dict]:
        """Get auth token using client credentials"""
        try:
            if HAS_HTTPX:
                with httpx.Client(timeout=30.0) as client:
                    response = client.post(
                        f"{self.base_url}/v1/auth/token",
                        headers={
                            "client_id": client_id,
                            "client_secret": client_secret
                        }
                    )
                    response.raise_for_status()
                    result = response.json()
            else:
                response = requests.post(
                    f"{self.base_url}/v1/auth/token",
                    headers={
                        "client_id": client_id,
                        "client_secret": client_secret
                    },
                    timeout=30.0
                )
                response.raise_for_status()
                result = response.json()

            self.token = result.get("token", "")
            self.user_id = result.get("user_id", "")
            self.tier = result.get("tier", "free")
            self.client_id = client_id

            self._save_credentials()
            return result

        except Exception as e:
            logger.error(f"Token auth failed: {e}")
            return None

    def is_authenticated(self) -> bool:
        """Check if authenticated"""
        return bool(self.token)

    # =========================================================================
    # Chat
    # =========================================================================

    def chat(
        self,
        message: str,
        model: str = None,
        system_prompt: str = None,
        temperature: float = 0.7
    ) -> Dict[str, Any]:
        """Send chat message"""
        data = {
            "message": message,
            "temperature": temperature,
        }
        if model:
            data["model"] = model
        if system_prompt:
            data["system_prompt"] = system_prompt

        return self._request("POST", "/v1/client/chat", data, timeout=120.0)

    def get_models(self) -> Dict[str, Any]:
        """
        Get available models from server based on user tier.
        
        Returns:
            Dict with:
            - tier: str (free/pro/enterprise)
            - tier_name: str (display name)
            - model_count: int
            - models: List[str] (model IDs)
            - backend: str (ollama/openrouter)
            - upgrade_available: bool
        """
        try:
            result = self._request("GET", "/v1/client/models")
            logger.info(f"Got {result.get('model_count', 0)} models from server (tier: {result.get('tier')})")
            return result
        except Exception as e:
            logger.warning(f"Failed to get models from server: {e}")
            return {
                "tier": "free",
                "tier_name": "Free (Offline)",
                "model_count": 0,
                "models": [],
                "backend": "ollama",
                "upgrade_available": True
            }
    
    def get_model_list(self) -> List[str]:
        """Get just the model ID list"""
        result = self.get_models()
        return result.get("models", [])

    def get_tier_info(self) -> Dict[str, Any]:
        """Get tier information"""
        try:
            return self._request("GET", "/v1/client/tier")
        except:
            return {"tier": "free", "name": "Free"}

    # =========================================================================
    # MCP Tools
    # =========================================================================

    def list_mcp_tools(self) -> List[Dict]:
        """List available MCP tools"""
        try:
            result = self._request("GET", "/v1/client/mcp/tools")
            return result.get("tools", [])
        except:
            return []

    def call_mcp_tool(self, tool: str, params: Dict = None) -> Dict[str, Any]:
        """Call MCP tool"""
        return self._request("POST", "/v1/client/mcp/call", {
            "tool": tool,
            "params": params or {}
        })

    # =========================================================================
    # Settings
    # =========================================================================

    def get_settings(self) -> Dict[str, Any]:
        """Get user settings"""
        try:
            return self._request("GET", f"/v1/users/{self.user_id}/settings")
        except:
            return {}

    def sync_settings(self, settings: Dict, merge: bool = True) -> Dict[str, Any]:
        """Sync settings to server"""
        return self._request("POST", f"/v1/users/{self.user_id}/settings", {
            "settings": settings,
            "merge": merge
        })
