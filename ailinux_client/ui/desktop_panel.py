"""
AILinux Desktop Panel
=====================

System tray/status bar with:
- App launcher (categories)
- Clock/Date
- Weather
- Network status
- CPU/RAM usage
- Battery
- Volume control

Designed for lean Linux with Ubuntu apt package manager.
Dependencies: python3-pyqt6, python3-psutil (apt install)
"""
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QMenu, QFrame, QSizePolicy, QToolButton, QSlider,
    QWidgetAction, QApplication, QSystemTrayIcon
)
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal, QProcess, QSize, QSettings
from PyQt6.QtGui import QIcon, QFont, QAction, QPixmap, QPainter, QColor
import subprocess
import os
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List, Any

logger = logging.getLogger("ailinux.desktop_panel")

# Optional imports with fallbacks
try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False
    logger.warning("psutil not installed - system stats disabled (apt install python3-psutil)")

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


# =============================================================================
# Base Status Widget
# =============================================================================

class StatusWidget(QFrame):
    """Base class for status bar widgets"""

    clicked = pyqtSignal()

    def __init__(self, parent=None, update_interval: int = 5000):
        super().__init__(parent)
        self.setFrameStyle(QFrame.Shape.NoFrame)
        self.setStyleSheet("""
            StatusWidget {
                background: transparent;
                padding: 2px 6px;
                border-radius: 4px;
            }
            StatusWidget:hover {
                background: rgba(255, 255, 255, 0.1);
            }
        """)

        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(4, 2, 4, 2)
        self.layout.setSpacing(4)

        self.icon_label = QLabel()
        self.icon_label.setFixedSize(16, 16)
        self.text_label = QLabel()
        self.text_label.setStyleSheet("color: #e0e0e0; font-size: 12px;")

        self.layout.addWidget(self.icon_label)
        self.layout.addWidget(self.text_label)

        # Update timer
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_status)
        if update_interval > 0:
            self.timer.start(update_interval)

        # Initial update
        QTimer.singleShot(100, self.update_status)

    def update_status(self):
        """Override in subclass"""
        pass

    def set_icon(self, icon_char: str, color: str = "#ffffff"):
        """Set emoji/unicode icon"""
        self.icon_label.setText(icon_char)
        self.icon_label.setStyleSheet(f"color: {color}; font-size: 14px;")

    def set_text(self, text: str):
        """Set status text"""
        self.text_label.setText(text)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


# =============================================================================
# Clock Widget
# =============================================================================

class ClockWidget(StatusWidget):
    """Date and time display"""

    def __init__(self, parent=None, show_date: bool = True, show_seconds: bool = False):
        super().__init__(parent, update_interval=1000)
        self.show_date = show_date
        self.show_seconds = show_seconds
        self.set_icon("")  # No icon, just text
        self.icon_label.hide()
        self.text_label.setStyleSheet("color: #ffffff; font-size: 12px; font-weight: bold;")

    def update_status(self):
        now = datetime.now()
        if self.show_seconds:
            time_str = now.strftime("%H:%M:%S")
        else:
            time_str = now.strftime("%H:%M")

        if self.show_date:
            date_str = now.strftime("%a %d.%m")
            self.set_text(f"{date_str}  {time_str}")
        else:
            self.set_text(time_str)


# =============================================================================
# Weather Widget
# =============================================================================

