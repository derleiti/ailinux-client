"""
AILinux Client Version
======================
Automatisches Changelog-System
"""

VERSION = "4.0.0"
BUILD_DATE = "20251217"

# Changelog - wird automatisch bei jedem Release erweitert
CHANGELOG = """
# AILinux Client Changelog

## Version 3.0.1 (2025-12-17)

### Neu
- App-Icon Integration (Fenster, Desktop, About-Dialog)
- Erweiterter About-Dialog mit Header-Bild und Version
- Desktop-Icon für Anwendungsmenü

### Verbessert
- Desktop-Integration (.desktop file mit Icon)
- Build-Script generiert automatisch Icons in allen Größen
- Auto-Update testet Repository-Verbindung

## Version 3.0.0 (2025-12-17)

### Neu
- Tier-System v3.0 Integration (Pro: Ollama unlimited)
- Auto-Update System mit .deb Paketen
- Server-synchronisierte Modelle
- 30-Minuten Auto-Update-Check

### Technisch
- PyInstaller kompiliert
- Debian-Paket für Ubuntu/Debian
- SHA256 Checksum-Verifizierung
- Repository: repo.ailinux.me
"""
