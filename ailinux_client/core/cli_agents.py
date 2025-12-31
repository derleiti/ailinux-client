"""
CLI Agent Detector
==================

Detects locally installed CLI AI agents:
- Claude Code (claude)
- Gemini CLI (gemini)
- Codex (codex)
- OpenCode (opencode)

Provides MCP server configuration for integration.
"""
import os
import subprocess
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Dict, Any

logger = logging.getLogger("ailinux.cli_agents")


@dataclass
class CLIAgent:
    """Represents a detected CLI agent"""
    name: str
    display_name: str
    path: str
    version: Optional[str] = None
    mcp_supported: bool = False

    def get_launch_command(self, working_dir: str = None, mcp_config: str = None) -> str:
        """Get command to launch this agent"""
        cmd = self.path

        if mcp_config:
            if self.name == "claude":
                cmd = f"{self.path} --mcp-config {mcp_config}"
            elif self.name == "gemini":
                cmd = f"GEMINI_MCP_CONFIG={mcp_config} {self.path}"
            elif self.name == "codex":
                cmd = f"{self.path} --mcp {mcp_config}"

        return cmd


class CLIAgentDetector:
    """
    Detects installed CLI AI agents

    Searches common paths and checks version.
    """

    # Known agents with their binaries
    KNOWN_AGENTS = {
        "claude": {
            "display_name": "Claude Code",
            "binaries": ["claude", "claude-code"],
            "version_cmd": ["--version"],
            "mcp_supported": True,
        },
        "gemini": {
            "display_name": "Gemini CLI",
            "binaries": ["gemini", "gemini-cli"],
            "version_cmd": ["--version"],
            "mcp_supported": True,
        },
        "codex": {
            "display_name": "Codex",
            "binaries": ["codex", "openai-codex"],
            "version_cmd": ["--version"],
            "mcp_supported": True,
        },
        "opencode": {
            "display_name": "OpenCode",
            "binaries": ["opencode", "oc"],
            "version_cmd": ["--version"],
            "mcp_supported": True,
        },
        "aider": {
            "display_name": "Aider",
            "binaries": ["aider"],
            "version_cmd": ["--version"],
            "mcp_supported": False,
        },
        "continue": {
            "display_name": "Continue",
            "binaries": ["continue"],
            "version_cmd": ["--version"],
            "mcp_supported": False,
        },
    }

    # Additional search paths
    SEARCH_PATHS = [
        "/usr/local/bin",
        "/usr/bin",
        str(Path.home() / ".local" / "bin"),
        str(Path.home() / ".cargo" / "bin"),
        str(Path.home() / ".npm-global" / "bin"),
        "/opt/homebrew/bin",  # macOS
    ]

    def __init__(self):
        self.detected_agents: List[CLIAgent] = []

    def detect_all(self) -> List[CLIAgent]:
        """Detect all installed CLI agents"""
        self.detected_agents = []

        for agent_name, info in self.KNOWN_AGENTS.items():
            agent = self._detect_agent(agent_name, info)
            if agent:
                self.detected_agents.append(agent)
                logger.info(f"Detected {agent.display_name} at {agent.path}")

        return self.detected_agents

    def _detect_agent(self, name: str, info: Dict) -> Optional[CLIAgent]:
        """Try to detect a specific agent"""
        for binary in info["binaries"]:
            path = self._find_binary(binary)
            if path:
                version = self._get_version(path, info.get("version_cmd", ["--version"]))
                return CLIAgent(
                    name=name,
                    display_name=info["display_name"],
                    path=path,
                    version=version,
                    mcp_supported=info.get("mcp_supported", False)
                )
        return None

    def _find_binary(self, binary: str) -> Optional[str]:
        """Find binary in PATH or known locations"""
        # Check PATH first
        try:
            result = subprocess.run(
                ["which", binary],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except:
            pass

        # Check additional paths
        for search_path in self.SEARCH_PATHS:
            full_path = Path(search_path) / binary
            if full_path.exists() and os.access(full_path, os.X_OK):
                return str(full_path)

        return None

    def _get_version(self, path: str, version_cmd: List[str]) -> Optional[str]:
        """Get version of agent"""
        try:
            result = subprocess.run(
                [path] + version_cmd,
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                # Extract first line as version
                return result.stdout.strip().split("\n")[0][:100]
        except:
            pass
        return None

    def get_agent(self, name: str) -> Optional[CLIAgent]:
        """Get detected agent by name"""
        for agent in self.detected_agents:
            if agent.name == name:
                return agent
        return None


class LocalMCPServer:
    """
    Generates MCP server configuration for CLI agents

    Creates a config file that CLI agents can use to connect
    to our local MCP tool server via stdio or WebSocket.

    Bootstrap Flow:
    1. Client starts and connects to server MCP node
    2. Client generates MCP config for CLI agents
    3. CLI agents (Claude, Gemini, etc.) use this config to connect
    4. Agents can now use local MCP tools

    Environment variables set for agents:
    - AILINUX_SERVER: Backend URL
    - AILINUX_TOKEN: User auth token
    - AILINUX_TIER: User tier (for tool filtering)
    - AILINUX_SESSION_ID: Session ID for telemetry
    """

    def __init__(self, server_port: int = 9876):
        self.server_port = server_port
        self.config_dir = Path.home() / ".config" / "ailinux" / "mcp"
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self._bootstrapped = False

    def bootstrap_for_tier(self, tier: str, token: str = None, server_url: str = None) -> bool:
        """
        Bootstrap MCP server configs for all agents based on user tier.

        This should be called after user authentication to set up proper
        MCP configs with correct credentials and tier-based tool access.
        """
        self._tier = tier
        self._token = token
        self._server_url = server_url or os.environ.get("AILINUX_SERVER", "https://api.ailinux.me")

        # Load session ID
        session_file = Path.home() / ".config" / "ailinux" / "session_id"
        if session_file.exists():
            self._session_id = session_file.read_text().strip()
        else:
            import uuid
            self._session_id = f"sess_{uuid.uuid4().hex[:16]}"
            session_file.parent.mkdir(parents=True, exist_ok=True)
            session_file.write_text(self._session_id)

        # Generate configs for all MCP-supported agents
        agents_configured = 0
        for agent_name in ["claude", "gemini", "codex", "opencode"]:
            try:
                self.generate_config_for_agent(agent_name)
                agents_configured += 1
            except Exception as e:
                logger.warning(f"Failed to generate config for {agent_name}: {e}")

        self._bootstrapped = agents_configured > 0
        logger.info(f"MCP Bootstrap complete: {agents_configured} agents configured (tier: {tier})")
        return self._bootstrapped

    def get_agent_env(self) -> Dict[str, str]:
        """Get environment variables for CLI agents to connect to MCP"""
        env = {
            "AILINUX_SERVER": getattr(self, '_server_url', "https://api.ailinux.me"),
            "AILINUX_TIER": getattr(self, '_tier', "free"),
            "AILINUX_MCP_MODE": "stdio",
        }

        if hasattr(self, '_token') and self._token:
            env["AILINUX_TOKEN"] = self._token

        if hasattr(self, '_session_id') and self._session_id:
            env["AILINUX_SESSION_ID"] = self._session_id

        return env

    def generate_config_for_agent(self, agent_name: str) -> str:
        """
        Generate MCP config file for a specific agent

        Returns path to config file.
        """
        config = self._get_config_template(agent_name)
        config_path = self.config_dir / f"{agent_name}-mcp.json"

        with open(config_path, "w") as f:
            json.dump(config, f, indent=2)

        logger.info(f"Generated MCP config: {config_path}")
        return str(config_path)

    def _get_config_template(self, agent_name: str) -> Dict[str, Any]:
        """Get MCP config template for agent type"""

        # Get environment variables for MCP connection
        env_vars = self.get_agent_env()

        # Base MCP server config
        mcp_server_config = {
            "command": "python3",
            "args": ["-m", "ailinux_client.core.mcp_stdio_server"],
            "env": env_vars
        }

        # Agent-specific config formats
        if agent_name == "claude":
            # Claude Code uses standard MCP config format
            config = {
                "mcpServers": {
                    "ailinux": mcp_server_config
                }
            }
        elif agent_name == "gemini":
            # Gemini CLI uses similar format but may need adjustments
            config = {
                "mcpServers": {
                    "ailinux": mcp_server_config
                }
            }
        elif agent_name == "codex":
            # OpenAI Codex CLI format
            config = {
                "mcpServers": {
                    "ailinux": mcp_server_config
                }
            }
        elif agent_name == "opencode":
            # OpenCode format
            config = {
                "mcpServers": {
                    "ailinux": mcp_server_config
                }
            }
        else:
            # Default format
            config = {
                "mcpServers": {
                    "ailinux": mcp_server_config
                }
            }

        return config

    def get_config_path(self, agent_name: str) -> Path:
        """Get the config file path for an agent"""
        return self.config_dir / f"{agent_name}-mcp.json"

    def launch_agent(self, agent: CLIAgent, working_dir: str = None) -> Optional[subprocess.Popen]:
        """
        Launch a CLI agent with MCP config.

        Returns the subprocess handle or None if launch failed.
        """
        if not agent.mcp_supported:
            logger.warning(f"Agent {agent.name} does not support MCP")
            return None

        config_path = self.get_config_path(agent.name)
        if not config_path.exists():
            # Generate config if not exists
            self.generate_config_for_agent(agent.name)

        # Build launch command based on agent type
        env = os.environ.copy()
        env.update(self.get_agent_env())

        cmd = []
        if agent.name == "claude":
            cmd = [agent.path, "--mcp-config", str(config_path)]
        elif agent.name == "gemini":
            env["GEMINI_MCP_CONFIG"] = str(config_path)
            cmd = [agent.path]
        elif agent.name == "codex":
            cmd = [agent.path, "--mcp", str(config_path)]
        elif agent.name == "opencode":
            cmd = [agent.path, "--mcp-config", str(config_path)]
        else:
            cmd = [agent.path]

        try:
            cwd = working_dir or str(Path.home())
            process = subprocess.Popen(
                cmd,
                env=env,
                cwd=cwd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            logger.info(f"Launched {agent.display_name} with MCP config")
            return process
        except Exception as e:
            logger.error(f"Failed to launch {agent.name}: {e}")
            return None

    def bootstrap_detected_agents(self, detector: 'CLIAgentDetector') -> Dict[str, bool]:
        """
        Bootstrap MCP configs for all detected agents.

        Returns dict of agent_name -> success status.
        """
        if not self._bootstrapped:
            logger.warning("MCP server not bootstrapped - call bootstrap_for_tier first")
            return {}

        results = {}
        for agent in detector.detected_agents:
            if agent.mcp_supported:
                try:
                    self.generate_config_for_agent(agent.name)
                    results[agent.name] = True
                    logger.info(f"Bootstrapped MCP for {agent.display_name}")
                except Exception as e:
                    results[agent.name] = False
                    logger.error(f"Failed to bootstrap {agent.name}: {e}")

        return results

    def is_bootstrapped(self) -> bool:
        """Check if MCP server has been bootstrapped"""
        return self._bootstrapped

    def get_available_tools(self) -> List[Dict[str, Any]]:
        """Get list of tools provided by local MCP server"""
        return [
            {
                "name": "file_read",
                "description": "Read file from local filesystem",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "File path"}
                    },
                    "required": ["path"]
                }
            },
            {
                "name": "file_write",
                "description": "Write file to local filesystem",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "content": {"type": "string"}
                    },
                    "required": ["path", "content"]
                }
            },
            {
                "name": "file_list",
                "description": "List directory contents",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "recursive": {"type": "boolean", "default": False}
                    },
                    "required": ["path"]
                }
            },
            {
                "name": "bash_exec",
                "description": "Execute shell command",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "command": {"type": "string"},
                        "cwd": {"type": "string"}
                    },
                    "required": ["command"]
                }
            },
            {
                "name": "codebase_search",
                "description": "Search code files",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "path": {"type": "string"},
                        "file_pattern": {"type": "string"}
                    },
                    "required": ["query"]
                }
            },
            {
                "name": "git_status",
                "description": "Get git repository status",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"}
                    },
                    "required": ["path"]
                }
            },
            {
                "name": "git_diff",
                "description": "Get git diff",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "staged": {"type": "boolean", "default": False}
                    },
                    "required": ["path"]
                }
            },
            {
                "name": "git_log",
                "description": "Get git commit log",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "limit": {"type": "integer", "default": 10}
                    },
                    "required": ["path"]
                }
            },
            {
                "name": "system_info",
                "description": "Get system information (CPU, memory, disk)",
                "inputSchema": {
                    "type": "object",
                    "properties": {}
                }
            },
        ]


# Global instances
agent_detector = CLIAgentDetector()
local_mcp_server = LocalMCPServer()