class WeatherWorker(QThread):
    """Background weather fetch"""
    result = pyqtSignal(dict)

    def __init__(self, location: str = ""):
        super().__init__()
        self.location = location

    def run(self):
        try:
            # Use wttr.in API (no key required)
            url = f"https://wttr.in/{self.location}?format=j1"

            if HAS_REQUESTS:
                import requests
                resp = requests.get(url, timeout=5)
                data = resp.json()
            else:
                # Fallback to curl
                result = subprocess.run(
                    ["curl", "-s", "--connect-timeout", "5", url],
                    capture_output=True, text=True
                )
                if result.returncode == 0:
                    data = json.loads(result.stdout)
                else:
                    data = {}

            if data and "current_condition" in data:
                current = data["current_condition"][0]
                self.result.emit({
                    "temp": current.get("temp_C", "?"),
                    "feels": current.get("FeelsLikeC", "?"),
                    "desc": current.get("weatherDesc", [{}])[0].get("value", ""),
                    "humidity": current.get("humidity", "?"),
                    "wind": current.get("windspeedKmph", "?"),
                    "icon": self._get_weather_icon(current.get("weatherCode", ""))
                })
            else:
                self.result.emit({"error": "No data"})

        except Exception as e:
            self.result.emit({"error": str(e)})

    def _get_weather_icon(self, code: str) -> str:
        """Convert weather code to emoji"""
        code = str(code)
        icons = {
            "113": "☀️",   # Sunny
            "116": "⛅",   # Partly cloudy
            "119": "☁️",   # Cloudy
            "122": "☁️",   # Overcast
            "143": "🌫️",   # Mist
            "176": "🌧️",   # Patchy rain
            "179": "🌨️",   # Patchy snow
            "182": "🌧️",   # Patchy sleet
            "200": "⛈️",   # Thunder
            "227": "❄️",   # Blowing snow
            "230": "❄️",   # Blizzard
            "248": "🌫️",   # Fog
            "260": "🌫️",   # Freezing fog
            "263": "🌧️",   # Patchy light drizzle
            "266": "🌧️",   # Light drizzle
            "281": "🌧️",   # Freezing drizzle
            "284": "🌧️",   # Heavy freezing drizzle
            "293": "🌧️",   # Patchy light rain
            "296": "🌧️",   # Light rain
            "299": "🌧️",   # Moderate rain
            "302": "🌧️",   # Heavy rain
            "305": "🌧️",   # Heavy rain
            "308": "🌧️",   # Heavy rain
            "311": "🌧️",   # Freezing rain
            "314": "🌧️",   # Heavy freezing rain
            "317": "🌨️",   # Light sleet
            "320": "🌨️",   # Moderate sleet
            "323": "🌨️",   # Patchy snow
            "326": "🌨️",   # Light snow
            "329": "❄️",   # Patchy moderate snow
            "332": "❄️",   # Moderate snow
            "335": "❄️",   # Heavy snow
            "338": "❄️",   # Heavy snow
            "350": "🌨️",   # Ice pellets
            "353": "🌧️",   # Light rain shower
            "356": "🌧️",   # Moderate rain shower
            "359": "🌧️",   # Torrential rain
            "362": "🌨️",   # Light sleet shower
            "365": "🌨️",   # Moderate sleet shower
            "368": "🌨️",   # Light snow shower
            "371": "❄️",   # Moderate snow shower
            "374": "🌨️",   # Light ice pellets
            "377": "🌨️",   # Moderate ice pellets
            "386": "⛈️",   # Patchy rain with thunder
            "389": "⛈️",   # Moderate rain with thunder
            "392": "⛈️",   # Patchy snow with thunder
            "395": "⛈️",   # Moderate snow with thunder
        }
        return icons.get(code, "🌡️")


class WeatherWidget(StatusWidget):
    """Weather display with wttr.in"""

    def __init__(self, parent=None, location: str = ""):
        super().__init__(parent, update_interval=600000)  # 10 min
        self.location = location
        self.worker = None
        self.set_icon("🌡️")
        self.set_text("--°C")

        # Tooltip with more details
        self.setToolTip("Weather: Loading...")

    def update_status(self):
        if self.worker and self.worker.isRunning():
            return

        self.worker = WeatherWorker(self.location)
        self.worker.result.connect(self._on_weather_result)
        self.worker.start()

    def _on_weather_result(self, data: dict):
        if "error" in data:
            self.set_text("--°C")
            self.setToolTip(f"Weather: {data['error']}")
        else:
            self.set_icon(data.get("icon", "🌡️"))
            self.set_text(f"{data['temp']}°C")
            self.setToolTip(
                f"Weather: {data['desc']}\n"
                f"Feels like: {data['feels']}°C\n"
                f"Humidity: {data['humidity']}%\n"
                f"Wind: {data['wind']} km/h"
            )


# =============================================================================
# Network Widget
# =============================================================================

