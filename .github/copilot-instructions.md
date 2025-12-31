# Copilot instructions for AILinux Client

This project is a PyQt6-based desktop client with a hardware-optimized bootstrap, an HTTP API client, and an MCP (agent) stdio proxy. Keep guidance focused, actionable, and repository-specific.

High-level architecture
- The bootstrap is `run.py`: does hardware detection, sets env vars, then calls `ailinux_client.main.main()`.
- The GUI entry is `ailinux_client/main.py`: MUST set Qt-related environment and `QSurfaceFormat` BEFORE importing Qt widgets or WebEngine.
- Core services live under `ailinux_client/core/` (API client, MCP stdio server, hardware detection, tier manager, etc.).
- UI lives under `ailinux_client/ui/` and uses PyQt6 Widgets (not QML).

What to watch for (rules for edits)
- Always set Qt env variables and call `_setup_surface_format()` before any `PyQt6` widget import. See `ailinux_client/main.py` for exact locations and examples.
- The app tries `httpx` first, falls back to `requests` if `httpx` is unavailable. Use the same pattern when adding new HTTP code (see `ailinux_client/core/api_client.py`).
- Credentials and session files are stored under `~/.config/ailinux/` (e.g. `credentials.json`, `session_id`). Code often assumes secure file perms (0o600).
- Environment variables commonly used: `AILINUX_SERVER`, `AILINUX_TOKEN`, `AILINUX_TIER`, `AILINUX_CLIENT_CERT`, `AILINUX_CA_CERT`, `AILINUX_WSS_PORT`. Use these for local testing and daemons.
- Graceful shutdown hooks: `run.py` exposes `register_cleanup()` and `set_main_window()` — use these to ensure background threads/servers stop cleanly.

MCP / Agent specifics
- `ailinux_client/core/mcp_stdio_server.py` implements a JSON-RPC-over-stdio MCP proxy used by CLI agents. It:
  - Filters remote tools by `tier` (see `TIER_TOOLS`).
  - Exposes local-only tools prefixed with `local_` (e.g. `local_file_read`).
  - Maintains read-only telemetry via a WebSocket; remote tool execution from the server is explicitly blocked.
- When editing MCP behavior, preserve the tier-filter logic and never enable remote code execution in telemetry loops.

Developer workflows & common commands
- Install dependencies: `pip install -r requirements.txt` (virtualenv recommended).
- Launch the app (dev):
  - `./run-ailinux.sh` or `python3 run.py` (bootstrap + GUI)
  - `python -m ailinux_client` (module entry)
- Non-GUI helpers:
  - Show hardware info: `python3 run.py --hwinfo`
  - Run benchmark: `python3 run.py --benchmark`
  - MCP daemon (telemetry): `python3 run_mcp_daemon.py`

Patterns & examples to reference
- Hardware/Qt ordering: `run.py` -> `_early_optimizations()` -> `_setup_qt_environment()` -> `ailinux_client.main._setup_surface_format()`
- API client usage: instantiate `APIClient()` from `ailinux_client/core/api_client.py` and call `.is_authenticated()`, `.login()`, `.get_models()`.
- Telemetry & mTLS: `run_mcp_daemon.py` shows environment variables and how mTLS certs are expected (see `mcp_stdio_server`'s `_bootstrap_telemetry`).

Testing and CI notes
- There is a Windows build workflow under `.github/workflows/`. Local CI and packaging may require platform-specific Qt packages.
- When adding integration tests that import Qt, ensure test harness sets the same QSurfaceFormat and Qt env variables before importing PyQt6.

Editing checklist for PRs
- If touching startup/Qt code: verify no PyQt imports occur before environment setup.
- If touching network code: prefer `httpx` async client patterns used in `mcp_stdio_server.py` for async flows and fall back to sync `requests` where consistent.
- Preserve telemetry safety: do not allow server-initiated execution on the client.

If anything is unclear, ask for the exact file and line to examine — include a short rationale for changes that affect startup order, networking, or security.
