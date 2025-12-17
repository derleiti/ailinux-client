"""
AILinux MCP Node Client
=======================

WebSocket-Verbindung zum Server MCP Node.
Empfängt Tool-Calls vom Server und führt sie lokal aus.

Architektur:
1. Client verbindet sich via WebSocket zu /v1/mcp/node/connect
2. Server kann Tool-Calls an Client senden
3. Client führt Tools lokal aus (via LocalMCPExecutor)
4. Ergebnisse werden an Server zurückgesendet
5. KI kann weitere Tools aufrufen

Authentifizierung:
- Nutzt User-Token aus APIClient (wenn eingeloggt)
- Session-ID für eindeutige Client-Identifikation
- Backend weiß welcher User + welche Session
"""
import asyncio
import json
import logging
import os
import uuid
import platform
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, Callable
from dataclasses import dataclass, field

import aiohttp
from dotenv import load_dotenv

from .local_mcp import local_mcp, MCPToolResult

logger = logging.getLogger("ailinux.mcp_node_client")

# Config laden
for p in [Path("config/.env"), Path.home() / ".config/ailinux/.env"]:
    if p.exists():
        load_dotenv(p)
        break


def _get_or_create_session_id() -> str:
    """Generiere oder lade persistente Session-ID"""
    session_file = Path.home() / ".config" / "ailinux" / "session_id"

    if session_file.exists():
        try:
            return session_file.read_text().strip()
        except:
            pass

    # Neue Session-ID generieren
    session_id = f"sess_{uuid.uuid4().hex[:16]}"

    # Speichern
    session_file.parent.mkdir(parents=True, exist_ok=True)
    session_file.write_text(session_id)
    session_file.chmod(0o600)

    return session_id


def _get_machine_id() -> str:
    """Generiere eindeutige Machine-ID"""
    try:
        # Linux: /etc/machine-id
        machine_id_path = Path("/etc/machine-id")
        if machine_id_path.exists():
            return machine_id_path.read_text().strip()[:16]
    except:
        pass

    # Fallback: hostname + user
    import hashlib
    data = f"{platform.node()}:{os.getenv('USER', 'unknown')}"
    return hashlib.sha256(data.encode()).hexdigest()[:16]


@dataclass
class ConnectionState:
    """Verbindungsstatus"""
    connected: bool = False
    client_id: Optional[str] = None
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    tier: Optional[str] = None
    available_tools: list = field(default_factory=list)
    last_ping: Optional[datetime] = None
    machine_id: Optional[str] = None