class NetworkWidget(StatusWidget):
    """Network status and speed"""

    def __init__(self, parent=None):
        super().__init__(parent, update_interval=2000)
        self.last_bytes_sent = 0
        self.last_bytes_recv = 0
        self.set_icon("📶")

    def update_status(self):
        if not HAS_PSUTIL:
            self.set_text("N/A")
            return

        try:
            # Check connection status
            net_if = psutil.net_if_stats()
            connected = any(v.isup for v in net_if.values() if v.isup)

            if not connected:
                self.set_icon("📵", "#ff6b6b")
                self.set_text("Offline")
                return

            # Get network I/O
            net_io = psutil.net_io_counters()

            # Calculate speed
            sent_speed = (net_io.bytes_sent - self.last_bytes_sent) / 2  # bytes/sec
            recv_speed = (net_io.bytes_recv - self.last_bytes_recv) / 2

            self.last_bytes_sent = net_io.bytes_sent
            self.last_bytes_recv = net_io.bytes_recv

            # Format speed
            def format_speed(bps):
                if bps < 1024:
                    return f"{bps:.0f}B"
                elif bps < 1024 * 1024:
                    return f"{bps/1024:.1f}K"
                else:
                    return f"{bps/1024/1024:.1f}M"

            self.set_icon("📶", "#4ade80")
            self.set_text(f"↓{format_speed(recv_speed)} ↑{format_speed(sent_speed)}")

            # Tooltip with interface info
            interfaces = []
            addrs = psutil.net_if_addrs()
            for iface, stats in net_if.items():
                if stats.isup and iface != "lo":
                    ip = "N/A"
                    if iface in addrs:
                        for addr in addrs[iface]:
                            if addr.family.name == "AF_INET":
                                ip = addr.address
                                break
                    interfaces.append(f"{iface}: {ip}")

            self.setToolTip("Network:\n" + "\n".join(interfaces) if interfaces else "Network: Connected")

        except Exception as e:
            self.set_text("Error")
            logger.error(f"Network status error: {e}")


# =============================================================================
# CPU Widget
# =============================================================================

class CpuWidget(StatusWidget):
    """CPU usage display"""

    def __init__(self, parent=None):
        super().__init__(parent, update_interval=2000)
        self.set_icon("💻")

    def update_status(self):
        if not HAS_PSUTIL:
            self.set_text("N/A")
            return

        try:
            cpu_percent = psutil.cpu_percent(interval=0)

            # Color based on load
            if cpu_percent < 50:
                color = "#4ade80"  # Green
            elif cpu_percent < 80:
                color = "#fbbf24"  # Yellow
            else:
                color = "#ef4444"  # Red

            self.set_icon("💻", color)
            self.set_text(f"{cpu_percent:.0f}%")

            # Tooltip with per-core info
            per_cpu = psutil.cpu_percent(percpu=True)
            freq = psutil.cpu_freq()
            tooltip = f"CPU: {cpu_percent:.1f}%\n"
            if freq:
                tooltip += f"Freq: {freq.current:.0f} MHz\n"
            tooltip += f"Cores: {' '.join(f'{p:.0f}%' for p in per_cpu[:8])}"
            self.setToolTip(tooltip)

        except Exception as e:
            self.set_text("Err")
            logger.error(f"CPU status error: {e}")


# =============================================================================
# Memory Widget
# =============================================================================

class MemoryWidget(StatusWidget):
    """RAM usage display"""

    def __init__(self, parent=None):
        super().__init__(parent, update_interval=5000)
        self.set_icon("🧠")

    def update_status(self):
        if not HAS_PSUTIL:
            self.set_text("N/A")
            return

        try:
            mem = psutil.virtual_memory()
            percent = mem.percent

            # Color based on usage
            if percent < 60:
                color = "#4ade80"
            elif percent < 85:
                color = "#fbbf24"
            else:
                color = "#ef4444"

            self.set_icon("🧠", color)

            # Format used/total
            used_gb = mem.used / (1024 ** 3)
            total_gb = mem.total / (1024 ** 3)
            self.set_text(f"{used_gb:.1f}G")

            # Tooltip
            swap = psutil.swap_memory()
            self.setToolTip(
                f"RAM: {used_gb:.1f}G / {total_gb:.1f}G ({percent:.0f}%)\n"
                f"Available: {mem.available / (1024**3):.1f}G\n"
                f"Swap: {swap.used / (1024**3):.1f}G / {swap.total / (1024**3):.1f}G"
            )

        except Exception as e:
            self.set_text("Err")
            logger.error(f"Memory status error: {e}")


