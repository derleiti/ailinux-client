# AILinux Client

<div align="center">

![Version](https://img.shields.io/badge/version-4.3.3-blue)
![Python](https://img.shields.io/badge/python-3.10%2B-green)
![Platform](https://img.shields.io/badge/platform-linux-lightgrey)
![License](https://img.shields.io/badge/license-MIT-green)

**Desktop AI Assistant for AILinux/TriForce Platform**

[Installation](#installation) • [Features](#features) • [Usage](#usage) • [Development](#development)

</div>

---

## 🚀 Overview

AILinux Client is a PyQt6-based desktop application that provides access to 686+ AI models through the TriForce backend. It features multi-tab chat, terminal integration, file browser, and MCP tool support.

## ✨ Features

- **Multi-Model Chat**: Access 686+ models from 9 providers (Gemini, Anthropic, Groq, Mistral, etc.)
- **Multi-Tab Interface**: Open multiple chat sessions simultaneously
- **Integrated Terminal**: Built-in terminal with AI assistance
- **File Browser**: Navigate and open files with AI context
- **CLI Agents**: Control autonomous AI agents (Claude, Codex, Gemini, OpenCode)
- **MCP Integration**: 134+ MCP tools available
- **Desktop Panel**: Quick-access panel for common actions
- **Theme Support**: Multiple color schemes
- **Tor Support**: Optional Tor proxy for privacy
- **Auto-Update**: Automatic updates from update.ailinux.me

## 📦 Installation

### Debian/Ubuntu (Recommended)

```bash
# Add repository
echo "deb https://repo.ailinux.me stable main" | sudo tee /etc/apt/sources.list.d/ailinux.list
curl -fsSL https://repo.ailinux.me/pubkey.gpg | sudo gpg --dearmor -o /etc/apt/trusted.gpg.d/ailinux.gpg
sudo apt update

# Install
sudo apt install ailinux-client
```

### Direct Download

```bash
wget https://repo.ailinux.me/pool/main/ailinux-client_4.3.3_amd64.deb
sudo dpkg -i ailinux-client_4.3.3_amd64.deb
sudo apt-get install -f  # Install dependencies
```

### From Source

```bash
git clone https://github.com/derleiti/ailinux-client.git
cd ailinux-client
pip install -r requirements.txt
python -m ailinux_client
```

## 🔧 Requirements

- Python 3.10+
- PyQt6 + PyQt6-WebEngine
- Linux (Debian/Ubuntu recommended)
- Internet connection

## 📖 Usage

### Launch

```bash
# From terminal
ailinux-client

# Or
python -m ailinux_client
```

### Configuration

Configuration is stored in `~/.config/ailinux-client/`:

```
~/.config/ailinux-client/
├── config.json      # Main configuration
├── auth.json        # Authentication tokens
└── themes/          # Custom themes
```

### API Configuration

```json
{
  "api_url": "https://api.ailinux.me",
  "default_model": "gemini/gemini-2.0-flash",
  "theme": "dark"
}
```

## 🏗️ Architecture

```
ailinux_client/
├── core/              # Core functionality
│   ├── api_client.py  # API communication
│   ├── auth.py        # Authentication
│   ├── config.py      # Configuration
│   └── updater.py     # Auto-update
├── ui/                # UI components
│   ├── main_window.py # Main window
│   ├── chat_widget.py # Chat interface
│   ├── terminal.py    # Terminal widget
│   └── file_browser.py # File browser
├── translations/      # i18n (de, es, fr)
└── resources/         # Icons, themes
```

## 🔄 Updates

The client automatically checks for updates from `update.ailinux.me`. Updates are downloaded and installed on next restart.

Manual update check:
```bash
ailinux-client --check-update
```

## 🛠️ Development

```bash
# Clone
git clone https://github.com/derleiti/ailinux-client.git
cd ailinux-client

# Install dev dependencies
pip install -r requirements-dev.txt

# Run in development mode
python -m ailinux_client --debug

# Build DEB package
./build-deb.sh
```

## 📄 License

MIT License - see [LICENSE](LICENSE)

---

<div align="center">

**Part of the [AILinux](https://ailinux.me) Platform**

</div>
