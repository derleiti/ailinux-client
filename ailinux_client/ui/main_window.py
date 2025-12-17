"""
AILinux Client - Main Window
============================

Desktop-ready client with:
- Full desktop panel (taskbar)
- CLI agent integration
- MCP Node connection
- Terminal with tabs
"""
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QToolBar, QPushButton, QLabel, QStatusBar,
    QSplitter, QTabWidget, QMenuBar, QMenu,
    QMessageBox, QApplication, QSizePolicy,
    QFileDialog, QDialog, QTextBrowser
)
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal, QSettings
from PyQt6.QtGui import QAction, QKeySequence, QIcon, QShortcut, QScreen
import os
import sys
import json
import logging
import subprocess
from typing import Optional
from pathlib import Path

logger = logging.getLogger("ailinux.main_window")

# Import translations
from ..translations import tr, set_language, get_current_language, SUPPORTED_LANGUAGES

# Import UI components
from .chat_widget import ChatWidget
from .terminal_widget import TerminalWidget
from .file_browser import FileBrowser
from .desktop_panel import DesktopPanel

# Import core components
from ..core.api_client import APIClient
from ..core.local_mcp import LocalMCPExecutor
from ..core.cli_agents import agent_detector, local_mcp_server, CLIAgent
from ..core.tier_manager import get_tier_manager, Tier

# Optional MCP Node client
try:
    from ..core.mcp_node_client import MCPNodeClient
    HAS_MCP_NODE = True
except ImportError:
    HAS_MCP_NODE = False
    logger.warning("MCP Node client not available")

# Shortcut manager
try:
    from ..core.shortcut_manager import ShortcutManager, ShortcutContext, get_shortcut_manager
    HAS_SHORTCUT_MANAGER = True
except ImportError:
    HAS_SHORTCUT_MANAGER = False
    logger.warning("Shortcut manager not available")

# Highlight frame for active widget indication
try:
    from .highlight_frame import HighlightManager
    HAS_HIGHLIGHT_MANAGER = True
except ImportError:
    HAS_HIGHLIGHT_MANAGER = False


# =============================================================================
# MCP Node Thread (WebSocket connection to server)
# =============================================================================

class MCPNodeThread(QThread):
    """Background thread for MCP Node WebSocket connection"""

    connected = pyqtSignal()
    disconnected = pyqtSignal()
    tool_call = pyqtSignal(str, dict)  # tool_name, params
    error = pyqtSignal(str)

    def __init__(self, api_client: APIClient, parent=None):
        super().__init__(parent)
        self.api_client = api_client
        self.mcp_client: Optional[MCPNodeClient] = None
        self.running = False

    def run(self):
        if not HAS_MCP_NODE:
            return

        self.running = True
        import asyncio

        async def connect_loop():
            # Create MCP client with api_client for user auth
            self.mcp_client = MCPNodeClient(api_client=self.api_client)

            # Set callbacks
            def on_connected(state):
                self.connected.emit()

            def on_disconnected():
                self.disconnected.emit()

            def on_error(err):
                self.error.emit(str(err))

            def on_tool_call(name, args):
                self.tool_call.emit(name, args)

            self.mcp_client.on_connected = on_connected
            self.mcp_client.on_disconnected = on_disconnected
            self.mcp_client.on_error = on_error
            self.mcp_client.on_tool_call = on_tool_call

            # Connect with auto-reconnect
            while self.running:
                try:
                    success = await self.mcp_client.connect()
                    if success:
                        logger.info(f"MCP Node connected (session: {self.mcp_client.session_id})")

                        # Wait while connected
                        while self.running and self.mcp_client.is_connected():
                            await asyncio.sleep(0.1)
                    else:
                        self.error.emit("Connection failed")

                except Exception as e:
                    logger.error(f"MCP Node error: {e}")
                    self.error.emit(str(e))
                    self.disconnected.emit()

                if self.running:
                    await asyncio.sleep(5)  # Reconnect delay

        asyncio.run(connect_loop())

    def stop(self):
        self.running = False
        if self.mcp_client:
            import asyncio
            asyncio.run(self.mcp_client.disconnect())


# =============================================================================
# Main Window
# =============================================================================