# =============================================================================
# Battery Widget
# =============================================================================

class BatteryWidget(StatusWidget):
    """Battery status (for laptops)"""

    def __init__(self, parent=None):
        super().__init__(parent, update_interval=30000)
        self.has_battery = False
        self.set_icon("🔋")

    def update_status(self):
        if not HAS_PSUTIL:
            self.hide()
            return

        try:
            battery = psutil.sensors_battery()

            if battery is None:
                self.hide()
                return

            self.show()
            self.has_battery = True
            percent = battery.percent
            plugged = battery.power_plugged

            # Icon based on level and charging
            if plugged:
                icon = "🔌"
                color = "#4ade80"
            elif percent > 80:
                icon = "🔋"
                color = "#4ade80"
            elif percent > 40:
                icon = "🔋"
                color = "#fbbf24"
            elif percent > 20:
                icon = "🪫"
                color = "#f97316"
            else:
                icon = "🪫"
                color = "#ef4444"

            self.set_icon(icon, color)
            self.set_text(f"{percent:.0f}%")

            # Tooltip with time remaining
            if battery.secsleft > 0 and not plugged:
                hours = battery.secsleft // 3600
                mins = (battery.secsleft % 3600) // 60
                time_str = f"{hours}h {mins}m remaining"
            elif plugged:
                time_str = "Charging" if percent < 100 else "Fully charged"
            else:
                time_str = "Calculating..."

            self.setToolTip(f"Battery: {percent:.0f}%\n{time_str}")

        except Exception as e:
            self.hide()
            logger.error(f"Battery status error: {e}")


# =============================================================================
# Volume Widget
# =============================================================================

class VolumeWidget(StatusWidget):
    """Volume control (PulseAudio/PipeWire)"""

    def __init__(self, parent=None):
        super().__init__(parent, update_interval=5000)
        self.set_icon("🔊")
        self.muted = False
        self.volume = 50

    def update_status(self):
        try:
            # Try pactl (PulseAudio/PipeWire)
            result = subprocess.run(
                ["pactl", "get-sink-volume", "@DEFAULT_SINK@"],
                capture_output=True, text=True, timeout=2
            )

            if result.returncode == 0:
                # Parse volume (format: "Volume: front-left: 65536 / 100%...")
                output = result.stdout
                for part in output.split():
                    if "%" in part:
                        self.volume = int(part.replace("%", "").replace("/", ""))
                        break

            # Check mute status
            mute_result = subprocess.run(
                ["pactl", "get-sink-mute", "@DEFAULT_SINK@"],
                capture_output=True, text=True, timeout=2
            )
            self.muted = "yes" in mute_result.stdout.lower()

            # Update display
            if self.muted:
                self.set_icon("🔇", "#888888")
                self.set_text("Mute")
            elif self.volume == 0:
                self.set_icon("🔈")
                self.set_text("0%")
            elif self.volume < 50:
                self.set_icon("🔉")
                self.set_text(f"{self.volume}%")
            else:
                self.set_icon("🔊")
                self.set_text(f"{self.volume}%")

            self.setToolTip(f"Volume: {self.volume}%\nClick to mute/unmute")

        except Exception as e:
            self.set_text("N/A")
            logger.debug(f"Volume status error: {e}")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.toggle_mute()
        elif event.button() == Qt.MouseButton.RightButton:
            self.show_volume_menu(event.globalPosition().toPoint())
        super().mousePressEvent(event)

    def toggle_mute(self):
        try:
            subprocess.run(
                ["pactl", "set-sink-mute", "@DEFAULT_SINK@", "toggle"],
                timeout=2
            )
            QTimer.singleShot(100, self.update_status)
        except Exception as e:
            logger.error(f"Mute toggle error: {e}")

    def show_volume_menu(self, pos):
        menu = QMenu(self)

        # Volume slider
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(0, 150)
        slider.setValue(self.volume)
        slider.setFixedWidth(150)
        slider.valueChanged.connect(self.set_volume)

        slider_action = QWidgetAction(menu)
        slider_action.setDefaultWidget(slider)
        menu.addAction(slider_action)

        menu.addSeparator()
        menu.addAction("Open Sound Settings", self.open_sound_settings)

        menu.exec(pos)

    def set_volume(self, value: int):
        try:
            subprocess.run(
                ["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{value}%"],
                timeout=2
            )
            self.volume = value
            self.update_status()
        except Exception as e:
            logger.error(f"Set volume error: {e}")

    def open_sound_settings(self):
        for cmd in ["pavucontrol", "gnome-control-center sound", "systemsettings5 kcm_pulseaudio"]:
            try:
                subprocess.Popen(cmd.split(), start_new_session=True)
                return
            except:
                continue


