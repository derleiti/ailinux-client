"""AILinux Client Version"""
VERSION = "5.0.0-alpha.1"
BUILD_DATE = "20260419"
API_VERSION = "5.0.0-alpha.1"
CODENAME = "Brumo 2"

CHANGELOG = """
v5.0.0-alpha.1 "Brumo 2" (2026-04-19)
=====================================
- NEW: AI Search (Ctrl+Alt+K) - Perplexity-style web search via /client/search
- NEW: OCR Quick Capture (Ctrl+Alt+O) - Copa-lite, screenshot to text via Mistral
- NEW: Token Budget Widget in status bar with live usage + tier badge
- NEW: Click tier badge (Free/Guest) to open upgrade page
- NEW: api_client.py methods: ai_search, ocr_mistral, ocr_status, get_token_usage,
       get_mcp_permissions, get_changelog, get_ollama_status
- CLEANUP: Removed 6 stale backup files from core/ (-585 LOC)
- CLEANUP: Code repo freshened for v5.x series

v4.8.0-beta "Brumo" (2026-03-12)
================================
- NEW: AI-Dateianalyse aus File-Browser (Text/Binary-Risikoprofil)
- NEW: Browser-Seitenanalyse inkl. Link-Kontext direkt im Chat
- NEW: Compact-Prompt Dispatch zu Coding-Agents
- NEW: Terminal AI Preflight (Typos vor Enter abfangen)
- NEW: Runtime Safe-Mode und MCP-Disable Flags
- FIX: MCP Node connect() stabilisiert und Legacy-Code entfernt
- FIX: syslogger robust gegen nicht beschreibbare Logpfade
"""
