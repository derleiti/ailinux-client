ailinux-client/README.md
markdown
Kopieren
Bearbeiten
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
Auswahl im Menü erlaubt Git Push oder Anzeige des Backup-Verzeichnisses.

🧠 Git LFS
Alle .zip-Dateien werden automatisch via Git Large File Storage (LFS) versioniert.

🔐 Sicherheit
Das Token für den GitHub Push wird sicher aus ~/.pat_git geladen. Beispiel:

bash
Kopieren
Bearbeiten
echo 'export GITHUB_PAT=ghp_xxx' > ~/.pat_git
chmod 600 ~/.pat_git
🛠 Wartung
.gitignore: ignoriert server/, um Konflikte zu vermeiden

.gitattributes: konfiguriert Git LFS für .zip

💬 Kontakt
Maintained by Markus Leitermann & Nova AI 🤝
https://derleiti.de · https://ailinux.me