# =============================================================================
# App Launcher
# =============================================================================

class AppLauncherButton(QToolButton):
    """App launcher with category menus"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setText("Apps")
        self.setIcon(QIcon.fromTheme("applications-all", QIcon.fromTheme("start-here")))
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.setStyleSheet("""
            QToolButton {
                background: #3b82f6;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 4px 10px;
                font-weight: bold;
            }
            QToolButton:hover {
                background: #2563eb;
            }
            QToolButton::menu-indicator {
                image: none;
            }
        """)

        self._build_menu()

    def _build_menu(self):
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background: #1e1e1e;
                color: #e0e0e0;
                border: 1px solid #333;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 20px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background: #3b82f6;
            }
            QMenu::separator {
                height: 1px;
                background: #333;
                margin: 4px 10px;
            }
        """)

        # Categories with apps
        categories = {
            "System": [
                ("Terminal", "x-terminal-emulator", ["gnome-terminal", "konsole", "xfce4-terminal", "xterm"]),
                ("Files", "system-file-manager", ["nautilus", "dolphin", "thunar", "pcmanfm"]),
                ("Settings", "preferences-system", ["gnome-control-center", "systemsettings5", "xfce4-settings-manager"]),
                ("Task Manager", "utilities-system-monitor", ["gnome-system-monitor", "ksysguard", "xfce4-taskmanager", "htop"]),
            ],
            "Internet": [
                ("Firefox", "firefox", ["firefox", "firefox-esr"]),
                ("Chrome", "google-chrome", ["google-chrome", "chromium", "chromium-browser"]),
                ("Email", "internet-mail", ["thunderbird", "geary", "evolution"]),
            ],
            "Development": [
                ("VS Code", "code", ["code", "codium"]),
                ("PyCharm", "pycharm", ["pycharm", "pycharm-community"]),
                ("Git GUI", "git", ["gitk", "git-gui", "gitg"]),
            ],
            "Media": [
                ("VLC", "vlc", ["vlc"]),
                ("Music", "audio-x-generic", ["rhythmbox", "spotify", "audacious"]),
                ("Images", "image-x-generic", ["eog", "gwenview", "feh"]),
            ],
            "AILinux": [
                ("AILinux Client", "applications-ai", ["ailinux-client"]),
                ("Claude Code", "terminal", ["claude"]),
                ("Gemini CLI", "terminal", ["gemini"]),
            ],
        }

        for category, apps in categories.items():
            submenu = menu.addMenu(category)
            for name, icon_name, commands in apps:
                action = submenu.addAction(QIcon.fromTheme(icon_name), name)
                action.setData(commands)
                action.triggered.connect(lambda checked, cmds=commands: self._launch_app(cmds))

        menu.addSeparator()

        # Power options
        power_menu = menu.addMenu("Power")
        power_menu.addAction("Lock Screen", lambda: self._run_cmd(["loginctl", "lock-session"]))
        power_menu.addAction("Log Out", lambda: self._run_cmd(["loginctl", "terminate-user", os.getenv("USER", "")]))
        power_menu.addSeparator()
        power_menu.addAction("Reboot", lambda: self._run_cmd(["systemctl", "reboot"]))
        power_menu.addAction("Shutdown", lambda: self._run_cmd(["systemctl", "poweroff"]))

        self.setMenu(menu)

    def _launch_app(self, commands: List[str]):
        """Try to launch app from list of possible commands"""
        for cmd in commands:
            try:
                # Check if command exists
                result = subprocess.run(["which", cmd], capture_output=True)
                if result.returncode == 0:
                    subprocess.Popen([cmd], start_new_session=True)
                    return
            except:
                continue

        logger.warning(f"No app found for: {commands}")

    def _run_cmd(self, cmd: List[str]):
        try:
            subprocess.run(cmd, timeout=5)
        except Exception as e:
            logger.error(f"Command error: {e}")


