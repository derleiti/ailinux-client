"""
AILinux Client Core Modules v2.1
"""
from .api_client import APIClient
from .local_mcp import LocalMCPExecutor
from .cli_agents import CLIAgentDetector, agent_detector, LocalMCPServer, local_mcp_server, CLIAgent
from .sudo_manager import SudoManager, get_sudo_manager, sudo_run, sudo_restart_service, sudo_write_file
from .model_sync import ModelSyncManager, ModelInfo, get_model_sync, init_model_sync

__all__ = [
    "APIClient",
    "LocalMCPExecutor",
    "CLIAgentDetector",
    "agent_detector",
    "LocalMCPServer",
    "local_mcp_server",
    "CLIAgent",
    "SudoManager",
    "get_sudo_manager",
    "sudo_run",
    "sudo_restart_service",
    "sudo_write_file",
    "ModelSyncManager",
    "ModelInfo",
    "get_model_sync",
    "init_model_sync",
]
