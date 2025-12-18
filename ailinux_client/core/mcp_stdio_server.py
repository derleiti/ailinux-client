#!/usr/bin/env python3
"""
AILinux MCP STDIO Server
========================

MCP-Server der über stdio (stdin/stdout) kommuniziert.
Wird von CLI-Agents (Claude Code, Gemini, Codex, etc.) als Subprocess gestartet.

Verbindet sich mit dem AILinux Remote-Server unter /v1/mcp
und filtert Tools basierend auf dem User-Tier:
- free: Kein MCP-Zugriff
- registered: Reduzierte Coding-Tools
- pro/enterprise: Voller MCP-Zugriff

Protokoll: JSON-RPC 2.0 über stdio
Format: Content-Length Header + JSON Body (wie LSP)
"""
import sys
import os
import json
import asyncio
import logging
import httpx
from pathlib import Path
from typing import Dict, Any, Optional, List

# Pfad zum Projekt hinzufügen
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Logging nach stderr (stdout ist für MCP reserviert)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s|%(levelname)-8s|%(name)-25s|%(message)s',
    stream=sys.stderr
)
logger = logging.getLogger("ailinux.mcp_stdio")

# AILinux Server configuration
AILINUX_SERVER = os.getenv("AILINUX_SERVER", "https://api.ailinux.me")
AILINUX_TOKEN = os.getenv("AILINUX_TOKEN", "")
AILINUX_TIER = os.getenv("AILINUX_TIER", "free")


# Tool access by tier
TIER_TOOLS = {
    "free": [
        # Support ist für alle verfügbar
        "support_call"
    ],
    "registered": [
        # Basic read-only tools for registered users
        "file_read", "file_list", "file_search",
        "git_status", "git_log", "git_diff",
        "system_info", "codebase_search",
        "support_call"
    ],
    "pro": [
        # Extended tools for pro users
        "file_read", "file_write", "file_list", "file_search",
        "bash_exec", "git_status", "git_log", "git_diff",
        "codebase_search", "system_info",
        # Additional pro tools
        "tristar_memory_search", "tristar_memory_store",
        "ollama_list", "ollama_generate", "ollama_chat",
        "web_search", "crawl_url",
        "support_call"
    ],
    "enterprise": [
        # All tools for enterprise
        "*"  # Wildcard = all tools
    ]
}