# =============================================================================
# Workspace Indicator
# =============================================================================

class WorkspaceWidget(StatusWidget):
    """Virtual desktop/workspace indicator"""

    def __init__(self, parent=None):
        super().__init__(parent, update_interval=1000)
        self.current_workspace = 1
        self.total_workspaces = 4
        self.set_icon("🖥️")

    def update_status(self):
        try:
            # Try wmctrl for workspace info
            result = subprocess.run(
                ["wmctrl", "-d"],
                capture_output=True, text=True, timeout=2
            )

            if result.returncode == 0:
                lines = result.stdout.strip().split("\n")
                self.total_workspaces = len(lines)
                for i, line in enumerate(lines):
                    if "*" in line:
                        self.current_workspace = i + 1
                        break

                self.set_text(f"{self.current_workspace}/{self.total_workspaces}")
            else:
                self.set_text("1/1")

        except FileNotFoundError:
            # wmctrl not installed
            self.set_text("1/1")
        except Exception as e:
            logger.debug(f"Workspace error: {e}")
            self.set_text("1/1")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.next_workspace()
        elif event.button() == Qt.MouseButton.RightButton:
            self.prev_workspace()
        super().mousePressEvent(event)

    def next_workspace(self):
        next_ws = (self.current_workspace % self.total_workspaces) + 1
        self._switch_workspace(next_ws - 1)

    def prev_workspace(self):
        prev_ws = ((self.current_workspace - 2) % self.total_workspaces) + 1
        self._switch_workspace(prev_ws - 1)

    def _switch_workspace(self, index: int):
        try:
            subprocess.run(["wmctrl", "-s", str(index)], timeout=2)
            QTimer.singleShot(100, self.update_status)
        except Exception as e:
            logger.debug(f"Switch workspace error: {e}")


# =============================================================================
# Main Desktop Panel
# =============================================================================

