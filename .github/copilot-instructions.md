# Copilot Instructions — AILinux / TriForce

## Project Context
This is part of the AILinux ecosystem by Markus Leitermann (@derleiti, Warzenried, Oberpfalz).
Backend: TriForce — FastAPI multi-LLM orchestration, 659+ models, MCP tools, WireGuard federation mesh.

## Stack
- Python 3.12, FastAPI, uvicorn, httpx
- Redis, Docker, Apache reverse proxy
- PyQt6 (desktop clients)
- MCP (Model Context Protocol) — JSON-RPC 2.0

## Coding Style
- Efficiency beats enthusiasm.
- No padding, no unnecessary abstraction.
- Ursache vor Fix — understand before implementing.
- Short, robust changes. No blind overwrites.
- Always syntax-check Python before suggesting: `python3 -c "import ast; ast.parse(...)"`
- Prefer subprocess over MCP for local execution.
- German variable names are acceptable, English for APIs.

## Architecture Rules
- MCP tools are READ-ONLY for aicoder users. No shell/binary_exec/code_edit on server.
- Execution (shell, service management) runs LOCALLY via subprocess.
- JWT tokens contain: client_id, sub (email), role, account_role, tier.
- Backend base URL for local/WireGuard: http://10.10.0.1:9000
- Backend base URL for external: https://api.ailinux.me

## Key Paths (Hetzner server)
- Backend: /home/zombie/triforce/
- Config: /home/zombie/triforce/config/triforce.env
- Users: /config/users.json
- WP: /home/zombie/triforce/docker/wordpress/html/

## AILinux Client Specific
- PyQt6 desktop app with JWT auth, WebSocket MCP, tier-based model access
- API endpoints: /v1/client/login, /v1/client/models, /v1/client/chat, /v1/mcp/*
- Beta code: AILINUX2026
