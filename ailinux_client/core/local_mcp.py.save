"""
Local MCP Executor
==================

Executes MCP tools locally on the client machine.
"""
import os
import subprocess
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass

logger = logging.getLogger("ailinux.local_mcp")


@dataclass
class MCPToolResult:
    """Result from MCP tool execution"""
    success: bool
    content: Any = None
    error: Optional[str] = None


class LocalMCPExecutor:
    """
    Executes MCP tools locally

    Available tools:
    - file_read: Read file content
    - file_write: Write file content
    - file_list: List directory contents
    - bash_exec: Execute shell command
    - codebase_search: Search code files
    - git_status: Git repository status
    """

    def __init__(self, allowed_paths: List[str] = None):
        self.allowed_paths = allowed_paths or [str(Path.home()), "/tmp"]

    def _check_path(self, path: str) -> bool:
        """Check if path is allowed"""
        try:
            resolved = str(Path(path).resolve())
            for allowed in self.allowed_paths:
                if resolved.startswith(str(Path(allowed).resolve())):
                    return True
            return False
        except:
            return False

    async def execute(self, tool: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a tool"""
        handlers = {
            "file_read": self._file_read,
            "file_write": self._file_write,
            "file_list": self._file_list,
            "file_search": self._file_search,
            "bash_exec": self._bash_exec,
            "codebase_search": self._codebase_search,
            "git_status": self._git_status,
            "git_diff": self._git_diff,
            "git_log": self._git_log,
            "system_info": self._system_info,
        }

        handler = handlers.get(tool)
        if not handler:
            return {"error": f"Unknown tool: {tool}"}

        try:
            return await handler(params)
        except Exception as e:
            logger.error(f"Tool error {tool}: {e}")
            return {"error": str(e)}

    async def _file_read(self, params: Dict) -> Dict:
        """Read file content"""
        path = params.get("path")
        if not path:
            return {"error": "path required"}

        if not self._check_path(path):
            return {"error": f"Path not allowed: {path}"}

        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()

            return {
                "path": path,
                "content": content,
                "size": len(content),
                "lines": content.count("\n") + 1
            }
        except FileNotFoundError:
            return {"error": f"File not found: {path}"}
        except Exception as e:
            return {"error": str(e)}

    async def _file_write(self, params: Dict) -> Dict:
        """Write file content"""
        path = params.get("path")
        content = params.get("content", "")

        if not path:
            return {"error": "path required"}

        if not self._check_path(path):
            return {"error": f"Path not allowed: {path}"}

        try:
            # Create parent directory if needed
            Path(path).parent.mkdir(parents=True, exist_ok=True)

            with open(path, "w", encoding="utf-8") as f:
                f.write(content)

            return {
                "path": path,
                "written": len(content),
                "success": True
            }
        except Exception as e:
            return {"error": str(e)}

    async def _file_list(self, params: Dict) -> Dict:
        """List directory contents"""
        path = params.get("path", ".")
        recursive = params.get("recursive", False)

        if not self._check_path(path):
            return {"error": f"Path not allowed: {path}"}

        try:
            p = Path(path)
            if not p.exists():
                return {"error": f"Path not found: {path}"}

            entries = []
            if recursive:
                for item in p.rglob("*"):
                    if len(entries) >= 1000:  # Limit
                        break
                    entries.append({
                        "name": str(item.relative_to(p)),
                        "type": "dir" if item.is_dir() else "file",
                        "size": item.stat().st_size if item.is_file() else 0
                    })
            else:
                for item in p.iterdir():
                    entries.append({
                        "name": item.name,
                        "type": "dir" if item.is_dir() else "file",
                        "size": item.stat().st_size if item.is_file() else 0
                    })

            return {
                "path": path,
                "entries": entries,
                "count": len(entries)
            }
        except Exception as e:
            return {"error": str(e)}

    async def _file_search(self, params: Dict) -> Dict:
        """Search for files by name pattern"""
        path = params.get("path", ".")
        pattern = params.get("pattern", "*")

        if not self._check_path(path):
            return {"error": f"Path not allowed: {path}"}

        try:
            p = Path(path)
            matches = list(p.rglob(pattern))[:100]  # Limit results

            return {
                "path": path,
                "pattern": pattern,
                "matches": [str(m) for m in matches],
                "count": len(matches)
            }
        except Exception as e:
            return {"error": str(e)}

    async def _bash_exec(self, params: Dict) -> Dict:
        """Execute shell command"""
        command = params.get("command")
        cwd = params.get("cwd")
        timeout = params.get("timeout", 30)

        if not command:
            return {"error": "command required"}

        if cwd and not self._check_path(cwd):
            return {"error": f"CWD not allowed: {cwd}"}

        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                cwd=cwd,
                timeout=timeout
            )

            return {
                "command": command,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode
            }
        except subprocess.TimeoutExpired:
            return {"error": f"Command timed out after {timeout}s"}
        except Exception as e:
            return {"error": str(e)}

    async def _codebase_search(self, params: Dict) -> Dict:
        """Search code files"""
        query = params.get("query")
        path = params.get("path", ".")
        file_pattern = params.get("file_pattern", "*.py")

        if not query:
            return {"error": "query required"}

        if not self._check_path(path):
            return {"error": f"Path not allowed: {path}"}

        try:
            # Use grep if available
            result = subprocess.run(
                ["grep", "-rn", "--include", file_pattern, query, path],
                capture_output=True,
                text=True,
                timeout=30
            )

            matches = []
            for line in result.stdout.split("\n")[:100]:
                if line:
                    parts = line.split(":", 2)
                    if len(parts) >= 3:
                        matches.append({
                            "file": parts[0],
                            "line": int(parts[1]),
                            "content": parts[2]
                        })

            return {
                "query": query,
                "matches": matches,
                "count": len(matches)
            }
        except Exception as e:
            return {"error": str(e)}

    async def _git_status(self, params: Dict) -> Dict:
        """Get git status"""
        path = params.get("path", ".")

        if not self._check_path(path):
            return {"error": f"Path not allowed: {path}"}

        try:
            result = subprocess.run(
                ["git", "status", "--porcelain", "-b"],
                capture_output=True,
                text=True,
                cwd=path
            )

            return {
                "path": path,
                "output": result.stdout,
                "is_git_repo": result.returncode == 0
            }
        except Exception as e:
            return {"error": str(e)}

    async def _git_diff(self, params: Dict) -> Dict:
        """Get git diff"""
        path = params.get("path", ".")
        staged = params.get("staged", False)

        if not self._check_path(path):
            return {"error": f"Path not allowed: {path}"}

        try:
            cmd = ["git", "diff"]
            if staged:
                cmd.append("--staged")

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=path
            )

            return {
                "path": path,
                "diff": result.stdout[:50000],  # Limit size
                "staged": staged
            }
        except Exception as e:
            return {"error": str(e)}

    async def _git_log(self, params: Dict) -> Dict:
        """Get git log"""
        path = params.get("path", ".")
        limit = params.get("limit", 10)

        if not self._check_path(path):
            return {"error": f"Path not allowed: {path}"}

        try:
            result = subprocess.run(
                ["git", "log", f"-{limit}", "--oneline"],
                capture_output=True,
                text=True,
                cwd=path
            )

            return {
                "path": path,
                "log": result.stdout,
                "commits": result.stdout.count("\n")
            }
        except Exception as e:
            return {"error": str(e)}

    async def _system_info(self, params: Dict) -> Dict:
        """Get system information"""
        try:
            import psutil
            return {
                "cpu_percent": psutil.cpu_percent(),
                "memory": {
                    "total": psutil.virtual_memory().total,
                    "available": psutil.virtual_memory().available,
                    "percent": psutil.virtual_memory().percent
                },
                "disk": {
                    "total": psutil.disk_usage("/").total,
                    "free": psutil.disk_usage("/").free,
                    "percent": psutil.disk_usage("/").percent
                },
                "platform": os.uname()._asdict()
            }
        except ImportError:
            return {
                "platform": os.uname()._asdict(),
                "error": "psutil not available for detailed stats"
            }

    def list_tools(self) -> List[Dict[str, Any]]:
        """List available tools"""
        return [
            {"name": "file_read", "description": "Read file content"},
            {"name": "file_write", "description": "Write file content"},
            {"name": "file_list", "description": "List directory contents"},
            {"name": "file_search", "description": "Search for files by pattern"},
            {"name": "bash_exec", "description": "Execute shell command"},
            {"name": "codebase_search", "description": "Search code files"},
            {"name": "git_status", "description": "Get git status"},
            {"name": "git_diff", "description": "Get git diff"},
            {"name": "git_log", "description": "Get git log"},
            {"name": "system_info", "description": "Get system information"},
        ]

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> MCPToolResult:
        """Call a tool and return MCPToolResult"""
        try:
            result = await self.execute(tool_name, arguments)
            if "error" in result:
                return MCPToolResult(success=False, error=result["error"])
            return MCPToolResult(success=True, content=result)
        except Exception as e:
            return MCPToolResult(success=False, error=str(e))


# Singleton instance
local_mcp = LocalMCPExecutor()