class DesktopPanel(QFrame):
    """
    Main desktop panel/taskbar

    Layout: [Apps] [Workspace] --- [CPU] [RAM] [Net] [Vol] [Weather] [Battery] [Clock]
    """

    def __init__(self, parent=None, weather_location: str = ""):
        super().__init__(parent)
        self.settings = QSettings("AILinux", "Client")
        self.setObjectName("DesktopPanel")
        self.setFixedHeight(32)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.setSpacing(2)

        # === Left side: App launcher, Workspace ===
        self.app_launcher = AppLauncherButton()
        layout.addWidget(self.app_launcher)

        self.workspace = WorkspaceWidget()
        layout.addWidget(self.workspace)

        # Spacer
        layout.addStretch()

        # === Right side: System widgets ===

        # CPU
        self.cpu = CpuWidget()
        layout.addWidget(self.cpu)

        # Memory
        self.memory = MemoryWidget()
        layout.addWidget(self.memory)

        # Network
        self.network = NetworkWidget()
        layout.addWidget(self.network)

        # Separator
        sep1 = QFrame()
        sep1.setFrameShape(QFrame.Shape.VLine)
        sep1.setStyleSheet("color: #444;")
        layout.addWidget(sep1)

        # Volume
        self.volume = VolumeWidget()
        layout.addWidget(self.volume)

        # Weather
        self.weather = WeatherWidget(location=weather_location)
        layout.addWidget(self.weather)

        # Battery (auto-hides if no battery)
        self.battery = BatteryWidget()
        layout.addWidget(self.battery)

        # Separator
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.VLine)
        sep2.setStyleSheet("color: #444;")
        layout.addWidget(sep2)

        # Clock (always last)
        self.clock = ClockWidget()
        layout.addWidget(self.clock)

        # Apply theme colors
        self._apply_theme_colors()

    def set_weather_location(self, location: str):
        """Update weather location"""
        self.weather.location = location
        self.weather.update_status()

    def apply_settings(self):
        """Apply settings from QSettings (called when settings change)"""
        self._apply_theme_colors()

    def _apply_theme_colors(self):
        """
        Apply theme colors from settings to desktop panel.
        Follows WCAG contrast guidelines for visibility.
        """
        # Read theme colors from settings
        primary = self.settings.value("theme_color_primary", "#3b82f6")
        secondary = self.settings.value("theme_color_secondary", "#6366f1")
        surface = self.settings.value("theme_color_surface", "#1a1a2e")
        text_color = self.settings.value("theme_color_text", "#e0e0e0")
        transparency = self.settings.value("widget_transparency", 85, type=int) / 100.0

        # Helper: Convert hex to rgba
        def hex_to_rgba(hex_color, alpha):
            hex_color = hex_color.lstrip("#")
            if len(hex_color) >= 6:
                r = int(hex_color[0:2], 16)
                g = int(hex_color[2:4], 16)
                b = int(hex_color[4:6], 16)
                return f"rgba({r}, {g}, {b}, {alpha:.2f})"
            return f"rgba(30, 30, 50, {alpha:.2f})"

        # Helper: Ensure minimum contrast (WCAG)
        def ensure_contrast(bg_hex, fg_hex):
            """Ensure text is readable - return adjusted text color if needed"""
            def luminance(hex_c):
                hex_c = hex_c.lstrip("#")
                if len(hex_c) < 6:
                    return 0.5
                r, g, b = int(hex_c[0:2], 16)/255, int(hex_c[2:4], 16)/255, int(hex_c[4:6], 16)/255
                r = r/12.92 if r <= 0.03928 else ((r+0.055)/1.055)**2.4
                g = g/12.92 if g <= 0.03928 else ((g+0.055)/1.055)**2.4
                b = b/12.92 if b <= 0.03928 else ((b+0.055)/1.055)**2.4
                return 0.2126*r + 0.7152*g + 0.0722*b

            bg_lum = luminance(bg_hex)
            fg_lum = luminance(fg_hex)
            lighter = max(bg_lum, fg_lum)
            darker = min(bg_lum, fg_lum)
            ratio = (lighter + 0.05) / (darker + 0.05)

            # WCAG AA requires 4.5:1 for normal text
            if ratio >= 4.5:
                return fg_hex
            return "#ffffff" if bg_lum < 0.5 else "#1a1a1a"

        # Ensure text contrast
        text_color = ensure_contrast(surface, text_color)

        surface_rgba = hex_to_rgba(surface, transparency)
        surface_darker = hex_to_rgba(surface, min(1.0, transparency + 0.15))

        # Panel gradient with theme colors
        self.setStyleSheet(f"""
            #DesktopPanel {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {surface_rgba}, stop:1 {surface_darker});
                border-bottom: 1px solid rgba(255, 255, 255, 0.1);
            }}
        """)


# =============================================================================
# Desktop Window (Full screen desktop mode)
# =============================================================================

class DesktopWindow(QWidget):
    """
    Full desktop mode window

    For running AILinux Client as a complete desktop environment
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("AILinux Desktop")
        self.setStyleSheet("background: #121212;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Top panel
        self.panel = DesktopPanel()
        layout.addWidget(self.panel)

        # Main content area (for embedding main window)
        self.content = QWidget()
        self.content.setStyleSheet("background: transparent;")
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.content, 1)

    def set_content(self, widget: QWidget):
        """Set the main content widget"""
        # Clear existing
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            if item.widget():
                item.widget().setParent(None)

        self.content_layout.addWidget(widget)

    def enter_fullscreen(self):
        """Enter fullscreen desktop mode"""
        self.showFullScreen()

    def exit_fullscreen(self):
        """Exit fullscreen mode"""
        self.showNormal()


# Test
if __name__ == "__main__":
    import sys
    app = QApplication(sys.argv)

    # Test panel standalone
    window = QWidget()
    window.setWindowTitle("Desktop Panel Test")
    window.setMinimumSize(1200, 600)
    window.setStyleSheet("background: #1e1e1e;")

    layout = QVBoxLayout(window)
    layout.setContentsMargins(0, 0, 0, 0)

    panel = DesktopPanel(weather_location="Berlin")
    layout.addWidget(panel)
    layout.addStretch()

    window.show()
    sys.exit(app.exec())