class MCPStdioServer:
    """
    MCP Server der über stdio kommuniziert und Remote-Tools proxyt.

    Unterstützt:
    - initialize: Server-Capabilities
    - tools/list: Verfügbare Tools (gefiltert nach Tier)
    - tools/call: Tool ausführen (Remote oder Lokal)
    
    Telemetrie (NUR LESEN):
    - Meldet Client-Status an Backend (hostname, platform, session)
    - Meldet Tool-Nutzung für Fehleranalyse
    - Server kann KEINE Tools auf dem Client ausführen!
    """

    SERVER_NAME = "ailinux-mcp-proxy"
    SERVER_VERSION = "2.2.0"

    def __init__(self, server_url: str = None, token: str = None, tier: str = None):
        self.initialized = False
        self.client_info = {}
        # Environment-Variablen HIER lesen (nicht beim Import)
        self.server_url = server_url or os.getenv("AILINUX_SERVER", "https://api.ailinux.me")
        self.token = token or os.getenv("AILINUX_TOKEN", "")
        self.tier = tier or os.getenv("AILINUX_TIER", "free")
        self.remote_tools: List[Dict] = []
        self.http_client: Optional[httpx.AsyncClient] = None
        
        # Telemetrie (read-only)
        self.session_id = None
        self._telemetry_ws = None
        self._telemetry_task = None

        logger.info(f"MCP Server initialized - Tier: {self.tier}, Server: {self.server_url}")

    async def _ensure_http_client(self):
        """Ensure HTTP client is initialized"""
        if not self.http_client:
            headers = {"Content-Type": "application/json"}
            if self.token:
                headers["Authorization"] = f"Bearer {self.token}"
            self.http_client = httpx.AsyncClient(
                base_url=self.server_url,
                headers=headers,
                timeout=60.0
            )

    async def _bootstrap_telemetry(self):
        """
        Bootstrap Telemetrie-Verbindung zum Backend (NUR LESEN, KEIN SCHREIBEN).
        
        Der Server kann sehen:
        - Welcher Client verbunden ist (hostname, platform, session)
        - Welche Tools der Client nutzt
        - Status für Fehleranalyse
        
        Der Server kann NICHT:
        - Tools auf dem Client ausführen
        - Dateien lesen/schreiben
        - Befehle ausführen
        """
        # Verhindere doppeltes Bootstrap
        if self._telemetry_task is not None:
            logger.debug("Telemetrie bereits gestartet - überspringe")
            return
            
        if self.tier == "free":
            logger.info("Free tier - Telemetrie nicht gestartet")
            return
        
        if not self.token:
            logger.warning("Kein Token gesetzt - Telemetrie nicht möglich")
            return
        
        try:
            import aiohttp
            import platform
            import uuid
            from datetime import datetime
            
            # Session-ID generieren oder laden
            session_file = Path.home() / ".config" / "ailinux" / "session_id"
            if session_file.exists():
                self.session_id = session_file.read_text().strip()
            else:
                self.session_id = f"sess_{uuid.uuid4().hex[:16]}"
                session_file.parent.mkdir(parents=True, exist_ok=True)
                session_file.write_text(self.session_id)
            
            # WebSocket URL
            ws_url = self.server_url.replace("https://", "wss://").replace("http://", "ws://")
            ws_url = f"{ws_url}/v1/mcp/node/connect?token={self.token}&session_id={self.session_id}&tier={self.tier}&mode=telemetry"
            
            async def telemetry_loop():
                """Hält WebSocket-Verbindung für Telemetrie"""
                while True:
                    try:
                        async with aiohttp.ClientSession() as session:
                            async with session.ws_connect(ws_url, heartbeat=30) as ws:
                                logger.info(f"✅ Telemetrie verbunden (session: {self.session_id})")
                                self._telemetry_ws = ws
                                
                                # Client-Info senden
                                await ws.send_json({
                                    "jsonrpc": "2.0",
                                    "method": "client/info",
                                    "params": {
                                        "session_id": self.session_id,
                                        "tier": self.tier,
                                        "platform": platform.system(),
                                        "hostname": platform.node(),
                                        "python_version": platform.python_version(),
                                        "server_version": self.SERVER_VERSION,
                                        "mode": "telemetry_only",  # Signalisiert: NUR Telemetrie!
                                        "connected_at": datetime.now().isoformat(),
                                    }
                                })
                                
                                # Message-Loop (ignoriert alle Befehle vom Server)
                                async for msg in ws:
                                    if msg.type == aiohttp.WSMsgType.TEXT:
                                        data = json.loads(msg.data)
                                        method = data.get("method", "")
                                        
                                        # Pong beantworten
                                        if method == "ping":
                                            await ws.send_json({"method": "pong"})
                                        
                                        # Verbindungsbestätigung loggen
                                        elif method == "connected":
                                            params = data.get("params", {})
                                            logger.info(f"🔗 Server bestätigt: {params.get('client_id')}")
                                        
                                        # ALLE anderen Befehle ignorieren (keine Remote-Execution!)
                                        elif method == "tools/call":
                                            logger.warning(f"⚠️ Server wollte Tool aufrufen - IGNORIERT (telemetry_only mode)")
                                            # Antwort: Nicht erlaubt
                                            request_id = data.get("id")
                                            if request_id:
                                                await ws.send_json({
                                                    "jsonrpc": "2.0",
                                                    "id": request_id,
                                                    "error": {
                                                        "code": -32600,
                                                        "message": "Remote execution disabled (telemetry_only mode)"
                                                    }
                                                })
                                    
                                    elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                                        break
                                
                    except Exception as e:
                        logger.error(f"Telemetrie-Fehler: {e}")
                    
                    self._telemetry_ws = None
                    logger.warning("⚠️ Telemetrie getrennt - reconnecting in 5s...")
                    await asyncio.sleep(5)
            
            self._telemetry_task = asyncio.create_task(telemetry_loop())
            logger.info("🚀 Telemetrie gestartet (read-only)")
            
        except ImportError:
            logger.warning("aiohttp nicht verfügbar - Telemetrie deaktiviert")
        except Exception as e:
            logger.error(f"Telemetrie-Bootstrap fehlgeschlagen: {e}")
    
    async def _report_tool_usage(self, tool_name: str, success: bool, duration_ms: int = 0):
        """Meldet Tool-Nutzung an Server (für Fehleranalyse)"""
        if hasattr(self, '_telemetry_ws') and self._telemetry_ws:
            try:
                await self._telemetry_ws.send_json({
                    "jsonrpc": "2.0",
                    "method": "telemetry/tool_used",
                    "params": {
                        "tool": tool_name,
                        "success": success,
                        "duration_ms": duration_ms,
                        "tier": self.tier,
                        "timestamp": __import__('datetime').datetime.now().isoformat()
                    }
                })
            except Exception as e:
                logger.debug(f"Tool-Report fehlgeschlagen: {e}")

    async def _fetch_remote_tools(self) -> List[Dict]:
        """Fetch available tools from remote server"""
        if self.tier == "free":
            logger.info("Free tier - no remote tools available")
            return []

        try:
            await self._ensure_http_client()
            response = await self.http_client.post(
                "/v1/mcp",
                json={"jsonrpc": "2.0", "method": "tools/list", "id": 1}
            )

            if response.status_code == 200:
                data = response.json()
                if "result" in data and "tools" in data["result"]:
                    self.remote_tools = data["result"]["tools"]
                    logger.info(f"Fetched {len(self.remote_tools)} remote tools")
                    return self.remote_tools
            else:
                logger.warning(f"Failed to fetch remote tools: {response.status_code}")

        except Exception as e:
            logger.error(f"Error fetching remote tools: {e}")

        return []

    def _filter_tools_by_tier(self, tools: List[Dict]) -> List[Dict]:
        """Filter tools based on user tier"""
        allowed = TIER_TOOLS.get(self.tier, [])

        # Enterprise gets everything
        if "*" in allowed:
            return tools

        # Filter to allowed tools only
        return [t for t in tools if t.get("name") in allowed]

    def get_capabilities(self) -> Dict[str, Any]:
        """Server Capabilities"""
        return {
            "capabilities": {
                "tools": {
                    "listChanged": True
                },
                "resources": {
                    "subscribe": False,
                    "listChanged": False
                },
                "prompts": {
                    "listChanged": False
                },
                "logging": {}
            },
            "serverInfo": {
                "name": self.SERVER_NAME,
                "version": self.SERVER_VERSION,
                "tier": self.tier
            }
        }

    def get_local_tools(self) -> List[Dict]:
        """Get local-only tools (always available)"""
        return [
            {
                "name": "local_file_read",
                "description": "Liest eine lokale Datei",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Dateipfad"}
                    },
                    "required": ["path"]
                }
            },
            {
                "name": "local_file_list",
                "description": "Listet lokale Dateien auf",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Verzeichnispfad"},
                        "pattern": {"type": "string", "description": "Glob-Pattern"}
                    },
                    "required": ["path"]
                }
            },
            {
                "name": "local_bash",
                "description": "Führt lokalen Shell-Befehl aus",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "command": {"type": "string", "description": "Shell-Befehl"},
                        "cwd": {"type": "string", "description": "Arbeitsverzeichnis"}
                    },
                    "required": ["command"]
                }
            }
        ]

    async def get_tools(self) -> List[Dict]:
        """Get all available tools (local + filtered remote)"""
        tools = []

        # Always add local tools for registered+ users
        if self.tier != "free":
            tools.extend(self.get_local_tools())

        # Fetch and filter remote tools
        if not self.remote_tools:
            await self._fetch_remote_tools()

        filtered_remote = self._filter_tools_by_tier(self.remote_tools)
        tools.extend(filtered_remote)

        logger.info(f"Returning {len(tools)} tools for tier {self.tier}")
        return tools

    async def call_local_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a local tool"""
        import subprocess
        import glob

        try:
            if name == "local_file_read":
                path = arguments.get("path", "")
                if not path:
                    return {"error": "Path required"}
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                return {"content": [{"type": "text", "text": content}]}

            elif name == "local_file_list":
                path = arguments.get("path", ".")
                pattern = arguments.get("pattern", "*")
                full_pattern = os.path.join(path, pattern)
                files = glob.glob(full_pattern)
                return {"content": [{"type": "text", "text": "\n".join(files)}]}

            elif name == "local_bash":
                command = arguments.get("command", "")
                cwd = arguments.get("cwd", os.getcwd())
                result = subprocess.run(
                    command, shell=True, cwd=cwd,
                    capture_output=True, text=True, timeout=30
                )
                output = result.stdout + result.stderr
                return {"content": [{"type": "text", "text": output}]}

            else:
                return {"error": f"Unknown local tool: {name}"}

        except Exception as e:
            return {"content": [{"type": "text", "text": f"Error: {e}"}], "isError": True}

    async def call_remote_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a remote tool via AILinux server"""
        # Check tier access
        allowed = TIER_TOOLS.get(self.tier, [])
        if "*" not in allowed and name not in allowed:
            return {
                "content": [{"type": "text", "text": f"Tool '{name}' not available for tier '{self.tier}'"}],
                "isError": True
            }

        try:
            await self._ensure_http_client()
            response = await self.http_client.post(
                "/v1/mcp",
                json={
                    "jsonrpc": "2.0",
                    "method": "tools/call",
                    "params": {"name": name, "arguments": arguments},
                    "id": 1
                }
            )

            if response.status_code == 200:
                data = response.json()
                if "result" in data:
                    return data["result"]
                elif "error" in data:
                    return {"content": [{"type": "text", "text": f"Error: {data['error']}"}], "isError": True}
            else:
                return {"content": [{"type": "text", "text": f"HTTP Error: {response.status_code}"}], "isError": True}

        except Exception as e:
            logger.error(f"Remote tool call error: {e}")
            return {"content": [{"type": "text", "text": f"Error: {e}"}], "isError": True}

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Route tool call to local or remote handler"""
        import time
        start_time = time.time()
        
        logger.info(f"Tool call: {name} (tier: {self.tier})")

        # Support-Call ist für ALLE verfügbar (auch free)
        if name == "support_call":
            result = await self._call_support(arguments)
            duration_ms = int((time.time() - start_time) * 1000)
            await self._report_tool_usage(name, not result.get("isError", False), duration_ms)
            return result

        # Free tier has no access to other tools
        if self.tier == "free":
            await self._report_tool_usage(name, False, 0)
            return {
                "content": [{"type": "text", "text": "MCP tools not available for free tier. Please register or upgrade."}],
                "isError": True
            }

        # Local tools
        if name.startswith("local_"):
            result = await self.call_local_tool(name, arguments)
        else:
            # Remote tools
            result = await self.call_remote_tool(name, arguments)
        
        # Telemetrie: Tool-Nutzung melden
        duration_ms = int((time.time() - start_time) * 1000)
        success = not result.get("isError", False) and "error" not in result
        await self._report_tool_usage(name, success, duration_ms)
        
        return result

    async def _call_support(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Support-Call: Sendet Problem an KI-Support
        
        Arguments:
            subject: Betreff (required)
            description: Problembeschreibung (required)
            category: general|bug|feature|billing|technical
            priority: low|normal|high|urgent
            logs: Relevante Log-Auszüge
        """
        import platform
        
        subject = arguments.get("subject", "Support-Anfrage")
        description = arguments.get("description", "")
        
        if not description:
            return {
                "content": [{"type": "text", "text": "Bitte beschreibe dein Problem in 'description'."}],
                "isError": True
            }
        
        # Client-Info sammeln
        client_info = {
            "platform": platform.system(),
            "hostname": platform.node(),
            "python_version": platform.python_version(),
            "mcp_version": self.SERVER_VERSION,
            "tier": self.tier,
            "session_id": getattr(self, 'session_id', None)
        }
        
        payload = {
            "subject": subject,
            "description": description,
            "category": arguments.get("category", "general"),
            "priority": arguments.get("priority", "normal"),
            "client_info": client_info,
            "logs": arguments.get("logs", "")
        }
        
        try:
            await self._ensure_http_client()
            client = self.http_client
            response = await client.post(
                f"{self.server_url}/v1/mcp/node/support/call",
                json=payload,
                headers={"Authorization": f"Bearer {self.token}"} if self.token else {}
            )
            
            if response.status_code == 200:
                data = response.json()
                
                # Antwort formatieren
                response_text = f"""🎫 **Support-Ticket erstellt: {data.get('ticket_id', 'N/A')}**

**Status:** {data.get('status', 'open')}
**Geschätzte Antwortzeit:** {data.get('estimated_response_time', '< 24h')}

---

**KI-Analyse:**
{data.get('ai_response', 'Wird bearbeitet...')}

---
"""
                if data.get('suggestions'):
                    response_text += "\n**Vorschläge:**\n"
                    for i, s in enumerate(data['suggestions'], 1):
                        response_text += f"{i}. {s}\n"
                
                if data.get('escalated'):
                    response_text += "\n⚠️ *Ticket wurde an menschlichen Support eskaliert.*"
                
                return {
                    "content": [{"type": "text", "text": response_text}]
                }
            else:
                error_msg = response.text[:200]
                return {
                    "content": [{"type": "text", "text": f"Support-Fehler ({response.status_code}): {error_msg}"}],
                    "isError": True
                }
                
        except Exception as e:
            logger.error(f"Support call failed: {e}")
            return {
                "content": [{"type": "text", "text": f"Support nicht erreichbar: {e}\n\nBitte versuche es später oder schreibe an support@ailinux.me"}],
                "isError": True
            }

    async def handle_request(self, request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Process a JSON-RPC request"""
        method = request.get("method", "")
        params = request.get("params", {})
        request_id = request.get("id")

        logger.info(f"Request: {method}")

        try:
            # Notifications don't need response
            if request_id is None:
                if method == "notifications/initialized":
                    self.initialized = True
                    logger.info("Client initialized")
                return None

            # Initialize
            if method == "initialize":
                self.client_info = params.get("clientInfo", {})
                logger.info(f"Initialize from: {self.client_info}")
                
                # Bootstrap Telemetrie für Status/Tool-Tracking (NUR LESEN!)
                await self._bootstrap_telemetry()
                
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": self.get_capabilities()
                }

            # Tools List
            elif method == "tools/list":
                tools = await self.get_tools()
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {"tools": tools}
                }

            # Tools Call
            elif method == "tools/call":
                tool_name = params.get("name", "")
                arguments = params.get("arguments", {})
                result = await self.call_tool(tool_name, arguments)
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": result
                }

            # Resources List (empty)
            elif method == "resources/list":
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {"resources": []}
                }

            # Prompts List (empty)
            elif method == "prompts/list":
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {"prompts": []}
                }

            # Unknown method
            else:
                logger.warning(f"Unknown method: {method}")
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {"code": -32601, "message": f"Method not found: {method}"}
                }

        except Exception as e:
            logger.error(f"Error handling {method}: {e}")
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32000, "message": str(e)}
            }

    async def close(self):
        """Cleanup resources"""
        # Stop Telemetrie
        if self._telemetry_task:
            self._telemetry_task.cancel()
            try:
                await self._telemetry_task
            except asyncio.CancelledError:
                pass
            logger.info("Telemetrie gestoppt")
        
        # Close HTTP client
        if self.http_client:
            await self.http_client.aclose()


def read_message() -> Optional[Dict[str, Any]]:
    """Read message from stdin (Content-Length header format)"""
    headers = {}
    while True:
        line = sys.stdin.readline()
        if not line or line == "\r\n" or line == "\n":
            break
        if ":" in line:
            key, value = line.split(":", 1)
            headers[key.strip().lower()] = value.strip()

    content_length = headers.get("content-length")
    if not content_length:
        return None

    try:
        content_length = int(content_length)
        body = sys.stdin.read(content_length)
        return json.loads(body)
    except:
        return None


def write_message(response: Dict[str, Any]):
    """Write message to stdout"""
    body = json.dumps(response, ensure_ascii=False)
    message = f"Content-Length: {len(body.encode('utf-8'))}\r\n\r\n{body}"
    sys.stdout.write(message)
    sys.stdout.flush()


async def main(daemon_mode: bool = False):
    """Main loop
    
    Args:
        daemon_mode: If True, only run telemetry without stdio (for background service)
    """
    logger.info("AILinux MCP Proxy Server starting...")
    logger.info(f"Server: {AILINUX_SERVER}, Tier: {AILINUX_TIER}, Daemon: {daemon_mode}")

    server = MCPStdioServer()
    
    # Bootstrap Telemetrie SOFORT beim Start (nicht erst bei initialize)
    # Dies ermöglicht Status-Tracking auch wenn kein CLI Agent verbunden ist
    if AILINUX_TIER != "free" and AILINUX_TOKEN:
        logger.info("Starte Telemetrie beim Server-Start...")
        await server._bootstrap_telemetry()
    else:
        logger.warning(f"Telemetrie nicht gestartet: tier={AILINUX_TIER}, token={'gesetzt' if AILINUX_TOKEN else 'LEER'}")

    try:
        if daemon_mode:
            # Daemon-Modus: Nur Telemetrie, kein stdin
            logger.info("🔧 Daemon-Modus aktiv - warte auf Telemetrie-Events...")
            while True:
                await asyncio.sleep(60)  # Keep alive, telemetry runs in background task
                if server._telemetry_ws:
                    logger.debug("Telemetrie aktiv")
                else:
                    logger.warning("Telemetrie nicht verbunden - reconnecting...")
        else:
            # Normal-Modus: stdio für CLI-Agents
            while True:
                request = read_message()

                if request is None:
                    await asyncio.sleep(0.1)
                    continue

                response = await server.handle_request(request)

                if response:
                    write_message(response)

    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        await server.close()


if __name__ == "__main__":
    import sys
    daemon = "--daemon" in sys.argv or "-d" in sys.argv
    asyncio.run(main(daemon_mode=daemon))
