# AILinux Client

Version: `4.8.0-beta`

Desktop client for the AILinux / TriForce platform.

## Overview

AILinux Client is a PyQt6 desktop application for interacting with TriForce services:

- authenticated chat against `https://api.ailinux.me`
- tier-based model access
- MCP tool listing and execution
- MCP node/websocket integration
- update checks and backend error logging

## Core Architecture

- `ailinux_client/core/api_client.py`
  - fixed backend base URL: `https://api.ailinux.me`
  - login and token flow
  - chat, model list, tier info, MCP client endpoints
- `ailinux_client/core/mcp_node_client.py`
  - websocket handshake to `/v1/mcp/node/connect`
- `ailinux_client/core/mcp_stdio_server.py`
  - MCP stdio bridge and remote MCP passthrough
- `ailinux_client/core/updater.py`
  - update metadata from `/v1/client/update/version`

## Installation (Debian/Ubuntu)

```bash
curl -fsSL https://repo.ailinux.me/mirror/archive.ailinux.me/ailinux-archive-key.gpg | sudo gpg --dearmor -o /etc/apt/trusted.gpg.d/ailinux.gpg
echo "deb https://repo.ailinux.me/mirror/archive.ailinux.me stable main" | sudo tee /etc/apt/sources.list.d/ailinux.list
sudo apt update
sudo apt install ailinux-client
```

## Run

```bash
ailinux-client
```

Safe/stable startup options:

```bash
# disable GPU + disable local/remote MCP auto-connect
python3 run.py --safe-mode

# disable only remote MCP node websocket
python3 run.py --no-mcp-node

# disable only local MCP stdio process
python3 run.py --no-local-mcp

# custom backend endpoint
python3 run.py --server https://api.ailinux.me
```

## Debug Loop

Use the built-in debug loop for repeatable stability checks:

```bash
./debug-loop.sh 3
```

Checks performed per loop:
- `compileall` for syntax regressions
- import smoke test for core/ui modules
- `run.py --hwinfo` non-GUI smoke test
- CLI parse check for stability flags

## Related Docs

- `docs/SERVER_API.md`
- `../../docs/projects/AILINUX_CLIENT_PROJECT.md`

## License

MIT
