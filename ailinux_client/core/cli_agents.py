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
    to our local MCP tool server.
    """

    def __init__(self, server_port: int = 9876):
        self.server_port = server_port
        self.config_dir = Path.home() / ".config" / "ailinux" / "mcp"
        self.config_dir.mkdir(parents=True, exist_ok=True)

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

        # Base config with stdio server
        config = {
            "mcpServers": {
                "ailinux-local": {
                    "command": "python3",
                    "args": [
                        "-m", "ailinux_client.core.mcp_stdio_server"
                    ],
                    "env": {
                        "AILINUX_MCP_MODE": "stdio"
                    }
                }
            }
        }

        # Agent-specific adjustments
        if agent_name == "claude":
            # Claude Code uses standard MCP config
            pass
        elif agent_name == "gemini":
            # Gemini might use different format
            pass
        elif agent_name == "codex":
            # Codex format
            pass

        return config

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