class MCPNodeClient:
    """
    WebSocket Client für MCP Node Verbindung.

    Ermöglicht dem Server, MCP-Tools auf dem Client auszuführen.
    Authentifiziert mit User-Token und Session-ID.
    """

    def __init__(self, api_client=None):
        self.api_client = api_client
        self.server_url = os.getenv("AILINUX_SERVER", "https://api.ailinux.me")
        self.ws_url = self.server_url.replace("https://", "wss://").replace("http://", "ws://")

        # Session Management
        self.session_id = _get_or_create_session_id()
        self.machine_id = _get_machine_id()

        # Legacy auth (für Fallback)
        self.client_id = os.getenv("AILINUX_CLIENT_ID", "")
        self.client_secret = os.getenv("AILINUX_CLIENT_SECRET", "")

        # State
        self.state = ConnectionState()
        self.state.session_id = self.session_id
        self.state.machine_id = self.machine_id

        self.websocket: Optional[aiohttp.ClientWebSocketResponse] = None
        self.aio_session: Optional[aiohttp.ClientSession] = None
        self._running = False
        self._reconnect_delay = 5

        # Callbacks
        self.on_connected: Optional[Callable] = None
        self.on_disconnected: Optional[Callable] = None
        self.on_tool_call: Optional[Callable] = None
        self.on_error: Optional[Callable] = None

        # Auth Token (User oder Client)
        self.auth_token: Optional[str] = None
        
        # Lade credentials.json falls vorhanden
        self._load_credentials()
    
    def _load_credentials(self):
        """Lade Token aus credentials.json"""
        cred_file = Path.home() / ".config" / "ailinux" / "credentials.json"
        if cred_file.exists():
            try:
                import json
                data = json.loads(cred_file.read_text())
                if data.get("token"):
                    self.auth_token = data["token"]
                    logger.info(f"Loaded token from credentials.json (user: {data.get('user_id', 'unknown')})")
            except Exception as e:
                logger.warning(f"Could not load credentials.json: {e}")
        
    def set_api_client(self, api_client):
        """Set API client for user authentication"""
        self.api_client = api_client
        # Update server URL from api_client if set
        if api_client and api_client.base_url:
            self.server_url = api_client.base_url
            self.ws_url = self.server_url.replace("https://", "wss://").replace("http://", "ws://")

    def get_auth_token(self) -> Optional[str]:
        """Get auth token - prefer user token from api_client"""
        # 1. Nutze User-Token aus api_client (eingeloggter User)
        if self.api_client and self.api_client.token:
            logger.debug("Using user token from api_client")
            return self.api_client.token

        # 2. Fallback: Legacy client credentials (für Server-to-Server)
        if self.client_id and self.client_secret:
            logger.debug("Using legacy client credentials")
            return None  # Will trigger legacy auth flow

        logger.warning("No authentication available")
        return None

    async def _get_legacy_token(self) -> Optional[str]:
        """Legacy: Hole JWT Token via client credentials"""
        if not self.client_id or not self.client_secret:
            return None

        try:
            async with aiohttp.ClientSession() as session:
                headers = {
                    "client-id": self.client_id,
                    "client-secret": self.client_secret
                }
                async with session.post(
                    f"{self.server_url}/v1/auth/token",
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get("token")
                    else:
                        text = await resp.text()
                        logger.error(f"Legacy auth failed: {resp.status} - {text}")
        except Exception as e:
            logger.error(f"Legacy auth error: {e}")

        return None

    async def connect(self):
        """Verbindung zum MCP Node herstellen mit User-Auth und Session-ID"""
        # Token holen (User-Token oder Legacy)
        # Nur neu holen wenn noch kein Token
        if not self.auth_token:
            self.auth_token = self.get_auth_token()

        if not self.auth_token:
            # Fallback zu legacy client credentials
            self.auth_token = await self._get_legacy_token()

        if not self.auth_token:
            logger.error("Could not get auth token (no user token and no client credentials)")
            if self.on_error:
                self.on_error("Authentication failed - please login")
            return False

        # Get user info from api_client or credentials.json
        user_id = ""
        tier = "free"
        if self.api_client:
            user_id = self.api_client.user_id or ""
            tier = self.api_client.tier or "free"
        else:
            # Fallback: Lade aus credentials.json
            cred_file = Path.home() / ".config" / "ailinux" / "credentials.json"
            if cred_file.exists():
                try:
                    import json
                    creds = json.loads(cred_file.read_text())
                    user_id = creds.get("user_id", "")
                    tier = creds.get("tier", "free")
                    logger.info(f"Using credentials: user={user_id}, tier={tier}")
                except: pass

        # WebSocket URL mit Token, Session-ID und Machine-ID
        import urllib.parse
        params = urllib.parse.urlencode({
            "token": self.auth_token,
            "session_id": self.session_id,
            "machine_id": self.machine_id,
            "user_id": user_id,
            "tier": tier,
            "client_version": "1.0.0",
            "mode": "telemetry",
        })
        ws_url = f"{self.ws_url}/v1/mcp/node/connect?{params}"

        try:
            self.aio_session = aiohttp.ClientSession()
            self.websocket = await self.aio_session.ws_connect(
                ws_url,
                heartbeat=30,
                timeout=aiohttp.ClientTimeout(total=60)
            )

            logger.info(f"Connected to MCP Node: {self.ws_url} (session: {self.session_id})")
            self._running = True
            self.state.user_id = user_id
            self.state.tier = tier

            # Message Loop starten
            asyncio.create_task(self._message_loop())

            # Ping Loop starten
            asyncio.create_task(self._ping_loop())

            # Tool-Liste + Client-Info an Server senden
            await self._send_client_info()
            await self._send_tool_list()

            return True

        except Exception as e:
            logger.error(f"Connection failed: {e}")
            if self.on_error:
                self.on_error(str(e))
            return False

    async def _send_client_info(self):
        """Sendet Client-Informationen an Server"""
        if not self.websocket:
            return

        import platform

        info = {
            "jsonrpc": "2.0",
            "method": "client/info",
            "params": {
                "session_id": self.session_id,
                "machine_id": self.machine_id,
                "user_id": self.api_client.user_id if self.api_client else "",
                "tier": self.api_client.tier if self.api_client else "free",
                "platform": platform.system(),
                "hostname": platform.node(),
                "python_version": platform.python_version(),
                "client_version": "1.0.0",
            "mode": "telemetry_only",
            }
        }

        await self.websocket.send_json(info)
        logger.debug(f"Sent client info: session={self.session_id}")
    
    async def _send_tool_list(self):
        """Sendet Liste der lokalen Tools an Server"""
        if not self.websocket:
            return
            
        tools = local_mcp.list_tools()
        tool_names = [t["name"] for t in tools]
        
        message = {
            "jsonrpc": "2.0",
            "method": "tools/list",
            "params": {
                "tools": tool_names
            }
        }
        
        await self.websocket.send_json(message)
        logger.info(f"Sent tool list: {len(tool_names)} tools")
    
    async def _message_loop(self):
        """Empfängt und verarbeitet Nachrichten vom Server"""
        try:
            async for msg in self.websocket:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    data = json.loads(msg.data)
                    await self._handle_message(data)
                    
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    logger.error(f"WebSocket error: {self.websocket.exception()}")
                    break
                    
                elif msg.type == aiohttp.WSMsgType.CLOSED:
                    logger.info("WebSocket closed")
                    break
                    
        except Exception as e:
            logger.error(f"Message loop error: {e}")
        finally:
            self._running = False
            self.state.connected = False
            if self.on_disconnected:
                self.on_disconnected()
            
            # Auto-Reconnect
            if self._running:
                await asyncio.sleep(self._reconnect_delay)
                await self.connect()
    
    async def _handle_message(self, data: Dict[str, Any]):
        """Verarbeitet eingehende Nachrichten"""
        method = data.get("method")
        request_id = data.get("id")
        
        # Verbindungsbestätigung
        if method == "connected":
            params = data.get("params", {})
            self.state.connected = True
            self.state.client_id = params.get("client_id")
            self.state.tier = params.get("tier")
            self.state.available_tools = params.get("available_tools", [])
            
            logger.info(f"MCP Node connected: {self.state.client_id} ({self.state.tier})")
            
            if self.on_connected:
                self.on_connected(self.state)
                
        # Pong
        elif method == "pong":
            self.state.last_ping = datetime.now()
            
        # Tool-Call vom Server
        elif method == "tools/call":
            params = data.get("params", {})
            tool_name = params.get("name")
            arguments = params.get("arguments", {})
            
            logger.info(f"Tool call received: {tool_name}")
            
            if self.on_tool_call:
                self.on_tool_call(tool_name, arguments)
            
            # Tool ausführen
            result = await self._execute_tool(tool_name, arguments)
            
            # Response senden
            response = {
                "jsonrpc": "2.0",
                "id": request_id,
            }
            
            if result.success:
                response["result"] = result.content
            else:
                response["error"] = {
                    "code": -32000,
                    "message": result.error
                }
            
            await self.websocket.send_json(response)
            logger.info(f"Tool result sent: {tool_name} - success={result.success}")
    
    async def _execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> MCPToolResult:
        """Führt lokales Tool aus"""
        # Mapping von Client-Tool-Namen zu lokalen Tools
        tool_mapping = {
            "client_file_read": "file_read",
            "client_file_write": "file_write",
            "client_file_list": "file_list",
            "client_shell_exec": "bash_exec",
            "client_codebase_search": "file_search",
            "client_git_status": "bash_exec",  # git status als bash
        }
        
        local_tool = tool_mapping.get(tool_name, tool_name)
        
        # Git Status speziell behandeln
        if tool_name == "client_git_status":
            path = arguments.get("path", ".")
            arguments = {"command": "git status", "cwd": path}
        
        return await local_mcp.call_tool(local_tool, arguments)
    
    async def _ping_loop(self):
        """Sendet regelmäßig Pings"""
        while self._running and self.websocket:
            try:
                await self.websocket.send_json({"method": "ping"})
                await asyncio.sleep(30)
            except:
                break
    
    async def disconnect(self):
        """Verbindung trennen"""
        self._running = False

        if self.websocket:
            await self.websocket.close()
            self.websocket = None

        if self.aio_session:
            await self.aio_session.close()
            self.aio_session = None

        self.state.connected = False
        logger.info(f"Disconnected from MCP Node (session: {self.session_id})")
    
    def is_connected(self) -> bool:
        """Prüft ob verbunden"""
        return self.state.connected and self.websocket is not None


# Singleton
mcp_node = MCPNodeClient()
