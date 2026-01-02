# AILinux Client

<div align="center">

![Version](https://img.shields.io/badge/version-4.3.3-blue)
![Python](https://img.shields.io/badge/python-3.10%2B-green)
![Platform](https://img.shields.io/badge/platform-linux-lightgrey)

**Desktop AI Assistant for AILinux/TriForce Platform**

</div>

---

## 🚀 Overview

PyQt6-based desktop application providing access to 686+ AI models through the TriForce backend.

## ✨ Features

- Multi-Model Chat (686+ models from 9 providers)
- Integrated Terminal with AI assistance
- MCP Tools Integration (134+ tools)
- CLI Agent Control (Claude, Codex, Gemini, OpenCode)
- Auto-Update from update.ailinux.me

## 📦 Installation

### APT Repository (Recommended)

```bash
# Add GPG key
curl -fsSL https://repo.ailinux.me/mirror/archive.ailinux.me/ailinux-archive-key.gpg | sudo gpg --dearmor -o /etc/apt/trusted.gpg.d/ailinux.gpg

# Add repository
echo "deb https://repo.ailinux.me/mirror/archive.ailinux.me stable main" | sudo tee /etc/apt/sources.list.d/ailinux.list

# Install
sudo apt update && sudo apt install ailinux-client
```

### Direct Download

```bash
wget https://update.ailinux.me/client/linux/ailinux-client_4.3.3_amd64.deb
sudo dpkg -i ailinux-client_4.3.3_amd64.deb
```

## 🔧 Requirements

- Python 3.10+
- PyQt6 + PyQt6-WebEngine
- Debian/Ubuntu Linux

## 📖 Usage

```bash
ailinux-client
```

## 📄 License

MIT License

---

**Part of [AILinux](https://ailinux.me)**