class MainWindow(QMainWindow):
    """
    AILinux Client Main Window

    Features:
    - Desktop panel (taskbar) at top
    - Chat, Terminal, File Browser tabs
    - CLI agent integration
    - MCP Node connection
    """

    def __init__(self, api_client: APIClient = None, desktop_mode: bool = False):
        super().__init__()

        # Load application icon from main folder
        self._setup_app_icon()

        self.api_client = api_client or APIClient()
        self.desktop_mode = desktop_mode
        self.mcp_node_thread: Optional[MCPNodeThread] = None
        self.local_mcp = LocalMCPExecutor()
        self.local_mcp_process: Optional[subprocess.Popen] = None

        # Settings
        self.settings = QSettings("AILinux", "Client")

        # Detected CLI agents
        self.cli_agents = []

        self._setup_ui()
        self._setup_statusbar()  # Must be before toolbar (toolbar references tier_label)
        self._setup_menu()
        self._setup_toolbar()
        self._setup_shortcuts()

        # Start local MCP server
        self._start_local_mcp_server()

        # Detect CLI agents
        self._detect_cli_agents()

        # Connect MCP Node if authenticated (registered users get limited MCP)
        # Use a timer to allow async operations to complete and retry if needed
        if HAS_MCP_NODE:
            if self.api_client.user_id or self.api_client.token:
                self._connect_mcp_node()
            else:
                # Retry connection after a delay (user might be authenticating)
                QTimer.singleShot(2000, self._retry_mcp_connection)

        # Window settings
        self._load_window_settings()

        # Apply saved theme colors
        self._apply_theme_colors()

        # Setup focus tracking for context-aware shortcuts
        if HAS_SHORTCUT_MANAGER:
            self._setup_focus_tracking()

    def _setup_app_icon(self):
        """Load and set application icon from main folder"""
        # Try multiple icon file formats in order of preference
        icon_names = ["icon.png", "icon.jpg", "icon.ico", "icon.svg"]
        base_path = Path(__file__).parent.parent.parent  # Go up to ailinux-client root

        for icon_name in icon_names:
            icon_path = base_path / icon_name
            if icon_path.exists():
                icon = QIcon(str(icon_path))
                if not icon.isNull():
                    self.setWindowIcon(icon)
                    # Also set for application-wide
                    app = QApplication.instance()
                    if app:
                        app.setWindowIcon(icon)
                    logger.info(f"Loaded application icon: {icon_path}")
                    return

        logger.debug("No application icon found in main folder")

    def _detect_aspect_ratio(self) -> str:
        """
        Detect screen aspect ratio.
        Returns: '21:9' for ultrawide, '16:9' for standard, '4:3' for legacy
        """
        try:
            screen = QApplication.primaryScreen()
            if screen:
                geometry = screen.geometry()
                ratio = geometry.width() / geometry.height()

                # Ultrawide: 21:9 = 2.33, 32:9 = 3.55
                if ratio >= 2.1:
                    return '21:9'
                # Standard widescreen: 16:9 = 1.77, 16:10 = 1.6
                elif ratio >= 1.5:
                    return '16:9'
                # Legacy: 4:3 = 1.33
                else:
                    return '4:3'
        except Exception as e:
            logger.warning(f"Could not detect aspect ratio: {e}")
        return '16:9'  # Default

    def _get_layout_sizes(self) -> dict:
        """
        Get optimal layout sizes based on screen aspect ratio.

        21:9 Ultrawide: More horizontal space, Files wider, Chat wider
        16:9 Standard: Balanced layout
        4:3 Legacy: Minimize side panels
        """
        aspect = self._detect_aspect_ratio()

        if aspect == '21:9':
            # Ultrawide: Can afford wider side panels
            # Files: 200px, Center: 1000px+, Chat: 350px
            return {
                'main_splitter': [200, 900, 350],  # Files, Center, Chat
                'center_splitter': [0.55, 0.45],    # Browser, Terminal (more terminal)
                'aspect': '21:9'
            }
        elif aspect == '16:9':
            # Standard widescreen: Balanced
            # Files: 180px, Center: 720px, Chat: 300px
            return {
                'main_splitter': [180, 720, 300],
                'center_splitter': [0.60, 0.40],   # Browser, Terminal
                'aspect': '16:9'
            }
        else:
            # 4:3 or narrow: Minimize side panels
            return {
                'main_splitter': [150, 600, 250],
                'center_splitter': [0.65, 0.35],
                'aspect': '4:3'
            }

    def _setup_ui(self):
        """Setup main UI:
        Left: Files (full height, compact)
        Center: Browser (top, large) + Terminal (bottom, small/resizable)
        Right: Chat (full height, same size as Files)
        """
        self.setWindowTitle("AILinux Client")
        self.setMinimumSize(1200, 800)

        # Load background image from settings or use default wallpaper
        bg_image = self.settings.value("desktop_background", "")

        # Default wallpaper paths to check
        default_wallpapers = [
            "/usr/share/backgrounds/ailinux-wallpaper.jpg",
            "/usr/share/backgrounds/default.jpg",
            os.path.expanduser("~/.config/ailinux/wallpaper.jpg"),
        ]

        # Find a valid wallpaper
        if not bg_image or not os.path.exists(bg_image):
            for wp in default_wallpapers:
                if os.path.exists(wp):
                    bg_image = wp
                    break

        if bg_image and os.path.exists(bg_image):
            # Wallpaper with image
            bg_style = f"background-image: url({bg_image}); background-position: center; background-repeat: no-repeat;"
        else:
            # Beautiful gradient fallback (deep space theme)
            bg_style = """background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 #0a0a1a,
                stop:0.3 #1a1a3e,
                stop:0.6 #0f2027,
                stop:1 #203a43);"""

        self.setStyleSheet(f"""
            QMainWindow {{
                {bg_style}
            }}
            QSplitter::handle {{
                background: rgba(255, 255, 255, 0.08);
                width: 3px;
                height: 3px;
                border-radius: 1px;
            }}
            QSplitter::handle:hover {{
                background: rgba(59, 130, 246, 0.7);
            }}
        """)

        # Central widget with contrast overlay
        central = QWidget()
        self.setCentralWidget(central)
        central.setObjectName("centralWidget")

        # Apply overlay effect - semi-transparent dark layer for contrast
        # This creates the "frosted glass" effect over the wallpaper
        # Read overlay opacity from settings (0-100 -> 0.0-1.0)
        overlay_opacity = self.settings.value("overlay_opacity", 65, type=int) / 100.0
        self._apply_overlay_opacity(central, overlay_opacity)

        layout = QVBoxLayout(central)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # Desktop Panel (taskbar) - only in desktop mode
        if self.desktop_mode:
            weather_location = self.settings.value("weather_location", "")
            self.desktop_panel = DesktopPanel(weather_location=weather_location)
            layout.addWidget(self.desktop_panel)

        # Main horizontal splitter: Files | Center | Chat
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(self.main_splitter, 1)

        # LEFT: File browser (full height, compact)
        self.file_browser = FileBrowser()
        self.file_browser.file_selected.connect(self._on_file_selected)
        self.file_browser.setMinimumWidth(150)
        self.main_splitter.addWidget(self.file_browser)

        # CENTER: Browser (top, large) + Terminal (bottom, small)
        self.center_splitter = QSplitter(Qt.Orientation.Vertical)
        self.center_splitter.setChildrenCollapsible(False)  # Prevent collapsing
        self.main_splitter.addWidget(self.center_splitter)

        # Center-Top: Browser (large)
        try:
            from .browser_widget import BrowserWidget
            self.browser_widget = BrowserWidget()
        except Exception as e:
            # Fallback if browser widget not available
            logger.error(f"Failed to load browser widget: {e}")
            self.browser_widget = QWidget()
            browser_layout = QVBoxLayout(self.browser_widget)
            browser_label = QLabel(f"🌐 Browser - Error: {str(e)[:100]}")
            browser_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            browser_label.setStyleSheet("color: #888; font-size: 16px;")
            browser_layout.addWidget(browser_label)
        self.browser_widget.setMinimumHeight(100)
        self.center_splitter.addWidget(self.browser_widget)

        # Center-Bottom: Terminal (small, user can resize)
        self.terminal_widget = TerminalWidget()
        self.terminal_widget.setMinimumHeight(100)
        self.center_splitter.addWidget(self.terminal_widget)

        # RIGHT: Chat widget (full height, same size as Files)
        self.chat_widget = ChatWidget(self.api_client)
        self.chat_widget.setMinimumWidth(200)
        self.main_splitter.addWidget(self.chat_widget)

        # Allow all splitter sections to be resized freely
        self.main_splitter.setChildrenCollapsible(False)

        # Get layout sizes based on screen aspect ratio (21:9 vs 16:9)
        layout = self._get_layout_sizes()
        logger.info(f"Detected screen aspect ratio: {layout['aspect']}")

        # Apply layout proportions
        self.main_splitter.setSizes(layout['main_splitter'])

        # Center splitter (Browser/Terminal) - calculate from total height
        total_h = self.height() or 800
        browser_h = int(total_h * layout['center_splitter'][0])
        terminal_h = int(total_h * layout['center_splitter'][1])
        self.center_splitter.setSizes([browser_h, terminal_h])

        # Visibility state for toggle
        self._widget_visible = {
            'browser': True,
            'files': True,
            'chat': True,
            'terminal': True
        }

        # Keep tabs reference for compatibility (hidden, for additional tabs)
        self.tabs = QTabWidget()
        self.tabs.setVisible(False)

    def _setup_menu(self):
        """Setup menu bar"""
        menubar = self.menuBar()
        menubar.setStyleSheet("""
            QMenuBar {
                background: rgba(20, 20, 30, 0.9);
                color: #c0c0c0;
                border-bottom: 1px solid rgba(255, 255, 255, 0.08);
                padding: 2px;
            }
            QMenuBar::item {
                padding: 6px 12px;
                border-radius: 4px;
                margin: 2px;
            }
            QMenuBar::item:selected {
                background: rgba(59, 130, 246, 0.6);
                color: white;
            }
            QMenu {
                background: rgba(25, 25, 35, 0.95);
                color: #e0e0e0;
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 8px;
                padding: 4px;
            }
            QMenu::item {
                padding: 8px 24px;
                border-radius: 4px;
                margin: 2px 4px;
            }
            QMenu::item:selected {
                background: rgba(59, 130, 246, 0.6);
            }
            QMenu::separator {
                height: 1px;
                background: rgba(255, 255, 255, 0.1);
                margin: 4px 10px;
            }
        """)

        # File menu
        file_menu = menubar.addMenu(tr("File"))

        action_new_chat = QAction(tr("New Chat"), self)
        action_new_chat.setShortcut(QKeySequence.StandardKey.New)
        action_new_chat.triggered.connect(self._new_chat)
        file_menu.addAction(action_new_chat)

        action_new_terminal = QAction(tr("New Terminal"), self)
        # Shortcut handled by ShortcutManager to avoid conflicts
        action_new_terminal.triggered.connect(self._new_terminal)
        file_menu.addAction(action_new_terminal)

        file_menu.addSeparator()

        action_open_file = QAction(tr("Open File..."), self)
        action_open_file.setShortcut(QKeySequence.StandardKey.Open)
        action_open_file.triggered.connect(self._open_file)
        file_menu.addAction(action_open_file)

        action_open_folder = QAction(tr("Open Folder..."), self)
        action_open_folder.setShortcut(QKeySequence("Ctrl+Shift+O"))
        action_open_folder.triggered.connect(self._open_folder)
        file_menu.addAction(action_open_folder)

        file_menu.addSeparator()

        action_settings = QAction(tr("Settings"), self)
        # Shortcut handled by ShortcutManager to avoid conflicts
        action_settings.triggered.connect(self._open_settings)
        file_menu.addAction(action_settings)

        file_menu.addSeparator()

        action_logout = QAction(tr("Logout"), self)
        action_logout.triggered.connect(self._logout)
        file_menu.addAction(action_logout)

        file_menu.addSeparator()

        action_exit = QAction(tr("Exit"), self)
        action_exit.setShortcut(QKeySequence.StandardKey.Quit)
        action_exit.triggered.connect(self.close)
        file_menu.addAction(action_exit)

        # View menu - Toggle each widget
        view_menu = menubar.addMenu(tr("View"))

        # Widget toggles with checkboxes
        self.action_toggle_browser = QAction(tr("Browser"), self)
        # Shortcut handled by ShortcutManager to avoid conflicts
        self.action_toggle_browser.setCheckable(True)
        self.action_toggle_browser.setChecked(True)
        self.action_toggle_browser.triggered.connect(self._toggle_browser)
        view_menu.addAction(self.action_toggle_browser)

        self.action_toggle_filebrowser = QAction(tr("File Browser"), self)
        # Shortcut handled by ShortcutManager to avoid conflicts
        self.action_toggle_filebrowser.setCheckable(True)
        self.action_toggle_filebrowser.setChecked(True)
        self.action_toggle_filebrowser.triggered.connect(self._toggle_file_browser)
        view_menu.addAction(self.action_toggle_filebrowser)

        self.action_toggle_chat = QAction(tr("Chat"), self)
        # Shortcut handled by ShortcutManager to avoid conflicts
        self.action_toggle_chat.setCheckable(True)
        self.action_toggle_chat.setChecked(True)
        self.action_toggle_chat.triggered.connect(self._toggle_chat)
        view_menu.addAction(self.action_toggle_chat)

        self.action_toggle_terminal = QAction(tr("Terminal"), self)
        # Shortcut handled by ShortcutManager to avoid conflicts
        self.action_toggle_terminal.setCheckable(True)
        self.action_toggle_terminal.setChecked(True)
        self.action_toggle_terminal.triggered.connect(self._toggle_terminal)
        view_menu.addAction(self.action_toggle_terminal)

        view_menu.addSeparator()

        action_auto_sort = QAction(tr("Auto Sort Layout"), self)
        # Shortcut handled by ShortcutManager to avoid conflicts
        action_auto_sort.triggered.connect(self._auto_sort_layout)
        view_menu.addAction(action_auto_sort)

        view_menu.addSeparator()

        if self.desktop_mode:
            self.action_toggle_panel = QAction(tr("Desktop Panel"), self)
            self.action_toggle_panel.setShortcut(QKeySequence("Ctrl+Shift+P"))
            self.action_toggle_panel.setCheckable(True)
            self.action_toggle_panel.setChecked(True)
            self.action_toggle_panel.triggered.connect(self._toggle_panel)
            view_menu.addAction(self.action_toggle_panel)

        view_menu.addSeparator()

        action_focus = QAction(tr("Focus Mode (Hide All)"), self)
        # Shortcut handled by ShortcutManager to avoid conflicts
        action_focus.triggered.connect(self._focus_mode)
        view_menu.addAction(action_focus)

        action_show_all = QAction(tr("Show All"), self)
        # Shortcut handled by ShortcutManager to avoid conflicts
        action_show_all.triggered.connect(self._show_all_widgets)
        view_menu.addAction(action_show_all)

        view_menu.addSeparator()

        action_fullscreen = QAction(tr("Toggle Fullscreen"), self)
        action_fullscreen.setShortcut(QKeySequence("F11"))
        action_fullscreen.triggered.connect(self._toggle_fullscreen)
        view_menu.addAction(action_fullscreen)

        # Tools menu
        tools_menu = menubar.addMenu(tr("Tools"))

        action_mcp_status = QAction(tr("MCP Status"), self)
        action_mcp_status.triggered.connect(self._show_mcp_status)
        tools_menu.addAction(action_mcp_status)

        action_reconnect = QAction(tr("Reconnect MCP Node"), self)
        action_reconnect.triggered.connect(self._reconnect_mcp_node)
        tools_menu.addAction(action_reconnect)

        tools_menu.addSeparator()

        action_hwinfo = QAction(tr("Hardware Info"), self)
        action_hwinfo.triggered.connect(self._show_hardware_info)
        tools_menu.addAction(action_hwinfo)

        tools_menu.addSeparator()

        # CLI Agents submenu
        self.cli_agents_menu = tools_menu.addMenu(tr("CLI Agents"))
        # Will be populated in _detect_cli_agents()

        # Help menu
        help_menu = menubar.addMenu(tr("Help"))

        action_readme = QAction(tr("README"), self)
        action_readme.triggered.connect(self._show_readme)
        help_menu.addAction(action_readme)

        action_license = QAction(tr("License Agreement"), self)
        action_license.triggered.connect(self._show_license)
        help_menu.addAction(action_license)

        help_menu.addSeparator()

        action_about = QAction(tr("About"), self)
        action_about.triggered.connect(self._show_about)
        help_menu.addAction(action_about)

        action_shortcuts = QAction(tr("Keyboard Shortcuts"), self)
        action_shortcuts.triggered.connect(self._show_shortcuts)
        help_menu.addAction(action_shortcuts)

        help_menu.addSeparator()

        action_check_updates = QAction(tr("Check for Updates"), self)
        action_check_updates.triggered.connect(self._check_updates)
        help_menu.addAction(action_check_updates)

        action_report_bug = QAction(tr("Report Bug"), self)
        action_report_bug.triggered.connect(self._report_bug)
        help_menu.addAction(action_report_bug)

    def _setup_toolbar(self):
        """Setup toolbar with toggle buttons and CLI agents"""
        toolbar = QToolBar("Main Toolbar")
        toolbar.setObjectName("MainToolBar")
        toolbar.setMovable(False)
        toolbar.setStyleSheet("""
            QToolBar {
                background: rgba(20, 20, 30, 0.85);
                border: none;
                border-bottom: 1px solid rgba(255, 255, 255, 0.05);
                spacing: 6px;
                padding: 6px 8px;
            }
            QPushButton {
                background: rgba(255, 255, 255, 0.08);
                color: #c0c0c0;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 6px;
                padding: 8px 16px;
                font-size: 13px;
                min-width: 80px;
            }
            QPushButton:hover {
                background: rgba(59, 130, 246, 0.5);
                color: white;
                border-color: rgba(59, 130, 246, 0.6);
            }
            QPushButton:pressed {
                background: rgba(37, 99, 235, 0.7);
            }
            QPushButton:checked {
                background: rgba(59, 130, 246, 0.6);
                border: 1px solid rgba(96, 165, 250, 0.7);
                color: white;
            }
            QPushButton.agent-btn {
                background: rgba(30, 58, 95, 0.7);
                min-width: 70px;
            }
            QPushButton.agent-btn:hover {
                background: rgba(37, 99, 235, 0.7);
            }
        """)
        self.addToolBar(toolbar)

        # ============== View Toggle Buttons ==============
        # Browser toggle
        self.btn_browser = QPushButton(tr("Browser"))
        self.btn_browser.setCheckable(True)
        self.btn_browser.setChecked(True)
        self.btn_browser.setToolTip(tr("Toggle Browser (Ctrl+Shift+B)"))
        self.btn_browser.clicked.connect(self._toggle_browser)
        toolbar.addWidget(self.btn_browser)

        # File Browser toggle
        self.btn_files = QPushButton(tr("File Browser"))
        self.btn_files.setCheckable(True)
        self.btn_files.setChecked(True)
        self.btn_files.setToolTip(tr("Toggle File Browser (Ctrl+B)"))
        self.btn_files.clicked.connect(self._toggle_file_browser)
        toolbar.addWidget(self.btn_files)

        # Chat toggle
        self.btn_chat = QPushButton(tr("Chat"))
        self.btn_chat.setCheckable(True)
        self.btn_chat.setChecked(True)
        self.btn_chat.setToolTip(tr("Toggle Chat (Ctrl+Shift+C)"))
        self.btn_chat.clicked.connect(self._toggle_chat)
        toolbar.addWidget(self.btn_chat)

        # Terminal toggle
        self.btn_terminal = QPushButton(tr("Terminal"))
        self.btn_terminal.setCheckable(True)
        self.btn_terminal.setChecked(True)
        self.btn_terminal.setToolTip(tr("Toggle Terminal (Ctrl+Shift+T)"))
        self.btn_terminal.clicked.connect(self._toggle_terminal)
        toolbar.addWidget(self.btn_terminal)

        toolbar.addSeparator()

        # ============== CLI Agent Buttons ==============
        agent_label = QLabel("  " + tr("Agents:"))
        agent_label.setStyleSheet("color: #888; font-weight: bold;")
        toolbar.addWidget(agent_label)

        self.agent_buttons = {}

        # Claude Code button
        self.btn_claude = QPushButton("🤖 Claude")
        self.btn_claude.setProperty("class", "agent-btn")
        self.btn_claude.setToolTip("Launch Claude Code mit MCP (Alt+C)")
        self.btn_claude.clicked.connect(lambda: self._launch_cli_agent("claude"))
        self.btn_claude.setVisible(False)
        toolbar.addWidget(self.btn_claude)
        self.agent_buttons["claude"] = self.btn_claude

        # Gemini CLI button
        self.btn_gemini = QPushButton("💎 Gemini")
        self.btn_gemini.setProperty("class", "agent-btn")
        self.btn_gemini.setToolTip("Launch Gemini CLI mit MCP (Alt+G)")
        self.btn_gemini.clicked.connect(lambda: self._launch_cli_agent("gemini"))
        self.btn_gemini.setVisible(False)
        toolbar.addWidget(self.btn_gemini)
        self.agent_buttons["gemini"] = self.btn_gemini

        # Codex button
        self.btn_codex = QPushButton("📦 Codex")
        self.btn_codex.setProperty("class", "agent-btn")
        self.btn_codex.setToolTip("Launch Codex mit MCP (Alt+X)")
        self.btn_codex.clicked.connect(lambda: self._launch_cli_agent("codex"))
        self.btn_codex.setVisible(False)
        toolbar.addWidget(self.btn_codex)
        self.agent_buttons["codex"] = self.btn_codex

        # OpenCode button
        self.btn_opencode = QPushButton("🔓 OpenCode")
        self.btn_opencode.setProperty("class", "agent-btn")
        self.btn_opencode.setToolTip("Launch OpenCode mit MCP (Alt+O)")
        self.btn_opencode.clicked.connect(lambda: self._launch_cli_agent("opencode"))
        self.btn_opencode.setVisible(False)
        toolbar.addWidget(self.btn_opencode)
        self.agent_buttons["opencode"] = self.btn_opencode

        toolbar.addSeparator()

        # MCP Node status
        self.mcp_status_label = QLabel("MCP: --")
        self.mcp_status_label.setStyleSheet("color: #888; padding: 0 8px;")
        toolbar.addWidget(self.mcp_status_label)

        # Spacer
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(spacer)

        # User info (if authenticated)
        self.user_label = QLabel()
        self.user_label.setStyleSheet("color: #4ade80; padding: 0 8px;")
        toolbar.addWidget(self.user_label)
        self._update_user_label()

    def _setup_shortcuts(self):
        """Setup keyboard shortcuts using centralized ShortcutManager"""
        if HAS_SHORTCUT_MANAGER:
            # Initialize shortcut manager with this window as parent
            self.shortcut_manager = get_shortcut_manager(self)

            # F1-F4: Widget toggles (Global)
            self.shortcut_manager.register("F1", self._toggle_browser, ShortcutContext.GLOBAL,
                                          "Toggle Browser", "View")
            self.shortcut_manager.register("F2", self._toggle_file_browser, ShortcutContext.GLOBAL,
                                          "Toggle File Browser", "View")
            self.shortcut_manager.register("F3", self._toggle_chat, ShortcutContext.GLOBAL,
                                          "Toggle Chat", "View")
            self.shortcut_manager.register("F4", self._toggle_terminal, ShortcutContext.GLOBAL,
                                          "Toggle Terminal", "View")

            # F5: Lock screen
            self.shortcut_manager.register("F5", self._toggle_lock_screen, ShortcutContext.GLOBAL,
                                          "Lock Screen", "System")

            # F11: Fullscreen
            self.shortcut_manager.register("F11", self._toggle_fullscreen, ShortcutContext.GLOBAL,
                                          "Toggle Fullscreen", "View")

            # Alt+Tab: Cycle through widgets
            self.shortcut_manager.register("Alt+Tab", self._cycle_widget_focus, ShortcutContext.GLOBAL,
                                          "Next Widget", "Navigation")
            self.shortcut_manager.register("Alt+Shift+Tab", self._cycle_widget_focus_reverse, ShortcutContext.GLOBAL,
                                          "Previous Widget", "Navigation")

            # Note: All Ctrl+* shortcuts are now widget-specific
            # Only F1-F5, F11, Alt+Tab are global shortcuts

            logger.info(f"Registered {len(self.shortcut_manager.get_all_shortcuts())} global shortcuts")

        else:
            # Fallback to old QShortcut method
            self._setup_shortcuts_fallback()

    def _setup_focus_tracking(self):
        """Setup focus change tracking for context-aware shortcuts and visual highlighting"""
        # Install event filter on application to track focus changes
        app = QApplication.instance()
        if app:
            app.focusChanged.connect(self._on_focus_changed)

        # Register widget contexts
        if hasattr(self, 'shortcut_manager'):
            self.shortcut_manager.register_widget_context(
                self.terminal_widget, ShortcutContext.TERMINAL
            )
            self.shortcut_manager.register_widget_context(
                self.chat_widget, ShortcutContext.CHAT
            )
            self.shortcut_manager.register_widget_context(
                self.file_browser, ShortcutContext.FILE_BROWSER
            )
            if hasattr(self, 'browser_widget'):
                self.shortcut_manager.register_widget_context(
                    self.browser_widget, ShortcutContext.BROWSER
                )

        # Track main widgets for highlighting
        self._main_widgets = [
            self.terminal_widget,
            self.chat_widget,
            self.file_browser,
        ]
        if hasattr(self, 'browser_widget'):
            self._main_widgets.append(self.browser_widget)

        # Store original stylesheets for restoration
        self._widget_original_styles = {}

        # Active highlight color from theme
        self._active_highlight_color = self.settings.value("theme_color_primary", "#3b82f6")

    def _on_focus_changed(self, old_widget: QWidget, new_widget: QWidget):
        """Handle focus change to update shortcut context and visual highlighting"""
        if new_widget is None:
            return

        # Update shortcut context
        if HAS_SHORTCUT_MANAGER and hasattr(self, 'shortcut_manager'):
            widget = new_widget
            while widget is not None:
                context = self.shortcut_manager.get_widget_context(widget)
                if context:
                    self.shortcut_manager.set_context(context)
                    logger.debug(f"Shortcut context changed to: {context.name}")
                    break
                widget = widget.parent() if hasattr(widget, 'parent') else None
            else:
                self.shortcut_manager.set_context(ShortcutContext.GLOBAL)

        # Update visual highlighting
        self._update_widget_highlight(new_widget)

    def _update_widget_highlight(self, focused_widget: QWidget):
        """Update visual highlight for the active widget"""
        if not hasattr(self, '_main_widgets'):
            return

        # Find which main widget contains the focused widget
        active_main_widget = None
        widget = focused_widget
        while widget is not None:
            if widget in self._main_widgets:
                active_main_widget = widget
                break
            widget = widget.parent() if hasattr(widget, 'parent') else None

        # Skip if same widget is already highlighted
        if hasattr(self, '_current_highlighted') and self._current_highlighted == active_main_widget:
            return

        # Remove highlight from previously active widget
        if hasattr(self, '_current_highlighted') and self._current_highlighted:
            self._remove_highlight(self._current_highlighted)

        # Add highlight to new active widget
        if active_main_widget:
            self._apply_active_highlight(active_main_widget, self._active_highlight_color)
            self._current_highlighted = active_main_widget
        else:
            self._current_highlighted = None

    def _apply_active_highlight(self, widget: QWidget, color: str):
        """Apply active highlight style to widget using a subtle glow border"""
        # Use QGraphicsDropShadowEffect for a nice glow
        from PyQt6.QtWidgets import QGraphicsDropShadowEffect
        from PyQt6.QtGui import QColor

        # Store original effect if any
        if id(widget) not in self._widget_original_styles:
            self._widget_original_styles[id(widget)] = widget.graphicsEffect()

        # Create glow effect
        glow = QGraphicsDropShadowEffect(widget)
        glow.setBlurRadius(15)
        glow.setOffset(0, 0)
        glow.setColor(QColor(color))

        widget.setGraphicsEffect(glow)

        # Also update statusbar to show active widget
        widget_names = {
            self.terminal_widget: "Terminal",
            self.chat_widget: "Chat",
            self.file_browser: "File Browser",
        }
        if hasattr(self, 'browser_widget'):
            widget_names[self.browser_widget] = "Browser"

        widget_name = widget_names.get(widget, "Unknown")
        self.statusbar.showMessage(f"Active: {widget_name}", 2000)

    def _remove_highlight(self, widget: QWidget):
        """Remove highlight glow from widget"""
        # Restore original effect (usually None)
        if id(widget) in self._widget_original_styles:
            widget.setGraphicsEffect(self._widget_original_styles[id(widget)])
        else:
            widget.setGraphicsEffect(None)

    def _setup_shortcuts_fallback(self):
        """Fallback shortcut setup using QShortcut directly"""
        # F1-F4: Widget toggles
        QShortcut(QKeySequence("F1"), self, self._toggle_browser)
        QShortcut(QKeySequence("F2"), self, self._toggle_file_browser)
        QShortcut(QKeySequence("F3"), self, self._toggle_chat)
        QShortcut(QKeySequence("F4"), self, self._toggle_terminal)

        # F5: Lock screen
        QShortcut(QKeySequence("F5"), self, self._toggle_lock_screen)

        # CLI agent shortcuts
        QShortcut(QKeySequence("Alt+C"), self, lambda: self._launch_cli_agent("claude"))
        QShortcut(QKeySequence("Alt+G"), self, lambda: self._launch_cli_agent("gemini"))
        QShortcut(QKeySequence("Alt+X"), self, lambda: self._launch_cli_agent("codex"))
        QShortcut(QKeySequence("Alt+O"), self, lambda: self._launch_cli_agent("opencode"))

        # Tab navigation
        QShortcut(QKeySequence("Ctrl+Tab"), self, self._next_tab)
        QShortcut(QKeySequence("Ctrl+Shift+Tab"), self, self._prev_tab)
        QShortcut(QKeySequence("Ctrl+W"), self, self._close_current_tab)

        # Focus shortcuts
        QShortcut(QKeySequence("Ctrl+L"), self, self._focus_chat)
        QShortcut(QKeySequence("Ctrl+`"), self, self._focus_terminal)

    def _setup_statusbar(self):
        """Setup status bar with connection info, ping, and response time"""
        self.statusbar = QStatusBar()
        self.setStatusBar(self.statusbar)
        self.statusbar.setStyleSheet("""
            QStatusBar {
                background: rgba(15, 15, 25, 0.95);
                color: #888;
                border-top: 1px solid rgba(255, 255, 255, 0.08);
                padding: 4px 12px;
                font-size: 12px;
            }
            QStatusBar::item {
                border: none;
            }
        """)

        # Connection status indicator
        self.conn_indicator = QLabel("⚫")
        self.conn_indicator.setStyleSheet("color: #666; font-size: 10px;")
        self.statusbar.addWidget(self.conn_indicator)
        
        # Server connection label
        self.conn_label = QLabel("Server: Verbinde...")
        self.conn_label.setStyleSheet("color: #888; margin-right: 16px;")
        self.statusbar.addWidget(self.conn_label)

        # Separator
        sep1 = QLabel("|")
        sep1.setStyleSheet("color: #444; margin: 0 8px;")
        self.statusbar.addWidget(sep1)

        # Ping label
        self.ping_label = QLabel("Ping: --")
        self.ping_label.setStyleSheet("color: #888; margin-right: 16px;")
        self.statusbar.addWidget(self.ping_label)

        # Separator
        sep2 = QLabel("|")
        sep2.setStyleSheet("color: #444; margin: 0 8px;")
        self.statusbar.addWidget(sep2)

        # Response time label
        self.response_label = QLabel("Response: --")
        self.response_label.setStyleSheet("color: #888; margin-right: 16px;")
        self.statusbar.addWidget(self.response_label)

        # Separator
        sep3 = QLabel("|")
        sep3.setStyleSheet("color: #444; margin: 0 8px;")
        self.statusbar.addWidget(sep3)

        # Model label
        self.model_label = QLabel("Modell: --")
        self.model_label.setStyleSheet("color: #888;")
        self.statusbar.addWidget(self.model_label)

        # Spacer
        self.statusbar.addWidget(QLabel(""), 1)

        # Tier info (right side)
        self.tier_label = QLabel()
        self.tier_label.setStyleSheet("color: #4ade80; font-weight: bold;")
        self.statusbar.addPermanentWidget(self.tier_label)

        # Start ping timer
        self._ping_timer = QTimer(self)
        self._ping_timer.timeout.connect(self._update_ping)
        self._ping_timer.start(5000)  # Every 5 seconds
        
        # Initial ping
        QTimer.singleShot(500, self._update_ping)

    def _update_ping(self):
        """Update ping to server"""
        import time
        try:
            start = time.time()
            # Simple health check
            if self.api_client:
                result = self.api_client._request("GET", "/health")
                ping_ms = int((time.time() - start) * 1000)
                
                # Update connection status
                self.conn_indicator.setText("🟢")
                self.conn_indicator.setStyleSheet("color: #4ade80; font-size: 10px;")
                self.conn_label.setText("Server: Online")
                self.conn_label.setStyleSheet("color: #4ade80;")
                
                # Update ping with color coding
                if ping_ms < 100:
                    ping_color = "#4ade80"  # Green
                elif ping_ms < 300:
                    ping_color = "#facc15"  # Yellow
                else:
                    ping_color = "#f87171"  # Red
                
                self.ping_label.setText(f"Ping: {ping_ms}ms")
                self.ping_label.setStyleSheet(f"color: {ping_color};")
            else:
                self._set_offline_status()
        except Exception as e:
            self._set_offline_status()

    def _set_offline_status(self):
        """Set offline status in statusbar"""
        self.conn_indicator.setText("🔴")
        self.conn_indicator.setStyleSheet("color: #f87171; font-size: 10px;")
        self.conn_label.setText("Server: Offline")
        self.conn_label.setStyleSheet("color: #f87171;")
        self.ping_label.setText("Ping: --")
        self.ping_label.setStyleSheet("color: #666;")

    def update_response_time(self, response_ms: int, model: str = None):
        """Update response time in statusbar (called from chat widget)"""
        if response_ms < 1000:
            time_str = f"{response_ms}ms"
        else:
            time_str = f"{response_ms/1000:.1f}s"
        
        # Color code response time
        if response_ms < 2000:
            color = "#4ade80"  # Green
        elif response_ms < 5000:
            color = "#facc15"  # Yellow
        else:
            color = "#f87171"  # Red
        
        self.response_label.setText(f"Response: {time_str}")
        self.response_label.setStyleSheet(f"color: {color};")
        
        if model:
            # Shorten model name if too long
            if len(model) > 25:
                model = model[:22] + "..."
            self.model_label.setText(f"Modell: {model}")
            self.model_label.setStyleSheet("color: #60a5fa;")

    # =========================================================================
    # CLI Agent Integration
    # =========================================================================

    def _detect_cli_agents(self):
        """Detect installed CLI agents"""
        self.cli_agents = agent_detector.detect_all()
        tier_mgr = get_tier_manager(self.api_client)
        can_use_agents = tier_mgr.can_use_cli_agents()

        # Update buttons visibility
        for agent in self.cli_agents:
            if agent.name in self.agent_buttons:
                btn = self.agent_buttons[agent.name]
                btn.setVisible(True)
                btn.setEnabled(can_use_agents)
                if can_use_agents:
                    btn.setToolTip(f"Launch {agent.display_name} ({agent.path})")
                else:
                    btn.setToolTip(f"{agent.display_name} - Upgrade to Tier 0.5+ for CLI Agents")

        # Update menu
        self.cli_agents_menu.clear()

        # Show tier requirement if not available
        if not can_use_agents:
            tier_info = self.cli_agents_menu.addAction("🔒 CLI Agents require Tier 0.5+")
            tier_info.setEnabled(False)
            upgrade_action = self.cli_agents_menu.addAction("📈 Register for free at ailinux.me")
            upgrade_action.triggered.connect(lambda: __import__('webbrowser').open('https://ailinux.me/register'))
            self.cli_agents_menu.addSeparator()

        if self.cli_agents:
            for agent in self.cli_agents:
                action = self.cli_agents_menu.addAction(
                    agent.display_name,
                    lambda a=agent: self._launch_cli_agent(a.name)
                )
                action.setToolTip(f"Path: {agent.path}")
                action.setEnabled(can_use_agents)
        else:
            self.cli_agents_menu.addAction(tr("No agents detected")).setEnabled(False)

        self.cli_agents_menu.addSeparator()
        self.cli_agents_menu.addAction(tr("Rescan"), self._detect_cli_agents)

        logger.info(f"Detected {len(self.cli_agents)} CLI agents (access: {can_use_agents})")

    def _start_local_mcp_server(self):
        """Start the local MCP stdio server as a subprocess"""
        try:
            mcp_server_path = Path(__file__).parent.parent / "core" / "mcp_stdio_server.py"

            if not mcp_server_path.exists():
                logger.warning(f"MCP server not found: {mcp_server_path}")
                return

            # Get user tier and token
            tier = self.api_client.tier or "free"
            token = self.api_client.token or ""
            server_url = self.api_client.base_url or "https://api.ailinux.me"

            # Environment variables for MCP server
            mcp_env = {
                **os.environ,
                "PYTHONUNBUFFERED": "1",
                "AILINUX_SERVER": server_url,
                "AILINUX_TOKEN": token,
                "AILINUX_TIER": tier,
            }

            # Start MCP server process
            self.local_mcp_process = subprocess.Popen(
                [sys.executable, str(mcp_server_path)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=str(Path.home()),
                env=mcp_env
            )

            logger.info(f"Local MCP server started (PID: {self.local_mcp_process.pid}, Tier: {tier})")
            self.statusbar.showMessage(f"MCP Server gestartet (Tier: {tier.upper()})", 3000)

            # Update MCP status in toolbar - show local ready, node status will update separately
            self.mcp_status_label.setText(tr("MCP: Local ready"))
            self.mcp_status_label.setStyleSheet("color: #4ade80; padding: 0 8px;")

        except Exception as e:
            logger.error(f"Failed to start local MCP server: {e}")
            self.statusbar.showMessage(f"MCP Server Fehler: {e}", 5000)
            self.mcp_status_label.setText(tr("MCP: Error"))
            self.mcp_status_label.setStyleSheet("color: #ef4444; padding: 0 8px;")

    def _stop_local_mcp_server(self):
        """Stop the local MCP server"""
        if self.local_mcp_process:
            try:
                self.local_mcp_process.terminate()
                self.local_mcp_process.wait(timeout=5)
                logger.info("Local MCP server stopped")
            except Exception as e:
                logger.error(f"Error stopping MCP server: {e}")
                self.local_mcp_process.kill()
            self.local_mcp_process = None
            self.mcp_status_label.setText(tr("MCP: Disconnected"))
            self.mcp_status_label.setStyleSheet("color: #888; padding: 0 8px;")

    def _get_allowed_mcp_tools(self) -> list:
        """Get allowed MCP tools based on user tier"""
        tier = self.api_client.tier or "free"

        # Basic tools for all registered users (free tier)
        basic_tools = [
            "file_read", "file_list", "file_search",
            "git_status", "git_log", "system_info"
        ]

        # Extended tools for pro tier
        pro_tools = basic_tools + [
            "file_write", "bash_exec", "git_diff",
            "codebase_search"
        ]

        # All tools for enterprise
        enterprise_tools = pro_tools + [
            "git_commit", "git_push", "docker_exec",
            "remote_exec", "admin_tools"
        ]

        if tier == "enterprise":
            return enterprise_tools
        elif tier == "pro":
            return pro_tools
        else:
            return basic_tools

    def _launch_cli_agent(self, agent_name: str):
        """Launch CLI agent with MCP integration"""
        # Check tier access
        tier_mgr = get_tier_manager(self.api_client)
        if not tier_mgr.can_use_cli_agents():
            QMessageBox.warning(
                self,
                "Tier 0.5+ Required",
                "CLI Agents are available from Tier 0.5 (Registered).\n\n"
                "Register for free at ailinux.me to unlock this feature."
            )
            return

        # Find agent
        agent = None
        for a in self.cli_agents:
            if a.name == agent_name:
                agent = a
                break

        if not agent:
            self.statusbar.showMessage(f"Agent not found: {agent_name}", 3000)
            return

        # Generate MCP config for the agent
        mcp_config_path = local_mcp_server.generate_config_for_agent(agent.name)

        # Build launch command
        working_dir = self.file_browser.current_path or str(Path.home())

        # Command to launch agent with MCP
        if agent.name == "claude":
            # Claude Code: claude --mcp-config <path>
            launch_cmd = f"{agent.path} --mcp-config {mcp_config_path}"
        elif agent.name == "gemini":
            # Gemini CLI
            launch_cmd = f"GEMINI_MCP_CONFIG={mcp_config_path} {agent.path}"
        elif agent.name == "codex":
            # Codex
            launch_cmd = f"{agent.path} --mcp {mcp_config_path}"
        else:
            # Generic
            launch_cmd = agent.path

        # Open new terminal tab with agent
        tab_title = f"🤖 {agent.display_name}"
        self.terminal_widget.add_tab(
            working_dir=working_dir,
            title=tab_title,
            startup_command=launch_cmd
        )

        # Switch to terminal
        for i in range(self.tabs.count()):
            if self.tabs.widget(i) == self.terminal_widget:
                self.tabs.setCurrentIndex(i)
                break

        self.statusbar.showMessage(f"Launched {agent.display_name}", 3000)

    # =========================================================================
    # MCP Node Connection
    # =========================================================================

    def _retry_mcp_connection(self):
        """Retry MCP Node connection if not yet connected"""
        if not HAS_MCP_NODE:
            return

        # Check if we now have authentication
        if (self.api_client.user_id or self.api_client.token) and not self.mcp_node_thread:
            logger.info("Retrying MCP Node connection after authentication")
            self._connect_mcp_node()
        elif not self.mcp_node_thread:
            # Still not authenticated, update status
            self.mcp_status_label.setText(tr("MCP: Local only"))
            self.mcp_status_label.setStyleSheet("color: #fbbf24; padding: 0 8px;")

    def _connect_mcp_node(self):
        """Connect to MCP Node WebSocket"""
        if not HAS_MCP_NODE:
            return

        if self.mcp_node_thread and self.mcp_node_thread.isRunning():
            return

        # Update status to show connecting
        self.mcp_status_label.setText(tr("MCP: Connecting..."))
        self.mcp_status_label.setStyleSheet("color: #60a5fa; padding: 0 8px;")

        self.mcp_node_thread = MCPNodeThread(self.api_client)
        self.mcp_node_thread.connected.connect(self._on_mcp_connected)
        self.mcp_node_thread.disconnected.connect(self._on_mcp_disconnected)
        self.mcp_node_thread.error.connect(self._on_mcp_error)
        self.mcp_node_thread.start()

    def _on_mcp_connected(self):
        self.mcp_status_label.setText("MCP: Connected")
        self.mcp_status_label.setStyleSheet("color: #4ade80; padding: 0 8px;")
        self.statusbar.showMessage("MCP Node connected", 3000)

    def _on_mcp_disconnected(self):
        self.mcp_status_label.setText("MCP: Disconnected")
        self.mcp_status_label.setStyleSheet("color: #888; padding: 0 8px;")

    def _on_mcp_error(self, error: str):
        self.mcp_status_label.setText("MCP: Error")
        self.mcp_status_label.setStyleSheet("color: #ef4444; padding: 0 8px;")
        logger.error(f"MCP Node error: {error}")

    def _reconnect_mcp_node(self):
        """Reconnect MCP Node"""
        if self.mcp_node_thread:
            self.mcp_node_thread.stop()
            self.mcp_node_thread.wait()

        if self.api_client.token:
            self._connect_mcp_node()

    def _show_mcp_status(self):
        """Show MCP status dialog"""
        # Local MCP server status
        local_status = "Running" if self.local_mcp_process else "Stopped"
        local_pid = self.local_mcp_process.pid if self.local_mcp_process else "N/A"

        # MCP Node status (optional remote connection)
        node_connected = self.mcp_node_thread and self.mcp_node_thread.running and self.mcp_node_thread.mcp_client
        node_status = "Connected" if node_connected else "Not connected"

        # Get session info from MCP client if available
        session_id = "N/A"
        machine_id = "N/A"
        if node_connected and self.mcp_node_thread.mcp_client:
            session_id = self.mcp_node_thread.mcp_client.session_id or "N/A"
            machine_id = self.mcp_node_thread.mcp_client.machine_id or "N/A"

        # Get tier info
        tier_mgr = get_tier_manager(self.api_client)

        msg = f"""Local MCP Server: {local_status} (PID: {local_pid})

Tier: {tier_mgr.config.display_name}
Server: {self.api_client.base_url}
Authenticated: {'Yes' if self.api_client.token else 'No'}
User ID: {self.api_client.user_id or 'N/A'}

MCP Node (Remote): {node_status}
Session ID: {session_id}
Machine ID: {machine_id}

CLI Agents: {len(self.cli_agents)}
"""
        for agent in self.cli_agents:
            msg += f"  - {agent.display_name}: {agent.path}\n"

        QMessageBox.information(self, tr("MCP Status"), msg)

    def _show_hardware_info(self):
        """Show hardware information dialog"""
        try:
            from ..core.hardware_detect import hardware_detector
            info = hardware_detector.get_summary()

            dialog = QDialog(self)
            dialog.setWindowTitle(tr("Hardware Info"))
            dialog.setMinimumSize(600, 500)
            dialog.setStyleSheet("background: #1e1e1e;")

            layout = QVBoxLayout(dialog)

            # Text browser for hardware info
            from PyQt6.QtWidgets import QTextBrowser
            text_browser = QTextBrowser()
            text_browser.setStyleSheet("""
                QTextBrowser {
                    background: #252525;
                    color: #e0e0e0;
                    border: 1px solid #333;
                    border-radius: 4px;
                    padding: 10px;
                    font-family: monospace;
                    font-size: 12px;
                }
            """)
            text_browser.setPlainText(info)
            layout.addWidget(text_browser)

            # Close button
            close_btn = QPushButton(tr("Close"))
            close_btn.clicked.connect(dialog.accept)
            layout.addWidget(close_btn)

            dialog.exec()

        except Exception as e:
            QMessageBox.warning(
                self,
                tr("Error"),
                f"Hardware detection failed: {e}"
            )

    # =========================================================================
    # Tab Management
    # =========================================================================

    def _new_chat(self):
        """Open new chat tab"""
        chat = ChatWidget(self.api_client)
        idx = self.tabs.addTab(chat, "💬 Chat")
        self.tabs.setCurrentIndex(idx)

    def _new_terminal(self):
        """Open new terminal tab"""
        working_dir = self.file_browser.current_path or str(Path.home())
        self.terminal_widget.add_tab(working_dir=working_dir)

        # Switch to terminal
        for i in range(self.tabs.count()):
            if self.tabs.widget(i) == self.terminal_widget:
                self.tabs.setCurrentIndex(i)
                break

    def _close_tab(self, index: int):
        """Close tab at index"""
        widget = self.tabs.widget(index)

        # Don't close main chat and terminal
        if widget == self.chat_widget or widget == self.terminal_widget:
            return

        self.tabs.removeTab(index)

    def _close_current_tab(self):
        """Close current tab"""
        self._close_tab(self.tabs.currentIndex())

    def _next_tab(self):
        """Switch to next tab"""
        idx = (self.tabs.currentIndex() + 1) % self.tabs.count()
        self.tabs.setCurrentIndex(idx)

    def _prev_tab(self):
        """Switch to previous tab"""
        idx = (self.tabs.currentIndex() - 1) % self.tabs.count()
        self.tabs.setCurrentIndex(idx)

    def _focus_chat(self):
        """Focus chat input"""
        for i in range(self.tabs.count()):
            if self.tabs.widget(i) == self.chat_widget:
                self.tabs.setCurrentIndex(i)
                self.chat_widget.focus_input()
                break

    def _focus_terminal(self):
        """Focus terminal"""
        for i in range(self.tabs.count()):
            if self.tabs.widget(i) == self.terminal_widget:
                self.tabs.setCurrentIndex(i)
                self.terminal_widget.focus_current()
                break

    def _get_focusable_widgets(self):
        """Get list of visible, focusable widgets in order"""
        widgets = []
        # Order: File Browser, Browser, Terminal, Chat
        if hasattr(self, 'file_browser') and self.file_browser.isVisible():
            widgets.append(('files', self.file_browser))
        if hasattr(self, 'browser_widget') and self.browser_widget.isVisible():
            widgets.append(('browser', self.browser_widget))
        if hasattr(self, 'terminal_widget') and self.terminal_widget.isVisible():
            widgets.append(('terminal', self.terminal_widget))
        if hasattr(self, 'chat_widget') and self.chat_widget.isVisible():
            widgets.append(('chat', self.chat_widget))
        return widgets

    def _get_current_focused_widget_index(self, widgets):
        """Find which widget currently has focus"""
        focused = QApplication.focusWidget()
        if not focused:
            return -1

        for i, (name, widget) in enumerate(widgets):
            # Check if focused widget is the widget or a child of it
            if focused == widget or widget.isAncestorOf(focused):
                return i
        return -1

    def _focus_widget(self, name: str, widget):
        """Focus a specific widget based on its type"""
        if name == 'terminal':
            self.terminal_widget.focus_current()
        elif name == 'chat':
            self.chat_widget.focus_input()
        elif name == 'browser':
            # Focus the current tab's web view
            tab = self.browser_widget.current_tab()
            if tab and hasattr(tab, 'focus_web_view'):
                tab.focus_web_view()
            else:
                self.browser_widget.url_bar.setFocus()
        elif name == 'files':
            self.file_browser.tree_view.setFocus()
        else:
            widget.setFocus()

    def _cycle_widget_focus(self):
        """Cycle focus to the next visible widget (Alt+Tab)"""
        widgets = self._get_focusable_widgets()
        if not widgets:
            return

        current_idx = self._get_current_focused_widget_index(widgets)
        next_idx = (current_idx + 1) % len(widgets)
        name, widget = widgets[next_idx]
        self._focus_widget(name, widget)
        logger.debug(f"Focused widget: {name}")

    def _cycle_widget_focus_reverse(self):
        """Cycle focus to the previous visible widget (Alt+Shift+Tab)"""
        widgets = self._get_focusable_widgets()
        if not widgets:
            return

        current_idx = self._get_current_focused_widget_index(widgets)
        prev_idx = (current_idx - 1) % len(widgets)
        name, widget = widgets[prev_idx]
        self._focus_widget(name, widget)
        logger.debug(f"Focused widget: {name}")

    # =========================================================================
    # View Actions - Toggleable Widgets
    # =========================================================================

    def _toggle_browser(self):
        """Toggle browser visibility"""
        visible = not self.browser_widget.isVisible()
        self.browser_widget.setVisible(visible)
        self._widget_visible['browser'] = visible
        self.action_toggle_browser.setChecked(visible)
        self.btn_browser.setChecked(visible)
        self._update_layout_for_visible_widgets()

    def _toggle_file_browser(self):
        """Toggle file browser visibility"""
        visible = not self.file_browser.isVisible()
        self.file_browser.setVisible(visible)
        self._widget_visible['files'] = visible
        self.action_toggle_filebrowser.setChecked(visible)
        self.btn_files.setChecked(visible)
        self._update_layout_for_visible_widgets()

    def _toggle_chat(self):
        """Toggle chat widget visibility"""
        visible = not self.chat_widget.isVisible()
        self.chat_widget.setVisible(visible)
        self._widget_visible['chat'] = visible
        self.action_toggle_chat.setChecked(visible)
        self.btn_chat.setChecked(visible)
        self._update_layout_for_visible_widgets()

    def _toggle_terminal(self):
        """Toggle terminal widget visibility"""
        visible = not self.terminal_widget.isVisible()
        self.terminal_widget.setVisible(visible)
        self._widget_visible['terminal'] = visible
        self.action_toggle_terminal.setChecked(visible)
        self.btn_terminal.setChecked(visible)
        self._update_layout_for_visible_widgets()

    def _toggle_panel(self):
        """Toggle desktop panel"""
        if hasattr(self, 'desktop_panel'):
            visible = not self.desktop_panel.isVisible()
            self.desktop_panel.setVisible(visible)
            if hasattr(self, 'action_toggle_panel'):
                self.action_toggle_panel.setChecked(visible)
            self._update_layout_for_visible_widgets()

    def _toggle_fullscreen(self):
        """Toggle fullscreen mode"""
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def _toggle_lock_screen(self):
        """Toggle lock screen - F5 to lock, F5 again to unlock with password"""
        if hasattr(self, '_lock_overlay') and self._lock_overlay and self._lock_overlay.isVisible():
            # Already locked - show unlock dialog
            self._show_unlock_dialog()
        else:
            # Lock the screen
            self._lock_screen()

    def _lock_screen(self):
        """Show lock screen overlay"""
        from PyQt6.QtWidgets import QFrame, QLabel
        from PyQt6.QtCore import Qt

        # Create lock overlay if not exists
        if not hasattr(self, '_lock_overlay') or not self._lock_overlay:
            self._lock_overlay = QFrame(self)

            # Get wallpaper from settings
            bg_image = self.settings.value("desktop_background", "")

            # Check default wallpaper paths
            default_wallpapers = [
                "/usr/share/backgrounds/ailinux-wallpaper.jpg",
                "/usr/share/backgrounds/default.jpg",
                os.path.expanduser("~/.config/ailinux/wallpaper.jpg"),
            ]

            if not bg_image or not os.path.exists(bg_image):
                for wp in default_wallpapers:
                    if os.path.exists(wp):
                        bg_image = wp
                        break

            if bg_image and os.path.exists(bg_image):
                # Wallpaper with dark overlay
                self._lock_overlay.setStyleSheet(f"""
                    QFrame {{
                        background-image: url({bg_image});
                        background-position: center;
                        background-repeat: no-repeat;
                        border: none;
                    }}
                """)
            else:
                # Gradient fallback
                self._lock_overlay.setStyleSheet("""
                    QFrame {
                        background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                            stop:0 #0a0a1a,
                            stop:0.3 #1a1a3e,
                            stop:0.6 #0f2027,
                            stop:1 #203a43);
                    }
                """)

            lock_layout = QVBoxLayout(self._lock_overlay)
            lock_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

            # Semi-transparent container for lock content
            lock_container = QFrame()
            lock_container.setStyleSheet("""
                QFrame {
                    background: rgba(10, 10, 20, 0.85);
                    border-radius: 20px;
                    padding: 40px;
                }
            """)
            lock_container.setFixedSize(300, 280)
            container_layout = QVBoxLayout(lock_container)
            container_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

            # Lock icon
            lock_icon = QLabel("🔒")
            lock_icon.setStyleSheet("font-size: 80px; color: #60a5fa; background: transparent;")
            lock_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
            container_layout.addWidget(lock_icon)

            # Lock message
            lock_msg = QLabel("Screen Locked")
            lock_msg.setStyleSheet("font-size: 24px; color: #e0e0e0; margin-top: 20px; background: transparent;")
            lock_msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
            container_layout.addWidget(lock_msg)

            # Unlock hint
            unlock_hint = QLabel("Press F5 to unlock")
            unlock_hint.setStyleSheet("font-size: 14px; color: #888; margin-top: 30px; background: transparent;")
            unlock_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
            container_layout.addWidget(unlock_hint)

            lock_layout.addWidget(lock_container)

        # Show overlay fullscreen over the window
        self._lock_overlay.setGeometry(self.rect())
        self._lock_overlay.raise_()
        self._lock_overlay.show()

        logger.info("Screen locked")

    def _show_unlock_dialog(self):
        """Show password dialog to unlock screen"""
        import pwd
        import os

        # Get current username
        username = pwd.getpwuid(os.getuid()).pw_name

        # Show password input dialog
        from PyQt6.QtWidgets import QInputDialog

        password, ok = QInputDialog.getText(
            self._lock_overlay,
            "Unlock Screen",
            f"Enter password for {username}:",
            QLineEdit.EchoMode.Password
        )

        if ok and password:
            # Verify password using PAM
            if self._verify_password(username, password):
                self._unlock_screen()
            else:
                QMessageBox.warning(
                    self._lock_overlay,
                    "Authentication Failed",
                    "Incorrect password. Please try again."
                )

    def _verify_password(self, username: str, password: str) -> bool:
        """Verify user password using PAM authentication"""
        # Try PAM first (most reliable)
        try:
            import pam
            p = pam.pam()
            if p.authenticate(username, password):
                return True
        except ImportError:
            logger.debug("python-pam not installed, trying alternatives")
        except Exception as e:
            logger.warning(f"PAM authentication error: {e}")

        # Fallback: Use pkexec with polkit (non-interactive check)
        try:
            import subprocess
            import crypt
            import spwd

            # Try to read shadow password (requires root or shadow group)
            try:
                shadow = spwd.getspnam(username)
                encrypted = shadow.sp_pwdp

                # Verify password
                if encrypted and encrypted != '!' and encrypted != '*':
                    result = crypt.crypt(password, encrypted)
                    if result == encrypted:
                        return True
            except (KeyError, PermissionError):
                pass

            # Last resort: use 'su' with expect-like approach via pty
            import pty
            import select

            master, slave = pty.openpty()
            proc = subprocess.Popen(
                ['su', '-c', 'echo OK', username],
                stdin=slave,
                stdout=slave,
                stderr=slave,
                close_fds=True
            )

            os.close(slave)

            # Wait for password prompt
            output = b''
            for _ in range(50):  # Max 5 seconds
                if select.select([master], [], [], 0.1)[0]:
                    try:
                        data = os.read(master, 1024)
                        if not data:
                            break
                        output += data
                        if b'assword' in output or b'Password' in output:
                            # Send password
                            os.write(master, (password + '\n').encode())
                            output = b''
                        elif b'OK' in output:
                            os.close(master)
                            proc.wait()
                            return True
                        elif b'failure' in output.lower() or b'incorrect' in output.lower():
                            break
                    except OSError:
                        break

            os.close(master)
            proc.wait(timeout=2)
            return False

        except Exception as e:
            logger.warning(f"Password verification failed: {e}")

        return False

    def _unlock_screen(self):
        """Hide lock screen overlay"""
        if hasattr(self, '_lock_overlay') and self._lock_overlay:
            self._lock_overlay.hide()
            logger.info("Screen unlocked")

    def resizeEvent(self, event):
        """Handle resize to keep lock overlay fullscreen"""
        super().resizeEvent(event)
        if hasattr(self, '_lock_overlay') and self._lock_overlay and self._lock_overlay.isVisible():
            self._lock_overlay.setGeometry(self.rect())

    def _auto_sort_layout(self):
        """Auto-sort layout to optimal proportions based on visible widgets and aspect ratio.
        Layout: Files | Browser+Terminal | Chat
        Adapts to screen aspect ratio (21:9 ultrawide vs 16:9 standard)
        """
        visible = self._widget_visible
        layout = self._get_layout_sizes()

        total_width = self.main_splitter.width()
        total_height = self.center_splitter.height() if hasattr(self, 'center_splitter') else 800

        # Get base proportions from aspect ratio config
        base_files = layout['main_splitter'][0]
        base_center = layout['main_splitter'][1]
        base_chat = layout['main_splitter'][2]
        base_total = base_files + base_center + base_chat

        # Calculate percentages
        files_pct = base_files / base_total if visible['files'] else 0
        center_pct = base_center / base_total if (visible['browser'] or visible['terminal']) else 0
        chat_pct = base_chat / base_total if visible['chat'] else 0

        # Normalize to 100%
        total_pct = files_pct + center_pct + chat_pct
        if total_pct > 0:
            files_pct /= total_pct
            center_pct /= total_pct
            chat_pct /= total_pct

        files_w = int(total_width * files_pct)
        center_w = int(total_width * center_pct)
        chat_w = int(total_width * chat_pct)

        self.main_splitter.setSizes([files_w, center_w, chat_w])

        # Center splitter (Browser | Terminal) - use aspect ratio config
        if hasattr(self, 'center_splitter'):
            browser_ratio = layout['center_splitter'][0]
            terminal_ratio = layout['center_splitter'][1]

            if visible['browser'] and visible['terminal']:
                self.center_splitter.setSizes([
                    int(total_height * browser_ratio),
                    int(total_height * terminal_ratio)
                ])
            elif visible['browser']:
                self.center_splitter.setSizes([total_height, 0])
            elif visible['terminal']:
                self.center_splitter.setSizes([0, total_height])

        self.statusbar.showMessage(f"Layout auto-sortiert ({layout['aspect']})", 2000)

    def _focus_mode(self):
        """Hide all widgets except browser - maximized view"""
        # Hide all except browser
        self.file_browser.setVisible(False)
        self.chat_widget.setVisible(False)
        self.terminal_widget.setVisible(False)

        self._widget_visible = {'browser': True, 'files': False, 'chat': False, 'terminal': False}

        self.action_toggle_filebrowser.setChecked(False)
        self.action_toggle_chat.setChecked(False)
        self.action_toggle_terminal.setChecked(False)
        self.btn_files.setChecked(False)
        self.btn_chat.setChecked(False)
        self.btn_terminal.setChecked(False)

        # Hide desktop panel if present
        if hasattr(self, 'desktop_panel'):
            self.desktop_panel.setVisible(False)
            if hasattr(self, 'action_toggle_panel'):
                self.action_toggle_panel.setChecked(False)

        # Hide toolbar and menubar
        for toolbar in self.findChildren(QToolBar):
            toolbar.setVisible(False)
        self.menuBar().setVisible(False)
        self.statusbar.setVisible(False)

        # Go fullscreen
        if not self.isFullScreen():
            self.showFullScreen()

        self._update_layout_for_visible_widgets()

    def _show_all_widgets(self):
        """Show all widgets - restore normal view"""
        # Show all widgets
        self.browser_widget.setVisible(True)
        self.file_browser.setVisible(True)
        self.chat_widget.setVisible(True)
        self.terminal_widget.setVisible(True)

        self._widget_visible = {'browser': True, 'files': True, 'chat': True, 'terminal': True}

        self.action_toggle_browser.setChecked(True)
        self.action_toggle_filebrowser.setChecked(True)
        self.action_toggle_chat.setChecked(True)
        self.action_toggle_terminal.setChecked(True)
        self.btn_browser.setChecked(True)
        self.btn_files.setChecked(True)
        self.btn_chat.setChecked(True)
        self.btn_terminal.setChecked(True)

        # Show desktop panel if present
        if hasattr(self, 'desktop_panel'):
            self.desktop_panel.setVisible(True)
            if hasattr(self, 'action_toggle_panel'):
                self.action_toggle_panel.setChecked(True)

        # Show toolbar and menubar
        for toolbar in self.findChildren(QToolBar):
            toolbar.setVisible(True)
        self.menuBar().setVisible(True)
        self.statusbar.setVisible(True)

        # Auto-sort layout
        self._auto_sort_layout()

        self.statusbar.showMessage("Alle Widgets wiederhergestellt", 3000)

    def _update_layout_for_visible_widgets(self):
        """Update layout when widgets are toggled - maximize remaining content
        Layout: Files | Browser+Terminal | Chat
        Uses aspect ratio detection for optimal proportions.
        """
        visible = self._widget_visible
        layout = self._get_layout_sizes()

        files_vis = visible.get('files', True)
        chat_vis = visible.get('chat', True)
        browser_vis = visible.get('browser', True)
        terminal_vis = visible.get('terminal', True)

        total_width = self.main_splitter.width()
        total_height = self.center_splitter.height() if hasattr(self, 'center_splitter') else 800

        # Get base proportions from aspect ratio config
        base_files = layout['main_splitter'][0]
        base_center = layout['main_splitter'][1]
        base_chat = layout['main_splitter'][2]
        base_total = base_files + base_center + base_chat

        # Horizontal sizes (Files | Center | Chat)
        sizes = []
        sizes.append(int(total_width * base_files / base_total) if files_vis else 0)
        sizes.append(int(total_width * base_center / base_total) if (browser_vis or terminal_vis) else 0)
        sizes.append(int(total_width * base_chat / base_total) if chat_vis else 0)

        # Normalize horizontal
        total = sum(sizes)
        if total > 0:
            factor = total_width / total
            sizes = [int(s * factor) for s in sizes]

        self.main_splitter.setSizes(sizes)

        # Update center splitter (Browser | Terminal) using aspect ratio config
        if hasattr(self, 'center_splitter'):
            browser_ratio = layout['center_splitter'][0]
            terminal_ratio = layout['center_splitter'][1]

            if browser_vis and terminal_vis:
                self.center_splitter.setSizes([
                    int(total_height * browser_ratio),
                    int(total_height * terminal_ratio)
                ])
            elif browser_vis:
                self.center_splitter.setSizes([total_height, 0])
            elif terminal_vis:
                self.center_splitter.setSizes([0, total_height])

    def _on_file_selected(self, file_path: str):
        """Handle file selection in browser"""
        # Could open in editor tab
        self.statusbar.showMessage(f"Selected: {file_path}", 3000)

    # =========================================================================
    # Settings & Dialogs
    # =========================================================================

    def _open_settings(self):
        """Open settings dialog"""
        from .settings_dialog import SettingsDialog
        dialog = SettingsDialog(self.api_client, self)
        if dialog.exec():
            self._apply_settings()

    def _apply_overlay_opacity(self, widget: QWidget, opacity: float):
        """Apply overlay opacity to the central widget for contrast over wallpaper"""
        # Clamp opacity between 0 and 1
        opacity = max(0.0, min(1.0, opacity))
        # Convert to 0-255 for rgba
        alpha_int = int(opacity * 255)
        widget.setStyleSheet(f"""
            QWidget#centralWidget {{
                background: rgba(10, 10, 20, {opacity:.2f});
            }}
        """)

    def _apply_wallpaper(self):
        """Apply wallpaper setting to main window background"""
        bg_image = self.settings.value("desktop_background", "")

        # Default wallpaper paths to check
        default_wallpapers = [
            "/usr/share/backgrounds/ailinux-wallpaper.jpg",
            "/usr/share/backgrounds/default.jpg",
            os.path.expanduser("~/.config/ailinux/wallpaper.jpg"),
        ]

        # Find a valid wallpaper
        if not bg_image or not os.path.exists(bg_image):
            for wp in default_wallpapers:
                if os.path.exists(wp):
                    bg_image = wp
                    break

        if bg_image and os.path.exists(bg_image):
            bg_style = f"background-image: url({bg_image}); background-position: center; background-repeat: no-repeat;"
        else:
            bg_style = """background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 #0a0a1a,
                stop:0.3 #1a1a3e,
                stop:0.6 #0f2027,
                stop:1 #203a43);"""

        self.setStyleSheet(f"""
            QMainWindow {{
                {bg_style}
            }}
            QSplitter::handle {{
                background: rgba(255, 255, 255, 0.08);
                width: 3px;
                height: 3px;
                border-radius: 1px;
            }}
            QSplitter::handle:hover {{
                background: rgba(59, 130, 246, 0.7);
            }}
        """)

    def _apply_theme_colors(self):
        """Apply theme colors from settings to all UI components"""
        # Read theme colors from settings (with defaults)
        primary = self.settings.value("theme_color_primary", "#3b82f6")
        secondary = self.settings.value("theme_color_secondary", "#6366f1")
        accent = self.settings.value("theme_color_accent", "#8b5cf6")
        background = self.settings.value("theme_color_background", "#0a0a1a")
        surface = self.settings.value("theme_color_surface", "#1a1a2e")
        text_color = self.settings.value("theme_color_text", "#e0e0e0")
        border_radius = self.settings.value("widget_border_radius", 10, type=int)
        transparency = self.settings.value("widget_transparency", 85, type=int) / 100.0

        # Calculate surface with transparency
        def hex_to_rgba(hex_color, alpha):
            hex_color = hex_color.lstrip("#")
            r = int(hex_color[0:2], 16)
            g = int(hex_color[2:4], 16)
            b = int(hex_color[4:6], 16)
            return f"rgba({r}, {g}, {b}, {alpha:.2f})"

        surface_rgba = hex_to_rgba(surface, transparency)

        # Apply menubar styling
        self.menuBar().setStyleSheet(f"""
            QMenuBar {{
                background: rgba(20, 20, 30, 0.9);
                color: #c0c0c0;
                border-bottom: 1px solid rgba(255, 255, 255, 0.08);
                padding: 2px;
            }}
            QMenuBar::item {{
                padding: 6px 12px;
                border-radius: {border_radius - 6}px;
                margin: 2px;
            }}
            QMenuBar::item:selected {{
                background: {primary};
                color: white;
            }}
            QMenu {{
                background: {surface_rgba};
                color: {text_color};
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: {border_radius}px;
                padding: 4px;
            }}
            QMenu::item {{
                padding: 8px 24px;
                border-radius: {border_radius - 6}px;
                margin: 2px 4px;
            }}
            QMenu::item:selected {{
                background: {primary};
            }}
            QMenu::separator {{
                height: 1px;
                background: rgba(255, 255, 255, 0.1);
                margin: 4px 10px;
            }}
        """)

        # Apply toolbar styling
        for toolbar in self.findChildren(QToolBar):
            toolbar.setStyleSheet(f"""
                QToolBar {{
                    background: rgba(20, 20, 30, 0.85);
                    border: none;
                    border-bottom: 1px solid rgba(255, 255, 255, 0.05);
                    spacing: 6px;
                    padding: 6px 8px;
                }}
                QPushButton {{
                    background: rgba(255, 255, 255, 0.08);
                    color: #c0c0c0;
                    border: 1px solid rgba(255, 255, 255, 0.08);
                    border-radius: {border_radius - 4}px;
                    padding: 8px 16px;
                    font-size: 13px;
                    min-width: 80px;
                }}
                QPushButton:hover {{
                    background: {primary};
                    color: white;
                    border-color: {primary};
                }}
                QPushButton:pressed {{
                    background: {secondary};
                }}
                QPushButton:checked {{
                    background: {primary};
                    border: 1px solid {accent};
                    color: white;
                }}
                QPushButton.agent-btn {{
                    background: rgba(30, 58, 95, 0.7);
                    min-width: 70px;
                }}
                QPushButton.agent-btn:hover {{
                    background: {secondary};
                }}
            """)

        # Apply statusbar styling
        self.statusbar.setStyleSheet(f"""
            QStatusBar {{
                background: rgba(15, 15, 25, 0.9);
                color: #888;
                border-top: 1px solid rgba(255, 255, 255, 0.08);
                padding: 2px 8px;
            }}
        """)

        logger.info(f"Applied theme colors: primary={primary}, surface={surface}")

    def _apply_settings(self):
        """Apply settings changes to all components"""
        # Apply theme colors first
        self._apply_theme_colors()

        # Wallpaper and overlay
        self._apply_wallpaper()
        overlay_opacity = self.settings.value("overlay_opacity", 65, type=int) / 100.0
        central = self.centralWidget()
        if central:
            self._apply_overlay_opacity(central, overlay_opacity)

        # Desktop panel
        if hasattr(self, 'desktop_panel'):
            location = self.settings.value("weather_location", "")
            self.desktop_panel.set_weather_location(location)

        # File browser
        if hasattr(self, 'file_browser') and hasattr(self.file_browser, 'apply_settings'):
            self.file_browser.apply_settings()

        # Terminal widget
        if hasattr(self, 'terminal_widget') and hasattr(self.terminal_widget, 'apply_settings'):
            self.terminal_widget.apply_settings()

        # Browser widget
        if hasattr(self, 'browser_widget') and hasattr(self.browser_widget, 'apply_settings'):
            self.browser_widget.apply_settings()

        # Chat widget
        if hasattr(self, 'chat_widget') and hasattr(self.chat_widget, 'apply_settings'):
            self.chat_widget.apply_settings()

    def _show_about(self):
        """Show about dialog with header image"""
        from ..version import VERSION, BUILD_DATE
        
        # Find icon path for header image
        icon_path = None
        assets_path = Path(__file__).parent.parent / "assets" / "icon.jpg"
        root_path = Path(__file__).parent.parent.parent / "icon.jpg"
        
        if assets_path.exists():
            icon_path = str(assets_path)
        elif root_path.exists():
            icon_path = str(root_path)
        
        # Create custom About dialog with image header
        dialog = QDialog(self)
        dialog.setWindowTitle(tr("About AILinux Client"))
        dialog.setMinimumSize(450, 500)
        
        layout = QVBoxLayout(dialog)
        layout.setSpacing(15)
        
        # Header image
        if icon_path:
            from PyQt6.QtGui import QPixmap
            header_label = QLabel()
            pixmap = QPixmap(icon_path)
            # Scale to fit width while keeping aspect ratio
            scaled = pixmap.scaledToWidth(400, Qt.TransformationMode.SmoothTransformation)
            header_label.setPixmap(scaled)
            header_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(header_label)
        
        # Title
        title_label = QLabel("<h1 style='color: #7c3aed;'>AILinux Client</h1>")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)
        
        # Version info
        version_label = QLabel(f"<p style='font-size: 14px;'>Version <b>{VERSION}</b><br/>Build: {BUILD_DATE}</p>")
        version_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(version_label)
        
        # Description
        desc_html = """
        <div style='text-align: center; padding: 10px;'>
            <p>Desktop Client für die AILinux KI-Plattform</p>
            <p style='color: #666; font-size: 12px;'>
                <b>Features:</b><br/>
                • AI Chat mit lokalen & Cloud-Modellen<br/>
                • Terminal mit Tabs<br/>
                • CLI Agent Integration (Claude, Gemini, Codex)<br/>
                • MCP Node Verbindung<br/>
                • Desktop Panel Modus
            </p>
            <hr style='border: 1px solid #ddd; margin: 15px 0;'/>
            <p style='font-size: 11px; color: #888;'>
                © 2024-2025 AILinux Project<br/>
                Entwickelt von Markus Leitermann<br/>
                <a href='https://ailinux.me' style='color: #7c3aed;'>https://ailinux.me</a>
            </p>
        </div>
        """
        desc_label = QLabel(desc_html)
        desc_label.setOpenExternalLinks(True)
        desc_label.setWordWrap(True)
        layout.addWidget(desc_label)
        
        # OK button
        ok_btn = QPushButton(tr("OK"))
        ok_btn.setFixedWidth(100)
        ok_btn.clicked.connect(dialog.accept)
        
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(ok_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)
        
        dialog.exec()

    def _show_shortcuts(self):
        """Show keyboard shortcuts - uses ShortcutManager if available"""
        if HAS_SHORTCUT_MANAGER and hasattr(self, 'shortcut_manager'):
            # Generate shortcuts from manager
            shortcuts_html = self.shortcut_manager.get_shortcuts_html()
            content = f"""
            <style>
                table {{ border-collapse: collapse; width: 100%; }}
                td {{ padding: 4px 8px; }}
                td:first-child {{ font-weight: bold; white-space: nowrap; }}
            </style>
            {shortcuts_html}

            <h3>Terminal Shortcuts</h3>
            <table>
            <tr><td>Tab</td><td>Tab completion</td></tr>
            <tr><td>Ctrl+C</td><td>Interrupt (SIGINT)</td></tr>
            <tr><td>Ctrl+D</td><td>EOF / Exit</td></tr>
            <tr><td>Ctrl+Z</td><td>Suspend (SIGTSTP)</td></tr>
            <tr><td>Ctrl+L</td><td>Clear screen</td></tr>
            <tr><td>Ctrl+Shift+C</td><td>Copy selection</td></tr>
            <tr><td>Ctrl+Shift+V</td><td>Paste</td></tr>
            <tr><td>Shift+PageUp/Down</td><td>Scroll history</td></tr>
            </table>
            """
        else:
            # Fallback static content
            content = """<h3>Quick Toggles (F-Keys)</h3>
            <table>
            <tr><td><b>F1</b></td><td>Toggle Browser</td></tr>
            <tr><td><b>F2</b></td><td>Toggle File Browser</td></tr>
            <tr><td><b>F3</b></td><td>Toggle Chat</td></tr>
            <tr><td><b>F4</b></td><td>Toggle Terminal</td></tr>
            <tr><td><b>F5</b></td><td>Lock/Unlock Screen</td></tr>
            <tr><td>F11</td><td>Toggle Fullscreen</td></tr>
            </table>

            <h3>View Controls</h3>
            <table>
            <tr><td>Ctrl+B</td><td>Toggle File Browser</td></tr>
            <tr><td>Ctrl+Shift+B</td><td>Toggle Browser</td></tr>
            <tr><td>Ctrl+Shift+C</td><td>Toggle Chat</td></tr>
            <tr><td>Ctrl+T</td><td>Toggle Terminal</td></tr>
            <tr><td>Ctrl+Shift+P</td><td>Toggle Desktop Panel</td></tr>
            <tr><td>Ctrl+Shift+F</td><td>Focus Mode (hide all)</td></tr>
            <tr><td>Ctrl+Shift+A</td><td>Show All Widgets</td></tr>
            </table>

            <h3>Navigation</h3>
            <table>
            <tr><td>Ctrl+Tab</td><td>Next tab</td></tr>
            <tr><td>Ctrl+Shift+Tab</td><td>Previous tab</td></tr>
            <tr><td>Ctrl+W</td><td>Close tab</td></tr>
            <tr><td>Ctrl+L</td><td>Focus chat input</td></tr>
            <tr><td>Ctrl+`</td><td>Focus terminal</td></tr>
            </table>

            <h3>CLI Agents</h3>
            <table>
            <tr><td>Alt+C</td><td>Launch Claude Code</td></tr>
            <tr><td>Alt+G</td><td>Launch Gemini CLI</td></tr>
            <tr><td>Alt+X</td><td>Launch Codex</td></tr>
            <tr><td>Alt+O</td><td>Launch OpenCode</td></tr>
            </table>
            """

        QMessageBox.information(self, "Keyboard Shortcuts", content)

    # =========================================================================
    # File Menu Actions
    # =========================================================================

    def _open_file(self):
        """Open file dialog"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Datei öffnen",
            self.file_browser.current_path or str(Path.home()),
            "All Files (*);;Python (*.py);;Text (*.txt);;JSON (*.json);;YAML (*.yml *.yaml)"
        )
        if file_path:
            self.file_browser.navigate_to(Path(file_path).parent)
            self.statusbar.showMessage(f"Geöffnet: {file_path}", 3000)

    def _open_folder(self):
        """Open folder dialog"""
        folder_path = QFileDialog.getExistingDirectory(
            self,
            "Ordner öffnen",
            self.file_browser.current_path or str(Path.home())
        )
        if folder_path:
            self.file_browser.navigate_to(folder_path)
            self.statusbar.showMessage(f"Ordner: {folder_path}", 3000)

    def _logout(self):
        """Logout and return to login dialog"""
        reply = QMessageBox.question(
            self,
            "Logout",
            "Möchten Sie sich wirklich abmelden?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            # Clear credentials
            self.api_client.logout()

            # Stop MCP connections
            self._stop_local_mcp_server()
            if self.mcp_node_thread:
                self.mcp_node_thread.stop()

            # Close and restart app
            self.close()
            QMessageBox.information(
                None,
                "Logout erfolgreich",
                "Sie wurden abgemeldet. Bitte starten Sie die Anwendung neu."
            )

    # =========================================================================
    # Help Menu Actions
    # =========================================================================

    def _show_readme(self):
        """Show README in a dialog"""
        readme_content = self._get_readme_content()

        dialog = QDialog(self)
        dialog.setWindowTitle("AILinux Client - README")
        dialog.setMinimumSize(700, 500)
        dialog.setStyleSheet("background: #1e1e1e;")

        layout = QVBoxLayout(dialog)

        text_browser = QTextBrowser()
        text_browser.setOpenExternalLinks(True)
        text_browser.setStyleSheet("""
            QTextBrowser {
                background: #252525;
                color: #e0e0e0;
                border: 1px solid #333;
                border-radius: 4px;
                padding: 10px;
                font-family: monospace;
                font-size: 13px;
            }
        """)
        text_browser.setHtml(readme_content)
        layout.addWidget(text_browser)

        close_btn = QPushButton("Schließen")
        close_btn.clicked.connect(dialog.accept)
        layout.addWidget(close_btn)

        dialog.exec()

    def _get_readme_content(self) -> str:
        """Get README content"""
        # Try to load from file
        readme_paths = [
            Path(__file__).parent.parent.parent / "README.md",
            Path(__file__).parent.parent.parent / "README.txt",
            Path(__file__).parent.parent / "README.md",
        ]

        for readme_path in readme_paths:
            if readme_path.exists():
                try:
                    content = readme_path.read_text(encoding="utf-8")
                    # Simple markdown to HTML conversion
                    html = content.replace("\n", "<br>")
                    html = html.replace("# ", "<h1>").replace("<br><h1>", "<br><h1>")
                    html = html.replace("## ", "<h2>").replace("<br><h2>", "<br><h2>")
                    html = html.replace("### ", "<h3>")
                    html = html.replace("**", "<b>").replace("**", "</b>")
                    return f"<div style='font-family: sans-serif;'>{html}</div>"
                except Exception:
                    pass

        # Fallback content
        return """
        <h1>AILinux Client</h1>
        <p>Desktop-Client für die AILinux KI-Plattform.</p>

        <h2>Features</h2>
        <ul>
            <li><b>KI Chat:</b> Chat mit lokalen und Cloud-Modellen</li>
            <li><b>Terminal:</b> Integriertes PTY-Terminal mit Tabs</li>
            <li><b>File Browser:</b> Dateimanager mit Navigation</li>
            <li><b>CLI Agents:</b> Integration von Claude Code, Gemini CLI, Codex</li>
            <li><b>MCP Integration:</b> Model Context Protocol für Tool-Nutzung</li>
        </ul>

        <h2>Tastenkürzel</h2>
        <ul>
            <li><b>F1:</b> Diese Hilfe anzeigen</li>
            <li><b>Ctrl+B:</b> File Browser ein/ausblenden</li>
            <li><b>Ctrl+T:</b> Terminal ein/ausblenden</li>
            <li><b>Alt+C:</b> Claude Code starten</li>
            <li><b>Alt+G:</b> Gemini CLI starten</li>
        </ul>

        <h2>Tier-System</h2>
        <ul>
            <li><b>Free:</b> Basis-Tools (file_read, file_list, git_status)</li>
            <li><b>Pro:</b> Erweiterte Tools (file_write, bash_exec, codebase_search)</li>
            <li><b>Enterprise:</b> Alle Tools inkl. Remote-Execution</li>
        </ul>

        <p><i>Version 1.0.0 - © 2024 AILinux</i></p>
        """

    def _show_license(self):
        """Show License Agreement"""
        dialog = QDialog(self)
        dialog.setWindowTitle("License Agreement")
        dialog.setMinimumSize(600, 450)
        dialog.setStyleSheet("background: #1e1e1e;")

        layout = QVBoxLayout(dialog)

        text_browser = QTextBrowser()
        text_browser.setStyleSheet("""
            QTextBrowser {
                background: #252525;
                color: #e0e0e0;
                border: 1px solid #333;
                border-radius: 4px;
                padding: 10px;
                font-family: monospace;
                font-size: 12px;
            }
        """)
        text_browser.setHtml("""
        <h2>AILinux Client License Agreement</h2>
        <p><b>Copyright © 2024 AILinux. All rights reserved.</b></p>

        <h3>MIT License</h3>
        <p>Permission is hereby granted, free of charge, to any person obtaining a copy
        of this software and associated documentation files (the "Software"), to deal
        in the Software without restriction, including without limitation the rights
        to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
        copies of the Software, and to permit persons to whom the Software is
        furnished to do so, subject to the following conditions:</p>

        <p>The above copyright notice and this permission notice shall be included in all
        copies or substantial portions of the Software.</p>

        <p><b>THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
        IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
        FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
        AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
        LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
        OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
        SOFTWARE.</b></p>

        <h3>Third-Party Licenses</h3>
        <ul>
            <li><b>PyQt6:</b> GPL v3 / Commercial</li>
            <li><b>Python:</b> PSF License</li>
            <li><b>Claude Code:</b> Anthropic Terms of Service</li>
            <li><b>Gemini:</b> Google Terms of Service</li>
        </ul>

        <h3>Data Usage</h3>
        <p>Ihre Daten werden gemäß unserer Datenschutzrichtlinie behandelt.
        Lokale MCP-Tools haben Zugriff auf Ihr Dateisystem im Rahmen der
        gewählten Berechtigungen.</p>
        """)
        layout.addWidget(text_browser)

        close_btn = QPushButton("Akzeptieren & Schließen")
        close_btn.clicked.connect(dialog.accept)
        layout.addWidget(close_btn)

        dialog.exec()

    def _check_updates(self):
        """Check for updates"""
        # For now, just show a message
        QMessageBox.information(
            self,
            "Updates prüfen",
            """<h3>AILinux Client v1.0.0</h3>
            <p>Sie verwenden die aktuelle Version.</p>
            <p>Updates werden automatisch über das AILinux Repository verteilt.</p>
            <p><a href="https://ailinux.me/updates">https://ailinux.me/updates</a></p>
            """
        )

    def _report_bug(self):
        """Open bug report dialog/link"""
        import webbrowser
        reply = QMessageBox.question(
            self,
            "Bug melden",
            "Möchten Sie einen Bug auf GitHub melden?\n\nDies öffnet Ihren Browser.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            webbrowser.open("https://github.com/ailinux/client/issues/new")

    def _update_user_label(self):
        """Update user label and tier status"""
        tier_mgr = get_tier_manager(self.api_client)

        if self.api_client.user_id:
            self.user_label.setText(f"👤 {self.api_client.user_id}")
        else:
            self.user_label.setText("")

        # Update tier label with token/request info
        status_text = tier_mgr.get_status_text()
        status_color = tier_mgr.get_status_color()
        self.tier_label.setText(status_text)
        self.tier_label.setStyleSheet(f"color: {status_color}; font-weight: bold; padding: 0 8px;")

    def _update_tier_status(self):
        """Update tier status in statusbar (called periodically or after requests)"""
        tier_mgr = get_tier_manager(self.api_client)
        status_text = tier_mgr.get_status_text()
        status_color = tier_mgr.get_status_color()
        self.tier_label.setText(status_text)
        self.tier_label.setStyleSheet(f"color: {status_color}; font-weight: bold; padding: 0 8px;")

    # =========================================================================
    # Window State
    # =========================================================================

    def _load_window_settings(self):
        """Load window geometry and state"""
        geometry = self.settings.value("geometry")
        if geometry:
            self.restoreGeometry(geometry)

        state = self.settings.value("windowState")
        if state:
            self.restoreState(state)

        # Splitters
        main_splitter_state = self.settings.value("mainSplitterState")
        if main_splitter_state and hasattr(self, 'main_splitter'):
            self.main_splitter.restoreState(main_splitter_state)

        center_splitter_state = self.settings.value("centerSplitterState")
        if center_splitter_state and hasattr(self, 'center_splitter'):
            self.center_splitter.restoreState(center_splitter_state)

    def closeEvent(self, event):
        """Save settings on close"""
        # Save window state
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("windowState", self.saveState())

        # Save splitter states
        if hasattr(self, 'main_splitter'):
            self.settings.setValue("mainSplitterState", self.main_splitter.saveState())
        if hasattr(self, 'center_splitter'):
            self.settings.setValue("centerSplitterState", self.center_splitter.saveState())

        # Stop local MCP server
        self._stop_local_mcp_server()

        # Stop MCP Node
        if self.mcp_node_thread:
            self.mcp_node_thread.stop()
            self.mcp_node_thread.wait(3000)

        event.accept()


# =============================================================================
# Desktop Mode Launcher
# =============================================================================

def launch_desktop_mode():
    """Launch client in full desktop mode"""
    app = QApplication(sys.argv)
    app.setApplicationName("AILinux Desktop")

    # Create main window in desktop mode
    window = MainWindow(desktop_mode=True)
    window.showFullScreen()

    sys.exit(app.exec())


if __name__ == "__main__":
    launch_desktop_mode()
