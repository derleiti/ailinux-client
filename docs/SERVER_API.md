# AILinux Client -> TriForce Server API

Stand: TriForce `v0.7.0-beta`, Client `v4.8.0-beta`

Diese Seite beschreibt die Endpunkte, die der Client-Code aktuell wirklich nutzt.

## Base URL

`https://api.ailinux.me`

Implementierung: `ailinux_client/core/api_client.py` (`APIClient.BASE_URL`).

## Authentication

### Login

- `POST /v1/auth/login`
- Payload: `email`, `password`
- Ergebnis: `user_id`, `token`, `tier`, `client_id`

### Token via Client Credentials

- `POST /v1/auth/token`
- Header: `client_id`, `client_secret`

### Device Registration

- `POST /v1/users/{user_id}/devices`

## Chat and Models

### Chat

- `POST /v1/client/chat`
- Hauptfelder: `message`, optional `model`, optional `system_prompt`, `temperature`

### Model List

- `GET /v1/client/models`
- Rueckgabe enthaelt u.a. `tier`, `model_count`, `models`, `backend`

### Tier Info

- `GET /v1/client/tier`

## MCP (Client Layer)

### List Tools

- `GET /v1/client/mcp/tools`

### Call Tool

- `POST /v1/client/mcp/call`
- Payload: `tool`, `params`

## MCP Node / Realtime

### Node Connect

- WebSocket: `/v1/mcp/node/connect`
- Verwendet in `mcp_node_client.py` und `mcp_stdio_server.py`

### Generic MCP JSON-RPC

- `POST /v1/mcp`
- Verwendet in `mcp_stdio_server.py`

### Support Bridge

- `POST /v1/mcp/node/support/call`
- Verwendet in `mcp_stdio_server.py`

## Settings Sync

- `GET /v1/users/{user_id}/settings`
- `POST /v1/users/{user_id}/settings`
- Encrypted settings optional via `/v1/user/settings/sync` (siehe `encrypted_settings.py`)

## Logging and Ops

### Client Log Upload

- `POST /v1/client/logs`
- Verwendet in `syslogger.py`

### Contributor/Federation Registration

- `POST /v1/federation/contributor/register`
- Verwendet in `contributor.py`

### Update Check

- `GET /v1/client/update/version`
- Verwendet in `updater.py`

## Hinweis zur API-Pflegestrategie

Diese Doku wird bewusst aus dem echten Client-Code abgeleitet, nicht aus Wunsch-Endpunkten. Wenn ein Endpoint hier auftaucht, ist er im aktuellen Clientpfad integriert.
