# 🤖 AILinux Client Backup

Dieses Repository enthält regelmäßige **Backups des AILinux-Clients**. Gesichert werden alle wichtigen Projektdateien, KI-Agenten, Crawler, Konfigurationen und Systemdienste vom Client-System.

## 🔒 Inhalte der Backups

- `~/ailinux-brand/` – Branding-Dateien und Installer-Slideshow
- `~/novabot/` – Nova AI Desktop-Agent
- `~/nova-crawler/` – Lokaler Web- & Log-Crawler
- `~/.ollama/` – Lokale Chatbot-Modelle
- `~/backup.sh` – Das aktuelle Backup-Skript
- `/opt/nova-*` – Zusätzliche KI-bezogene Tools
- Eigene `systemd`-Dienste unter `/etc/systemd/system/`

> 🖼 Medien (Bilder/Videos) können mit `--no-images` beim Backup ausgeschlossen werden.

## 📁 Speicherorte

- 🔄 Backups: `~/backups/`
- 📤 Git Push: `~/ailinux-client-git/`
- 🔒 GitHub Remote: [`derleiti/ailinux-client`](https://github.com/derleiti/ailinux-client)

## 🚀 Backup ausführen

```bash
./backup.sh
