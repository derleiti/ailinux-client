"""AILinux Client Version"""
VERSION = "4.3.0"
BUILD_DATE = "2025-12-31"
API_VERSION = "v1"
CODENAME = "Brumo"

CHANGELOG = """
v4.3.0 "Brumo" (2025-12-31)
===========================
- FIX: mcp_node_client.py connect() Einrückung (war außerhalb Klasse)
- FIX: model_sync.py async→sync + korrekter Endpoint
- NEW: CLI Agents REST API (/v1/agents/cli)
- NEW: Server Federation mit Auto-Healing
- NEW: Contributor Mode (Hardware teilen)
- NEW: Federation Status & Nodes Endpoints
"""
