"""
AILinux Settings Dialog
=======================

User settings configuration with component-specific tabs.
"""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget,
    QWidget, QLabel, QLineEdit, QPushButton,
    QFormLayout, QCheckBox, QSpinBox, QComboBox,
    QGroupBox, QMessageBox, QColorDialog, QFontComboBox,
    QSlider, QFrame, QListWidget, QListWidgetItem,
    QFileDialog, QInputDialog, QTextEdit
)
from PyQt6.QtCore import Qt, QSettings, pyqtSignal
from PyQt6.QtGui import QColor, QFont
import logging
import os

from ..translations import tr

# Import theme manager
try:
    from ..core.theme_manager import get_theme_manager, Theme, ThemeMetadata
    HAS_THEMES = True
except ImportError:
    HAS_THEMES = False

# Import autostart functions
try:
    from ..main import is_autostart_enabled, manage_autostart
    HAS_AUTOSTART = True
except ImportError:
    HAS_AUTOSTART = False

logger = logging.getLogger("ailinux.settings_dialog")


class ColorButton(QPushButton):
    """Button that shows and selects a color"""

    color_changed = pyqtSignal(str)

    def __init__(self, color: str = "#ffffff", parent=None):
        super().__init__(parent)
        self._color = color
        self.setFixedSize(60, 28)
        self._update_style()
        self.clicked.connect(self._pick_color)

    def _update_style(self):
        # Determine text color based on brightness
        c = QColor(self._color)
        brightness = (c.red() * 299 + c.green() * 587 + c.blue() * 114) / 1000
        text_color = "#000" if brightness > 128 else "#fff"
        self.setStyleSheet(f"""
            QPushButton {{
                background: {self._color};
                color: {text_color};
                border: 1px solid #555;
                border-radius: 4px;
                font-size: 10px;
            }}
            QPushButton:hover {{
                border-color: #3b82f6;
            }}
        """)
        self.setText(self._color.upper())

    def _pick_color(self):
        color = QColorDialog.getColor(QColor(self._color), self)
        if color.isValid():
            self._color = color.name()
            self._update_style()
            self.color_changed.emit(self._color)

    def color(self) -> str:
        return self._color

    def setColor(self, color: str):
        self._color = color
        self._update_style()


class SettingsDialog(QDialog):
    """
    Settings dialog with component-specific tabs

    Tabs:
    - Connection: Server URL, credentials
    - Desktop: Weather, panel settings
    - File Browser: Colors, sorting, display
    - Browser: Homepage, search engine
    - Terminal: Colors, font, scrollback
    - Chat: Model defaults, display
    - CLI Agents: Agent paths, MCP config
    """

    # Signal to notify components about setting changes
    settings_changed = pyqtSignal()

    def __init__(self, api_client, parent=None):
        super().__init__(parent)
        self.api_client = api_client
        self.settings = QSettings("AILinux", "Client")

        self.setWindowTitle(tr("Settings"))
        self.setMinimumSize(600, 500)
        self.setStyleSheet(self._get_base_style())

        self._setup_ui()
        self._load_settings()

    def _get_base_style(self) -> str:
        return """
            QDialog {
                background: #1e1e1e;
                color: #e0e0e0;
            }
            QTabWidget::pane {
                border: 1px solid #333;
                border-radius: 4px;
                background: #1e1e1e;
            }
            QTabBar::tab {
                background: #252525;
                color: #888;
                border: 1px solid #333;
                border-bottom: none;
                padding: 8px 16px;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background: #1e1e1e;
                color: #e0e0e0;
                border-bottom: 2px solid #3b82f6;
            }
            QTabBar::tab:hover:!selected {
                background: #333;
            }
            QGroupBox {
                border: 1px solid #333;
                border-radius: 4px;
                margin-top: 12px;
                padding-top: 8px;
                font-weight: bold;
            }
            QGroupBox::title {
                color: #3b82f6;
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
            QLineEdit, QSpinBox, QComboBox, QFontComboBox {
                background: #252525;
                border: 1px solid #333;
                border-radius: 4px;
                padding: 6px;
                color: #e0e0e0;
                min-height: 20px;
            }
            QLineEdit:focus, QSpinBox:focus, QComboBox:focus {
                border-color: #3b82f6;
            }
            QCheckBox {
                color: #e0e0e0;
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                border-radius: 3px;
                border: 1px solid #555;
                background: #252525;
            }
            QCheckBox::indicator:checked {
                background: #3b82f6;
                border-color: #3b82f6;
            }
            QPushButton {
                background: #3b82f6;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #2563eb;
            }
            QSlider::groove:horizontal {
                height: 6px;
                background: #333;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #3b82f6;
                width: 16px;
                margin: -5px 0;
                border-radius: 8px;
            }
            QLabel {
                color: #e0e0e0;
            }
        """

    def _setup_ui(self):
        """Setup UI"""
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Main tabs
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # Add all tabs
        self.tabs.addTab(self._create_themes_tab(), tr("Themes"))
        self.tabs.addTab(self._create_connection_tab(), tr("Connection"))
        self.tabs.addTab(self._create_desktop_tab(), tr("Desktop"))
        self.tabs.addTab(self._create_filebrowser_tab(), tr("File Browser"))
        self.tabs.addTab(self._create_browser_tab(), tr("Browser"))
        self.tabs.addTab(self._create_terminal_tab(), tr("Terminal"))
        self.tabs.addTab(self._create_chat_tab(), tr("Chat"))
        self.tabs.addTab(self._create_agents_tab(), tr("CLI Agents"))

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        reset_btn = QPushButton(tr("Reset to Defaults"))
        reset_btn.setStyleSheet("background: #666;")
        reset_btn.clicked.connect(self._reset_to_defaults)
        btn_layout.addWidget(reset_btn)

        cancel_btn = QPushButton(tr("Cancel"))
        cancel_btn.setStyleSheet("background: #444;")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        save_btn = QPushButton(tr("Save"))
        save_btn.clicked.connect(self._save_settings)
        btn_layout.addWidget(save_btn)

        layout.addLayout(btn_layout)

    # ==================== THEMES TAB ====================
    def _create_themes_tab(self) -> QWidget:
        """Create themes/skins settings tab with color customization"""
        widget = QWidget()
        layout = QHBoxLayout(widget)

        # Left side: Theme list
        left_layout = QVBoxLayout()

        # Theme selection group
        theme_group = QGroupBox(tr("Installed Themes"))
        theme_layout = QVBoxLayout(theme_group)

        self.theme_list = QListWidget()
        self.theme_list.setMinimumHeight(200)
        self.theme_list.itemClicked.connect(self._on_theme_selected)
        theme_layout.addWidget(self.theme_list)

        # Theme buttons
        theme_btn_layout = QHBoxLayout()

        apply_btn = QPushButton(tr("Apply"))
        apply_btn.clicked.connect(self._apply_selected_theme)
        theme_btn_layout.addWidget(apply_btn)

        delete_btn = QPushButton(tr("Delete"))
        delete_btn.setStyleSheet("background: #ef4444;")
        delete_btn.clicked.connect(self._delete_selected_theme)
        theme_btn_layout.addWidget(delete_btn)

        theme_layout.addLayout(theme_btn_layout)

        # Import/Export buttons
        io_layout = QHBoxLayout()

        import_btn = QPushButton(tr("Import Theme"))
        import_btn.clicked.connect(self._import_theme)
        io_layout.addWidget(import_btn)

        export_btn = QPushButton(tr("Export Theme"))
        export_btn.clicked.connect(self._export_theme)
        io_layout.addWidget(export_btn)

        theme_layout.addLayout(io_layout)

        left_layout.addWidget(theme_group)

        # Theme info
        info_group = QGroupBox(tr("Theme Info"))
        info_layout = QFormLayout(info_group)

        self.theme_name_label = QLabel("-")
        info_layout.addRow(tr("Name:"), self.theme_name_label)

        self.theme_author_label = QLabel("-")
        info_layout.addRow(tr("Author:"), self.theme_author_label)

        self.theme_desc_label = QLabel("-")
        self.theme_desc_label.setWordWrap(True)
        info_layout.addRow(tr("Description:"), self.theme_desc_label)

        left_layout.addWidget(info_group)
        left_layout.addStretch()

        layout.addLayout(left_layout)

        # Right side: Color customization
        right_layout = QVBoxLayout()

        # Colors group
        colors_group = QGroupBox(tr("Theme Colors"))
        colors_layout = QFormLayout(colors_group)

        self.theme_color_primary = ColorButton("#3b82f6")
        self.theme_color_primary.color_changed.connect(self._update_color_preview)
        colors_layout.addRow(tr("Primary:"), self.theme_color_primary)

        self.theme_color_secondary = ColorButton("#6366f1")
        self.theme_color_secondary.color_changed.connect(self._update_color_preview)
        colors_layout.addRow(tr("Secondary:"), self.theme_color_secondary)

        self.theme_color_accent = ColorButton("#8b5cf6")
        self.theme_color_accent.color_changed.connect(self._update_color_preview)
        colors_layout.addRow(tr("Accent:"), self.theme_color_accent)

        self.theme_color_background = ColorButton("#0a0a1a")
        self.theme_color_background.color_changed.connect(self._update_color_preview)
        colors_layout.addRow(tr("Background:"), self.theme_color_background)

        self.theme_color_surface = ColorButton("#1a1a2e")
        self.theme_color_surface.color_changed.connect(self._update_color_preview)
        colors_layout.addRow(tr("Surface:"), self.theme_color_surface)

        self.theme_color_text = ColorButton("#e0e0e0")
        self.theme_color_text.color_changed.connect(self._update_color_preview)
        colors_layout.addRow(tr("Text:"), self.theme_color_text)

        # Auto-contrast info
        self.contrast_info = QLabel("")
        self.contrast_info.setStyleSheet("color: #4ade80; font-size: 11px;")
        colors_layout.addRow("", self.contrast_info)

        # Randomize button
        randomize_btn = QPushButton(tr("Random Colors"))
        randomize_btn.clicked.connect(self._randomize_colors)
        colors_layout.addRow("", randomize_btn)

        right_layout.addWidget(colors_group)

        # Widget styling group
        widget_group = QGroupBox(tr("Widget Styling"))
        widget_layout = QFormLayout(widget_group)

        self.theme_border_radius = QSlider(Qt.Orientation.Horizontal)
        self.theme_border_radius.setRange(0, 20)
        self.theme_border_radius.setValue(10)
        self.theme_radius_label = QLabel("10px")
        self.theme_border_radius.valueChanged.connect(
            lambda v: self.theme_radius_label.setText(f"{v}px")
        )
        radius_row = QHBoxLayout()
        radius_row.addWidget(self.theme_border_radius)
        radius_row.addWidget(self.theme_radius_label)
        widget_layout.addRow(tr("Border Radius:"), radius_row)

        self.theme_transparency = QSlider(Qt.Orientation.Horizontal)
        self.theme_transparency.setRange(50, 100)
        self.theme_transparency.setValue(85)
        self.theme_trans_label = QLabel("85%")
        self.theme_transparency.valueChanged.connect(
            lambda v: self.theme_trans_label.setText(f"{v}%")
        )
        trans_row = QHBoxLayout()
        trans_row.addWidget(self.theme_transparency)
        trans_row.addWidget(self.theme_trans_label)
        widget_layout.addRow(tr("Transparency:"), trans_row)

        right_layout.addWidget(widget_group)

        # Save as new theme
        save_group = QGroupBox(tr("Save as New Theme"))
        save_layout = QFormLayout(save_group)

        self.new_theme_name = QLineEdit()
        self.new_theme_name.setPlaceholderText(tr("My Custom Theme"))
        save_layout.addRow(tr("Theme Name:"), self.new_theme_name)

        self.new_theme_author = QLineEdit()
        self.new_theme_author.setPlaceholderText(tr("Your Name"))
        save_layout.addRow(tr("Author:"), self.new_theme_author)

        save_theme_btn = QPushButton(tr("Save Theme"))
        save_theme_btn.clicked.connect(self._save_current_as_theme)
        save_layout.addRow("", save_theme_btn)

        right_layout.addWidget(save_group)
        right_layout.addStretch()

        layout.addLayout(right_layout)

        # Load theme list
        self._refresh_theme_list()

        return widget

    def _refresh_theme_list(self):
        """Refresh the theme list"""
        self.theme_list.clear()

        if not HAS_THEMES:
            item = QListWidgetItem(tr("Themes not available"))
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
            self.theme_list.addItem(item)
            return

        theme_mgr = get_theme_manager()
        for theme in theme_mgr.get_installed_themes():
            item = QListWidgetItem(f"🎨 {theme.metadata.name}")
            item.setData(Qt.ItemDataRole.UserRole, theme.metadata.name)
            self.theme_list.addItem(item)

    def _on_theme_selected(self, item: QListWidgetItem):
        """Handle theme selection"""
        if not HAS_THEMES:
            return

        theme_name = item.data(Qt.ItemDataRole.UserRole)
        theme_mgr = get_theme_manager()
        theme = theme_mgr.get_theme(theme_name)

        if theme:
            self.theme_name_label.setText(theme.metadata.name)
            self.theme_author_label.setText(theme.metadata.author)
            self.theme_desc_label.setText(theme.metadata.description)

            # Load colors
            self.theme_color_primary.setColor(theme.colors.primary)
            self.theme_color_secondary.setColor(theme.colors.secondary)
            self.theme_color_accent.setColor(theme.colors.accent)
            self.theme_color_background.setColor(theme.colors.background)
            self.theme_color_surface.setColor(theme.colors.surface)
            self.theme_color_text.setColor(theme.colors.text_primary)

            # Load styling
            self.theme_border_radius.setValue(theme.widgets.border_radius)
            self.theme_transparency.setValue(int(theme.widgets.transparency * 100))

            self._update_color_preview()

    def _apply_selected_theme(self):
        """Apply the selected theme"""
        if not HAS_THEMES:
            return

        item = self.theme_list.currentItem()
        if not item:
            QMessageBox.warning(self, tr("Warning"), tr("Please select a theme"))
            return

        theme_name = item.data(Qt.ItemDataRole.UserRole)
        theme_mgr = get_theme_manager()
        theme = theme_mgr.get_theme(theme_name)

        if theme:
            theme_mgr.apply_theme_to_settings(theme, self.settings)
            QMessageBox.information(
                self, tr("Theme Applied"),
                tr("Theme '{name}' applied successfully!").format(name=theme_name)
            )

    def _delete_selected_theme(self):
        """Delete the selected theme"""
        if not HAS_THEMES:
            return

        item = self.theme_list.currentItem()
        if not item:
            return

        theme_name = item.data(Qt.ItemDataRole.UserRole)

        reply = QMessageBox.question(
            self, tr("Delete Theme"),
            tr("Delete theme '{name}'?").format(name=theme_name),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            theme_mgr = get_theme_manager()
            if theme_mgr.delete_theme(theme_name):
                self._refresh_theme_list()

    def _import_theme(self):
        """Import theme from file"""
        if not HAS_THEMES:
            QMessageBox.warning(self, tr("Error"), tr("Themes not available"))
            return

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            tr("Import Theme"),
            os.path.expanduser("~"),
            tr("AILinux Theme Files") + " (*.ailinux-theme);;JSON (*.json)"
        )

        if file_path:
            theme_mgr = get_theme_manager()
            theme = theme_mgr.import_theme(file_path)
            if theme:
                QMessageBox.information(
                    self, tr("Success"),
                    tr("Theme '{name}' imported successfully!").format(name=theme.metadata.name)
                )
                self._refresh_theme_list()
            else:
                QMessageBox.warning(self, tr("Error"), tr("Failed to import theme"))

    def _export_theme(self):
        """Export current settings as theme"""
        if not HAS_THEMES:
            return

        # Get export filename
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            tr("Export Theme"),
            os.path.expanduser("~/my-theme.ailinux-theme"),
            tr("AILinux Theme Files") + " (*.ailinux-theme)"
        )

        if file_path:
            # Create theme from current color settings
            theme = self._create_theme_from_current()
            theme_mgr = get_theme_manager()

            # Ask if wallpaper should be embedded
            embed = QMessageBox.question(
                self, tr("Embed Wallpaper"),
                tr("Include wallpaper in theme file?\nThis makes the file larger but self-contained."),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            ) == QMessageBox.StandardButton.Yes

            if theme_mgr.export_theme(theme, file_path, embed_wallpaper=embed):
                QMessageBox.information(
                    self, tr("Success"),
                    tr("Theme exported to {path}").format(path=file_path)
                )

    def _save_current_as_theme(self):
        """Save current color settings as a new theme"""
        if not HAS_THEMES:
            return

        name = self.new_theme_name.text().strip()
        if not name:
            QMessageBox.warning(self, tr("Error"), tr("Please enter a theme name"))
            return

        theme = self._create_theme_from_current()
        theme.metadata.name = name
        theme.metadata.author = self.new_theme_author.text().strip() or "User"

        theme_mgr = get_theme_manager()
        if theme_mgr.save_theme(theme):
            QMessageBox.information(
                self, tr("Success"),
                tr("Theme '{name}' saved!").format(name=name)
            )
            self._refresh_theme_list()
            self.new_theme_name.clear()

    def _create_theme_from_current(self) -> "Theme":
        """Create theme from current UI settings"""
        from ..core.theme_manager import Theme, ThemeMetadata, ThemeColors, ThemeWidgets, ThemeOverlay

        theme = Theme()
        theme.metadata.name = self.new_theme_name.text() or "Custom Theme"
        theme.metadata.author = self.new_theme_author.text() or "User"

        # Colors
        theme.colors.primary = self.theme_color_primary.color()
        theme.colors.secondary = self.theme_color_secondary.color()
        theme.colors.accent = self.theme_color_accent.color()
        theme.colors.background = self.theme_color_background.color()
        theme.colors.surface = self.theme_color_surface.color()
        theme.colors.text_primary = self.theme_color_text.color()

        # Widgets
        theme.widgets.border_radius = self.theme_border_radius.value()
        theme.widgets.transparency = self.theme_transparency.value() / 100.0

        # Overlay
        theme.overlay.opacity = self.overlay_opacity.value() / 100.0

        # Wallpaper
        theme.wallpaper_path = self.wallpaper_path.text()

        return theme

    def _randomize_colors(self):
        """Generate random harmonious colors with good contrast"""
        import random
        import colorsys

        # Generate base hue
        base_hue = random.random()

        # Primary: saturated, medium bright
        primary_h = base_hue
        primary_s = 0.6 + random.random() * 0.3  # 60-90%
        primary_v = 0.6 + random.random() * 0.3  # 60-90%
        r, g, b = colorsys.hsv_to_rgb(primary_h, primary_s, primary_v)
        self.theme_color_primary.setColor(f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}")

        # Secondary: shifted hue (analogous)
        secondary_h = (base_hue + 0.08 + random.random() * 0.05) % 1.0
        secondary_s = 0.5 + random.random() * 0.3
        secondary_v = 0.5 + random.random() * 0.3
        r, g, b = colorsys.hsv_to_rgb(secondary_h, secondary_s, secondary_v)
        self.theme_color_secondary.setColor(f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}")

        # Accent: complementary or triadic
        accent_h = (base_hue + 0.33 + random.random() * 0.1) % 1.0
        accent_s = 0.5 + random.random() * 0.4
        accent_v = 0.6 + random.random() * 0.3
        r, g, b = colorsys.hsv_to_rgb(accent_h, accent_s, accent_v)
        self.theme_color_accent.setColor(f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}")

        # Background: very dark, slight hue tint
        bg_s = 0.1 + random.random() * 0.2  # Low saturation
        bg_v = 0.05 + random.random() * 0.08  # Very dark
        r, g, b = colorsys.hsv_to_rgb(base_hue, bg_s, bg_v)
        self.theme_color_background.setColor(f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}")

        # Surface: slightly lighter than background
        surface_s = 0.1 + random.random() * 0.15
        surface_v = 0.10 + random.random() * 0.10
        r, g, b = colorsys.hsv_to_rgb(base_hue, surface_s, surface_v)
        self.theme_color_surface.setColor(f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}")

        # Text: always high contrast (light for dark themes)
        text_v = 0.85 + random.random() * 0.1
        text_s = 0.0 + random.random() * 0.1
        r, g, b = colorsys.hsv_to_rgb(base_hue, text_s, text_v)
        self.theme_color_text.setColor(f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}")

        self._update_color_preview()

    def _update_color_preview(self):
        """Update contrast info based on current colors"""
        # Calculate contrast ratio between text and background
        bg_color = QColor(self.theme_color_background.color())
        text_color = QColor(self.theme_color_text.color())

        # Calculate relative luminance
        def luminance(color):
            r = color.redF()
            g = color.greenF()
            b = color.blueF()
            r = r / 12.92 if r <= 0.03928 else ((r + 0.055) / 1.055) ** 2.4
            g = g / 12.92 if g <= 0.03928 else ((g + 0.055) / 1.055) ** 2.4
            b = b / 12.92 if b <= 0.03928 else ((b + 0.055) / 1.055) ** 2.4
            return 0.2126 * r + 0.7152 * g + 0.0722 * b

        lum_bg = luminance(bg_color)
        lum_text = luminance(text_color)

        # Contrast ratio
        lighter = max(lum_bg, lum_text)
        darker = min(lum_bg, lum_text)
        ratio = (lighter + 0.05) / (darker + 0.05)

        # WCAG guidelines: 4.5:1 for normal text, 3:1 for large text
        if ratio >= 7:
            status = "✓ " + tr("Excellent contrast") + f" ({ratio:.1f}:1)"
            color = "#4ade80"  # Green
        elif ratio >= 4.5:
            status = "✓ " + tr("Good contrast") + f" ({ratio:.1f}:1)"
            color = "#a3e635"  # Light green
        elif ratio >= 3:
            status = "⚠ " + tr("Acceptable contrast") + f" ({ratio:.1f}:1)"
            color = "#fbbf24"  # Yellow
        else:
            status = "✗ " + tr("Poor contrast") + f" ({ratio:.1f}:1)"
            color = "#ef4444"  # Red

        self.contrast_info.setText(status)
        self.contrast_info.setStyleSheet(f"color: {color}; font-size: 11px;")

    # ==================== CONNECTION TAB ====================
    def _create_connection_tab(self) -> QWidget:
        """Create connection settings tab with login and user profile"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Server group
        server_group = QGroupBox(tr("Server"))
        server_layout = QFormLayout(server_group)

        self.server_url = QLineEdit()
        self.server_url.setPlaceholderText("https://api.ailinux.me")
        server_layout.addRow(tr("Server URL:"), self.server_url)

        layout.addWidget(server_group)

        # Login group (Email + Password only)
        login_group = QGroupBox(tr("Login"))
        login_layout = QFormLayout(login_group)

        self.login_email = QLineEdit()
        self.login_email.setPlaceholderText("deine@email.de")
        login_layout.addRow(tr("Email:"), self.login_email)

        self.login_password = QLineEdit()
        self.login_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.login_password.setPlaceholderText("••••••••")
        login_layout.addRow(tr("Passwort:"), self.login_password)

        # Login/Logout buttons
        btn_row = QHBoxLayout()
        self.login_btn = QPushButton(tr("🔐 Einloggen"))
        self.login_btn.clicked.connect(self._do_login)
        self.login_btn.setStyleSheet("""
            QPushButton {
                background: #3b82f6;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-weight: bold;
            }
            QPushButton:hover { background: #2563eb; }
        """)
        btn_row.addWidget(self.login_btn)
        
        self.logout_btn = QPushButton(tr("🚪 Ausloggen"))
        self.logout_btn.clicked.connect(self._do_logout)
        self.logout_btn.setStyleSheet("""
            QPushButton {
                background: #ef4444;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
            }
            QPushButton:hover { background: #dc2626; }
        """)
        btn_row.addWidget(self.logout_btn)
        login_layout.addRow("", btn_row)

        # Status label
        self.login_status = QLabel("Nicht eingeloggt")
        self.login_status.setStyleSheet("color: #888;")
        login_layout.addRow("", self.login_status)

        layout.addWidget(login_group)

        # User Profile group (editable)
        profile_group = QGroupBox(tr("Benutzerprofil"))
        profile_layout = QFormLayout(profile_group)

        self.profile_name = QLineEdit()
        self.profile_name.setPlaceholderText("Dein Name")
        profile_layout.addRow(tr("Name:"), self.profile_name)

        self.profile_email = QLineEdit()
        self.profile_email.setReadOnly(True)
        self.profile_email.setStyleSheet("background: #2a2a2a; color: #888;")
        profile_layout.addRow(tr("Email:"), self.profile_email)

        self.profile_tier = QLabel("--")
        self.profile_tier.setStyleSheet("color: #4ade80; font-weight: bold;")
        profile_layout.addRow(tr("Tier:"), self.profile_tier)

        self.profile_tokens = QLabel("--")
        self.profile_tokens.setStyleSheet("color: #60a5fa;")
        profile_layout.addRow(tr("Tokens heute:"), self.profile_tokens)

        self.profile_created = QLabel("--")
        self.profile_created.setStyleSheet("color: #888;")
        profile_layout.addRow(tr("Registriert:"), self.profile_created)

        # Save profile button
        save_profile_btn = QPushButton(tr("💾 Profil speichern"))
        save_profile_btn.clicked.connect(self._save_profile)
        save_profile_btn.setStyleSheet("""
            QPushButton {
                background: #22c55e;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
            }
            QPushButton:hover { background: #16a34a; }
        """)
        profile_layout.addRow("", save_profile_btn)

        layout.addWidget(profile_group)
        layout.addStretch()

        # Update UI based on login status
        self._update_login_ui()

        return widget

    def _do_login(self):
        """Perform login with email and password"""
        email = self.login_email.text().strip()
        password = self.login_password.text()
        
        if not email or not password:
            QMessageBox.warning(self, "Login", "Bitte Email und Passwort eingeben.")
            return
        
        try:
            if self.api_client:
                result = self.api_client.login(email, password)
                if result.get("success"):
                    self.login_status.setText(f"✅ Eingeloggt als {email}")
                    self.login_status.setStyleSheet("color: #4ade80;")
                    self._load_user_profile()
                    self._update_login_ui()
                    QMessageBox.information(self, "Login", "Erfolgreich eingeloggt!")
                else:
                    self.login_status.setText(f"❌ {result.get('error', 'Login fehlgeschlagen')}")
                    self.login_status.setStyleSheet("color: #ef4444;")
        except Exception as e:
            self.login_status.setText(f"❌ Fehler: {e}")
            self.login_status.setStyleSheet("color: #ef4444;")

    def _do_logout(self):
        """Perform logout"""
        try:
            if self.api_client:
                self.api_client.logout()
            self.login_status.setText("Ausgeloggt")
            self.login_status.setStyleSheet("color: #888;")
            self._clear_profile()
            self._update_login_ui()
        except Exception as e:
            logger.error(f"Logout error: {e}")

    def _update_login_ui(self):
        """Update UI based on login status"""
        is_logged_in = self.api_client and self.api_client.is_authenticated()
        
        self.login_email.setEnabled(not is_logged_in)
        self.login_password.setEnabled(not is_logged_in)
        self.login_btn.setEnabled(not is_logged_in)
        self.logout_btn.setEnabled(is_logged_in)
        
        if is_logged_in:
            self.login_status.setText(f"✅ Eingeloggt")
            self.login_status.setStyleSheet("color: #4ade80;")
            self._load_user_profile()
        else:
            self._clear_profile()

    def _load_user_profile(self):
        """Load user profile from server"""
        try:
            if self.api_client and self.api_client.is_authenticated():
                # Get user info from API
                user_info = self.api_client._request("GET", "/v1/client/tier")
                
                self.profile_email.setText(self.api_client.user_id or "--")
                self.profile_tier.setText(f"Tier {user_info.get('tier', 0)} ({user_info.get('tier_name', 'Free')})")
                
                tokens = user_info.get("tokens_today", 0)
                limit = user_info.get("token_limit", 100000)
                self.profile_tokens.setText(f"{tokens:,} / {limit:,}")
                
                # Load profile name from settings
                self.profile_name.setText(self.settings.value("profile_name", ""))
                self.profile_created.setText(user_info.get("created", "--"))
        except Exception as e:
            logger.error(f"Failed to load profile: {e}")

    def _clear_profile(self):
        """Clear profile fields"""
        self.profile_name.setText("")
        self.profile_email.setText("--")
        self.profile_tier.setText("--")
        self.profile_tokens.setText("--")
        self.profile_created.setText("--")

    def _save_profile(self):
        """Save profile changes"""
        self.settings.setValue("profile_name", self.profile_name.text())
        QMessageBox.information(self, "Profil", "Profil gespeichert!")

    # ==================== DESKTOP TAB ====================
    def _create_desktop_tab(self) -> QWidget:
        """Create desktop settings tab"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Background/Wallpaper group
        bg_group = QGroupBox(tr("Background"))
        bg_layout = QFormLayout(bg_group)

        # Wallpaper path with browse button
        wallpaper_row = QHBoxLayout()
        self.wallpaper_path = QLineEdit()
        self.wallpaper_path.setPlaceholderText(tr("Path to wallpaper image..."))
        wallpaper_row.addWidget(self.wallpaper_path)

        browse_btn = QPushButton(tr("Browse"))
        browse_btn.setFixedWidth(80)
        browse_btn.clicked.connect(self._browse_wallpaper)
        wallpaper_row.addWidget(browse_btn)

        bg_layout.addRow(tr("Wallpaper:"), wallpaper_row)

        # Overlay opacity slider
        self.overlay_opacity = QSlider(Qt.Orientation.Horizontal)
        self.overlay_opacity.setRange(0, 100)
        self.overlay_opacity.setValue(65)  # 65% opacity default
        self.overlay_opacity_label = QLabel("65%")
        self.overlay_opacity.valueChanged.connect(
            lambda v: self.overlay_opacity_label.setText(f"{v}%")
        )
        opacity_row = QHBoxLayout()
        opacity_row.addWidget(self.overlay_opacity)
        opacity_row.addWidget(self.overlay_opacity_label)
        bg_layout.addRow(tr("Overlay Opacity:"), opacity_row)

        layout.addWidget(bg_group)

        # Panel group
        panel_group = QGroupBox(tr("Desktop Panel"))
        panel_layout = QFormLayout(panel_group)

        self.weather_location = QLineEdit()
        self.weather_location.setPlaceholderText("Berlin, DE")
        panel_layout.addRow(tr("Weather Location:"), self.weather_location)

        self.show_seconds = QCheckBox()
        panel_layout.addRow(tr("Show Seconds:"), self.show_seconds)

        self.show_date = QCheckBox()
        self.show_date.setChecked(True)
        panel_layout.addRow(tr("Show Date:"), self.show_date)

        layout.addWidget(panel_group)

        # Startup group
        startup_group = QGroupBox(tr("Startup"))
        startup_layout = QFormLayout(startup_group)

        self.autostart_enabled = QCheckBox(tr("Start on system boot (systemd)"))
        startup_layout.addRow("", self.autostart_enabled)

        self.desktop_mode = QCheckBox(tr("Start in desktop mode"))
        startup_layout.addRow("", self.desktop_mode)

        self.auto_connect = QCheckBox(tr("Auto-connect MCP Node"))
        self.auto_connect.setChecked(True)
        startup_layout.addRow("", self.auto_connect)

        layout.addWidget(startup_group)
        layout.addStretch()

        return widget

    def _browse_wallpaper(self):
        """Browse for wallpaper image"""
        from PyQt6.QtWidgets import QFileDialog
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            tr("Select Wallpaper"),
            os.path.expanduser("~"),
            tr("Images") + " (*.jpg *.jpeg *.png *.bmp *.webp)"
        )
        if file_path:
            self.wallpaper_path.setText(file_path)

    # ==================== FILE BROWSER TAB ====================
    def _create_filebrowser_tab(self) -> QWidget:
        """Create file browser settings tab"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Display group
        display_group = QGroupBox(tr("Display"))
        display_layout = QFormLayout(display_group)

        self.fb_show_hidden = QCheckBox(tr("Show hidden files"))
        display_layout.addRow("", self.fb_show_hidden)

        self.fb_show_size = QCheckBox(tr("Show file size column"))
        self.fb_show_size.setChecked(True)
        display_layout.addRow("", self.fb_show_size)

        self.fb_show_date = QCheckBox(tr("Show date column"))
        self.fb_show_date.setChecked(True)
        display_layout.addRow("", self.fb_show_date)

        self.fb_sort_folders_first = QCheckBox(tr("Sort folders before files"))
        self.fb_sort_folders_first.setChecked(True)
        display_layout.addRow("", self.fb_sort_folders_first)

        layout.addWidget(display_group)

        # Colors group
        colors_group = QGroupBox(tr("File Type Colors"))
        colors_layout = QFormLayout(colors_group)

        self.fb_color_folder = ColorButton("#4fc3f7")
        colors_layout.addRow(tr("Folders:"), self.fb_color_folder)

        self.fb_color_python = ColorButton("#4caf50")
        colors_layout.addRow(tr("Python (.py):"), self.fb_color_python)

        self.fb_color_js = ColorButton("#ffeb3b")
        colors_layout.addRow(tr("JavaScript (.js):"), self.fb_color_js)

        self.fb_color_html = ColorButton("#ff9800")
        colors_layout.addRow(tr("HTML/CSS:"), self.fb_color_html)

        self.fb_color_image = ColorButton("#e91e63")
        colors_layout.addRow(tr("Images:"), self.fb_color_image)

        self.fb_color_archive = ColorButton("#9c27b0")
        colors_layout.addRow(tr("Archives (.zip, .tar):"), self.fb_color_archive)

        self.fb_color_exec = ColorButton("#f44336")
        colors_layout.addRow(tr("Executables:"), self.fb_color_exec)

        self.fb_color_text = ColorButton("#e0e0e0")
        colors_layout.addRow(tr("Text files:"), self.fb_color_text)

        layout.addWidget(colors_group)
        layout.addStretch()

        return widget

    # ==================== BROWSER TAB ====================
    def _create_browser_tab(self) -> QWidget:
        """Create browser settings tab"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # General group
        general_group = QGroupBox(tr("General"))
        general_layout = QFormLayout(general_group)

        self.browser_homepage = QLineEdit()
        self.browser_homepage.setPlaceholderText("https://www.google.com")
        general_layout.addRow(tr("Homepage:"), self.browser_homepage)

        self.browser_search_engine = QComboBox()
        self.browser_search_engine.addItems([
            "Google",
            "DuckDuckGo",
            "Bing",
            "Brave Search",
            "Ecosia",
            "StartPage"
        ])
        general_layout.addRow(tr("Search Engine:"), self.browser_search_engine)

        self.browser_new_tab_url = QLineEdit()
        self.browser_new_tab_url.setPlaceholderText("about:blank")
        general_layout.addRow(tr("New Tab URL:"), self.browser_new_tab_url)

        layout.addWidget(general_group)

        # Behavior group
        behavior_group = QGroupBox(tr("Behavior"))
        behavior_layout = QFormLayout(behavior_group)

        self.browser_open_links_new_tab = QCheckBox(tr("Open links in new tab"))
        behavior_layout.addRow("", self.browser_open_links_new_tab)

        self.browser_block_popups = QCheckBox(tr("Block popup windows"))
        self.browser_block_popups.setChecked(True)
        behavior_layout.addRow("", self.browser_block_popups)

        self.browser_enable_js = QCheckBox(tr("Enable JavaScript"))
        self.browser_enable_js.setChecked(True)
        behavior_layout.addRow("", self.browser_enable_js)

        self.browser_clear_on_exit = QCheckBox(tr("Clear history on exit"))
        behavior_layout.addRow("", self.browser_clear_on_exit)

        layout.addWidget(behavior_group)

        # Privacy group
        privacy_group = QGroupBox(tr("Privacy"))
        privacy_layout = QFormLayout(privacy_group)

        self.browser_do_not_track = QCheckBox(tr("Send Do Not Track header"))
        self.browser_do_not_track.setChecked(True)
        privacy_layout.addRow("", self.browser_do_not_track)

        self.browser_block_third_party_cookies = QCheckBox(tr("Block third-party cookies"))
        privacy_layout.addRow("", self.browser_block_third_party_cookies)

        layout.addWidget(privacy_group)

        # Data management group
        data_group = QGroupBox(tr("Data Management"))
        data_layout = QVBoxLayout(data_group)

        self.browser_clear_data_btn = QPushButton(tr("Clear Browser Data..."))
        self.browser_clear_data_btn.setStyleSheet("""
            QPushButton {
                background: #dc2626;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #b91c1c;
            }
        """)
        self.browser_clear_data_btn.clicked.connect(self._show_clear_browser_data_dialog)
        data_layout.addWidget(self.browser_clear_data_btn)

        layout.addWidget(data_group)
        layout.addStretch()

        return widget

    # ==================== TERMINAL TAB ====================
    def _create_terminal_tab(self) -> QWidget:
        """Create terminal settings tab"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Colors group
        colors_group = QGroupBox(tr("Colors"))
        colors_layout = QFormLayout(colors_group)

        self.term_bg_color = ColorButton("#1e1e1e")
        colors_layout.addRow(tr("Background:"), self.term_bg_color)

        self.term_fg_color = ColorButton("#e0e0e0")
        colors_layout.addRow(tr("Foreground:"), self.term_fg_color)

        self.term_cursor_color = ColorButton("#3b82f6")
        colors_layout.addRow(tr("Cursor:"), self.term_cursor_color)

        self.term_selection_color = ColorButton("#3b82f6")
        colors_layout.addRow(tr("Selection:"), self.term_selection_color)

        layout.addWidget(colors_group)

        # Font group
        font_group = QGroupBox(tr("Font"))
        font_layout = QFormLayout(font_group)

        self.term_font_family = QFontComboBox()
        self.term_font_family.setCurrentFont(QFont("Monospace"))
        # Filter to monospace fonts
        self.term_font_family.setFontFilters(QFontComboBox.FontFilter.MonospacedFonts)
        font_layout.addRow(tr("Font Family:"), self.term_font_family)

        self.term_font_size = QSpinBox()
        self.term_font_size.setRange(8, 24)
        self.term_font_size.setValue(12)
        font_layout.addRow(tr("Font Size:"), self.term_font_size)

        layout.addWidget(font_group)

        # Scrolling group
        scroll_group = QGroupBox(tr("Scrolling"))
        scroll_layout = QFormLayout(scroll_group)

        self.term_scrollback = QSpinBox()
        self.term_scrollback.setRange(100, 100000)
        self.term_scrollback.setValue(10000)
        self.term_scrollback.setSingleStep(1000)
        scroll_layout.addRow(tr("Scrollback Lines:"), self.term_scrollback)

        self.term_scroll_on_output = QCheckBox(tr("Scroll to bottom on output"))
        self.term_scroll_on_output.setChecked(True)
        scroll_layout.addRow("", self.term_scroll_on_output)

        self.term_scroll_on_input = QCheckBox(tr("Scroll to bottom on input"))
        self.term_scroll_on_input.setChecked(True)
        scroll_layout.addRow("", self.term_scroll_on_input)

        layout.addWidget(scroll_group)

        # Misc group
        misc_group = QGroupBox(tr("Miscellaneous"))
        misc_layout = QFormLayout(misc_group)

        self.term_bell_enabled = QCheckBox(tr("Enable bell sound"))
        misc_layout.addRow("", self.term_bell_enabled)

        self.term_cursor_blink = QCheckBox(tr("Blink cursor"))
        self.term_cursor_blink.setChecked(True)
        misc_layout.addRow("", self.term_cursor_blink)

        layout.addWidget(misc_group)
        layout.addStretch()

        return widget

    # ==================== CHAT TAB ====================
    def _create_chat_tab(self) -> QWidget:
        """Create chat settings tab"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Model group
        model_group = QGroupBox(tr("Model Defaults"))
        model_layout = QFormLayout(model_group)

        self.chat_default_model = QComboBox()
        self.chat_default_model.addItems([
            "auto",
            "gemini/gemini-2.0-flash",
            "gemini/gemini-1.5-pro",
            "anthropic/claude-sonnet-4",
            "ollama/llama3.2",
            "ollama/qwen2.5:14b",
            "ollama/deepseek-r1:14b"
        ])
        model_layout.addRow(tr("Default Model:"), self.chat_default_model)

        self.chat_temperature = QSlider(Qt.Orientation.Horizontal)
        self.chat_temperature.setRange(0, 20)  # 0.0 - 2.0
        self.chat_temperature.setValue(7)  # 0.7
        self.chat_temp_label = QLabel("0.7")
        self.chat_temperature.valueChanged.connect(
            lambda v: self.chat_temp_label.setText(f"{v/10:.1f}")
        )
        temp_row = QHBoxLayout()
        temp_row.addWidget(self.chat_temperature)
        temp_row.addWidget(self.chat_temp_label)
        model_layout.addRow(tr("Temperature:"), temp_row)

        layout.addWidget(model_group)

        # Display group
        display_group = QGroupBox(tr("Display"))
        display_layout = QFormLayout(display_group)

        self.chat_show_timestamps = QCheckBox(tr("Show message timestamps"))
        display_layout.addRow("", self.chat_show_timestamps)

        self.chat_show_model_name = QCheckBox(tr("Show model name in responses"))
        self.chat_show_model_name.setChecked(True)
        display_layout.addRow("", self.chat_show_model_name)

        self.chat_auto_scroll = QCheckBox(tr("Auto-scroll to new messages"))
        self.chat_auto_scroll.setChecked(True)
        display_layout.addRow("", self.chat_auto_scroll)

        self.chat_syntax_highlight = QCheckBox(tr("Syntax highlighting in code blocks"))
        self.chat_syntax_highlight.setChecked(True)
        display_layout.addRow("", self.chat_syntax_highlight)

        layout.addWidget(display_group)

        # History group
        history_group = QGroupBox(tr("History"))
        history_layout = QFormLayout(history_group)

        self.chat_max_history = QSpinBox()
        self.chat_max_history.setRange(10, 1000)
        self.chat_max_history.setValue(100)
        history_layout.addRow(tr("Max Messages:"), self.chat_max_history)

        self.chat_save_history = QCheckBox(tr("Save chat history"))
        self.chat_save_history.setChecked(True)
        history_layout.addRow("", self.chat_save_history)

        self.chat_clear_on_exit = QCheckBox(tr("Clear history on exit"))
        history_layout.addRow("", self.chat_clear_on_exit)

        layout.addWidget(history_group)

        # Input group
        input_group = QGroupBox(tr("Input"))
        input_layout = QFormLayout(input_group)

        self.chat_max_input_lines = QSpinBox()
        self.chat_max_input_lines.setRange(3, 20)
        self.chat_max_input_lines.setValue(10)
        input_layout.addRow(tr("Max Input Lines:"), self.chat_max_input_lines)

        self.chat_send_on_enter = QCheckBox(tr("Send on Enter (Shift+Enter for newline)"))
        self.chat_send_on_enter.setChecked(True)
        input_layout.addRow("", self.chat_send_on_enter)

        layout.addWidget(input_group)
        layout.addStretch()

        return widget

    # ==================== CLI AGENTS TAB ====================
    def _create_agents_tab(self) -> QWidget:
        """Create CLI agents settings tab"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Paths group
        paths_group = QGroupBox(tr("Agent Paths (leave empty for auto-detect)"))
        paths_layout = QFormLayout(paths_group)

        self.claude_path = QLineEdit()
        self.claude_path.setPlaceholderText("/usr/local/bin/claude")
        paths_layout.addRow(tr("Claude Code:"), self.claude_path)

        self.gemini_path = QLineEdit()
        self.gemini_path.setPlaceholderText("/usr/local/bin/gemini")
        paths_layout.addRow(tr("Gemini CLI:"), self.gemini_path)

        self.codex_path = QLineEdit()
        self.codex_path.setPlaceholderText("/usr/local/bin/codex")
        paths_layout.addRow(tr("Codex:"), self.codex_path)

        self.opencode_path = QLineEdit()
        self.opencode_path.setPlaceholderText("/usr/local/bin/opencode")
        paths_layout.addRow(tr("OpenCode:"), self.opencode_path)

        layout.addWidget(paths_group)

        # MCP group
        mcp_group = QGroupBox(tr("MCP Integration"))
        mcp_layout = QFormLayout(mcp_group)

        self.mcp_enabled = QCheckBox(tr("Enable MCP integration for agents"))
        self.mcp_enabled.setChecked(True)
        mcp_layout.addRow("", self.mcp_enabled)

        layout.addWidget(mcp_group)
        layout.addStretch()

        return widget

    # ==================== LOAD/SAVE SETTINGS ====================
    def _load_settings(self):
        """Load settings from storage"""
        # Connection
        self.server_url.setText(
            self.settings.value("server_url", "https://api.ailinux.me")
        )
        # Removed: user_id load
        # Removed: client_id
        self.client_secret.setText(self.settings.value("client_secret", ""))

        # Desktop - Background
        self.wallpaper_path.setText(self.settings.value("desktop_background", ""))
        self.overlay_opacity.setValue(self.settings.value("overlay_opacity", 65, type=int))
        self.overlay_opacity_label.setText(f"{self.overlay_opacity.value()}%")

        # Desktop - Panel
        self.weather_location.setText(self.settings.value("weather_location", ""))
        self.show_seconds.setChecked(self.settings.value("show_seconds", False, type=bool))
        self.show_date.setChecked(self.settings.value("show_date", True, type=bool))
        self.desktop_mode.setChecked(self.settings.value("desktop_mode", False, type=bool))
        self.auto_connect.setChecked(self.settings.value("auto_connect", True, type=bool))

        # Autostart - check actual systemd status
        if HAS_AUTOSTART:
            self.autostart_enabled.setChecked(is_autostart_enabled())
            self.autostart_enabled.setEnabled(True)
        else:
            self.autostart_enabled.setChecked(False)
            self.autostart_enabled.setEnabled(False)
            self.autostart_enabled.setToolTip("Autostart not available")

        # File Browser
        self.fb_show_hidden.setChecked(self.settings.value("fb_show_hidden", False, type=bool))
        self.fb_show_size.setChecked(self.settings.value("fb_show_size", True, type=bool))
        self.fb_show_date.setChecked(self.settings.value("fb_show_date", True, type=bool))
        self.fb_sort_folders_first.setChecked(self.settings.value("fb_sort_folders_first", True, type=bool))
        self.fb_color_folder.setColor(self.settings.value("fb_color_folder", "#4fc3f7"))
        self.fb_color_python.setColor(self.settings.value("fb_color_python", "#4caf50"))
        self.fb_color_js.setColor(self.settings.value("fb_color_js", "#ffeb3b"))
        self.fb_color_html.setColor(self.settings.value("fb_color_html", "#ff9800"))
        self.fb_color_image.setColor(self.settings.value("fb_color_image", "#e91e63"))
        self.fb_color_archive.setColor(self.settings.value("fb_color_archive", "#9c27b0"))
        self.fb_color_exec.setColor(self.settings.value("fb_color_exec", "#f44336"))
        self.fb_color_text.setColor(self.settings.value("fb_color_text", "#e0e0e0"))

        # Browser
        self.browser_homepage.setText(self.settings.value("browser_homepage", "https://www.google.com"))
        self.browser_search_engine.setCurrentText(self.settings.value("browser_search_engine", "Google"))
        self.browser_new_tab_url.setText(self.settings.value("browser_new_tab_url", "about:blank"))
        self.browser_open_links_new_tab.setChecked(self.settings.value("browser_open_links_new_tab", False, type=bool))
        self.browser_block_popups.setChecked(self.settings.value("browser_block_popups", True, type=bool))
        self.browser_enable_js.setChecked(self.settings.value("browser_enable_js", True, type=bool))
        self.browser_clear_on_exit.setChecked(self.settings.value("browser_clear_on_exit", False, type=bool))
        self.browser_do_not_track.setChecked(self.settings.value("browser_do_not_track", True, type=bool))
        self.browser_block_third_party_cookies.setChecked(self.settings.value("browser_block_third_party_cookies", False, type=bool))

        # Terminal
        self.term_bg_color.setColor(self.settings.value("term_bg_color", "#1e1e1e"))
        self.term_fg_color.setColor(self.settings.value("term_fg_color", "#e0e0e0"))
        self.term_cursor_color.setColor(self.settings.value("term_cursor_color", "#3b82f6"))
        self.term_selection_color.setColor(self.settings.value("term_selection_color", "#3b82f6"))
        font_family = self.settings.value("term_font_family", "Monospace")
        self.term_font_family.setCurrentFont(QFont(font_family))
        self.term_font_size.setValue(self.settings.value("term_font_size", 12, type=int))
        self.term_scrollback.setValue(self.settings.value("term_scrollback", 10000, type=int))
        self.term_scroll_on_output.setChecked(self.settings.value("term_scroll_on_output", True, type=bool))
        self.term_scroll_on_input.setChecked(self.settings.value("term_scroll_on_input", True, type=bool))
        self.term_bell_enabled.setChecked(self.settings.value("term_bell_enabled", False, type=bool))
        self.term_cursor_blink.setChecked(self.settings.value("term_cursor_blink", True, type=bool))

        # Chat
        self.chat_default_model.setCurrentText(self.settings.value("chat_default_model", "auto"))
        self.chat_temperature.setValue(self.settings.value("chat_temperature", 7, type=int))
        self.chat_temp_label.setText(f"{self.chat_temperature.value()/10:.1f}")
        self.chat_show_timestamps.setChecked(self.settings.value("chat_show_timestamps", False, type=bool))
        self.chat_show_model_name.setChecked(self.settings.value("chat_show_model_name", True, type=bool))
        self.chat_auto_scroll.setChecked(self.settings.value("chat_auto_scroll", True, type=bool))
        self.chat_syntax_highlight.setChecked(self.settings.value("chat_syntax_highlight", True, type=bool))
        self.chat_max_history.setValue(self.settings.value("chat_max_history", 100, type=int))
        self.chat_save_history.setChecked(self.settings.value("chat_save_history", True, type=bool))
        self.chat_clear_on_exit.setChecked(self.settings.value("chat_clear_on_exit", False, type=bool))
        self.chat_max_input_lines.setValue(self.settings.value("chat_max_input_lines", 10, type=int))
        self.chat_send_on_enter.setChecked(self.settings.value("chat_send_on_enter", True, type=bool))

        # Agents
        self.claude_path.setText(self.settings.value("claude_path", ""))
        self.gemini_path.setText(self.settings.value("gemini_path", ""))
        self.codex_path.setText(self.settings.value("codex_path", ""))
        self.opencode_path.setText(self.settings.value("opencode_path", ""))
        self.mcp_enabled.setChecked(self.settings.value("mcp_enabled", True, type=bool))

    def _save_settings(self):
        """Save settings"""
        # Connection
        self.settings.setValue("server_url", self.server_url.text())
        # Removed: user_id save
        # Removed: client_id
        self.settings.setValue("client_secret", self.client_secret.text())

        # Desktop - Background
        self.settings.setValue("desktop_background", self.wallpaper_path.text())
        self.settings.setValue("overlay_opacity", self.overlay_opacity.value())

        # Desktop - Panel
        self.settings.setValue("weather_location", self.weather_location.text())
        self.settings.setValue("show_seconds", self.show_seconds.isChecked())
        self.settings.setValue("show_date", self.show_date.isChecked())
        self.settings.setValue("desktop_mode", self.desktop_mode.isChecked())
        self.settings.setValue("auto_connect", self.auto_connect.isChecked())

        # Autostart - manage systemd service
        if HAS_AUTOSTART:
            current = is_autostart_enabled()
            desired = self.autostart_enabled.isChecked()
            if current != desired:
                if manage_autostart(desired):
                    action = "enabled" if desired else "disabled"
                    logger.info(f"Autostart {action}")
                else:
                    QMessageBox.warning(
                        self, "Warning",
                        f"Failed to {'enable' if desired else 'disable'} autostart"
                    )

        # File Browser
        self.settings.setValue("fb_show_hidden", self.fb_show_hidden.isChecked())
        self.settings.setValue("fb_show_size", self.fb_show_size.isChecked())
        self.settings.setValue("fb_show_date", self.fb_show_date.isChecked())
        self.settings.setValue("fb_sort_folders_first", self.fb_sort_folders_first.isChecked())
        self.settings.setValue("fb_color_folder", self.fb_color_folder.color())
        self.settings.setValue("fb_color_python", self.fb_color_python.color())
        self.settings.setValue("fb_color_js", self.fb_color_js.color())
        self.settings.setValue("fb_color_html", self.fb_color_html.color())
        self.settings.setValue("fb_color_image", self.fb_color_image.color())
        self.settings.setValue("fb_color_archive", self.fb_color_archive.color())
        self.settings.setValue("fb_color_exec", self.fb_color_exec.color())
        self.settings.setValue("fb_color_text", self.fb_color_text.color())

        # Browser
        self.settings.setValue("browser_homepage", self.browser_homepage.text())
        self.settings.setValue("browser_search_engine", self.browser_search_engine.currentText())
        self.settings.setValue("browser_new_tab_url", self.browser_new_tab_url.text())
        self.settings.setValue("browser_open_links_new_tab", self.browser_open_links_new_tab.isChecked())
        self.settings.setValue("browser_block_popups", self.browser_block_popups.isChecked())
        self.settings.setValue("browser_enable_js", self.browser_enable_js.isChecked())
        self.settings.setValue("browser_clear_on_exit", self.browser_clear_on_exit.isChecked())
        self.settings.setValue("browser_do_not_track", self.browser_do_not_track.isChecked())
        self.settings.setValue("browser_block_third_party_cookies", self.browser_block_third_party_cookies.isChecked())

        # Terminal
        self.settings.setValue("term_bg_color", self.term_bg_color.color())
        self.settings.setValue("term_fg_color", self.term_fg_color.color())
        self.settings.setValue("term_cursor_color", self.term_cursor_color.color())
        self.settings.setValue("term_selection_color", self.term_selection_color.color())
        self.settings.setValue("term_font_family", self.term_font_family.currentFont().family())
        self.settings.setValue("term_font_size", self.term_font_size.value())
        self.settings.setValue("term_scrollback", self.term_scrollback.value())
        self.settings.setValue("term_scroll_on_output", self.term_scroll_on_output.isChecked())
        self.settings.setValue("term_scroll_on_input", self.term_scroll_on_input.isChecked())
        self.settings.setValue("term_bell_enabled", self.term_bell_enabled.isChecked())
        self.settings.setValue("term_cursor_blink", self.term_cursor_blink.isChecked())

        # Chat
        self.settings.setValue("chat_default_model", self.chat_default_model.currentText())
        self.settings.setValue("chat_temperature", self.chat_temperature.value())
        self.settings.setValue("chat_show_timestamps", self.chat_show_timestamps.isChecked())
        self.settings.setValue("chat_show_model_name", self.chat_show_model_name.isChecked())
        self.settings.setValue("chat_auto_scroll", self.chat_auto_scroll.isChecked())
        self.settings.setValue("chat_syntax_highlight", self.chat_syntax_highlight.isChecked())
        self.settings.setValue("chat_max_history", self.chat_max_history.value())
        self.settings.setValue("chat_save_history", self.chat_save_history.isChecked())
        self.settings.setValue("chat_clear_on_exit", self.chat_clear_on_exit.isChecked())
        self.settings.setValue("chat_max_input_lines", self.chat_max_input_lines.value())
        self.settings.setValue("chat_send_on_enter", self.chat_send_on_enter.isChecked())

        # Agents
        self.settings.setValue("claude_path", self.claude_path.text())
        self.settings.setValue("gemini_path", self.gemini_path.text())
        self.settings.setValue("codex_path", self.codex_path.text())
        self.settings.setValue("opencode_path", self.opencode_path.text())
        self.settings.setValue("mcp_enabled", self.mcp_enabled.isChecked())

        # Update API client
        self.api_client.base_url = self.server_url.text()
        self.api_client.user_id = self.user_id.text()

        # Emit signal to notify components
        self.settings_changed.emit()

        self.accept()

    def _show_clear_browser_data_dialog(self):
        """Show dialog to clear browser data"""
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QCheckBox, QDialogButtonBox, QLabel

        dialog = QDialog(self)
        dialog.setWindowTitle(tr("Clear Browser Data"))
        dialog.setMinimumWidth(350)
        layout = QVBoxLayout(dialog)

        # Warning label
        warning = QLabel(tr("Select which data to clear:"))
        warning.setStyleSheet("font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(warning)

        # Checkboxes
        clear_cookies = QCheckBox(tr("Cookies (will log you out of websites)"))
        clear_cookies.setChecked(True)
        layout.addWidget(clear_cookies)

        clear_cache = QCheckBox(tr("Cache (temporary files, images)"))
        clear_cache.setChecked(True)
        layout.addWidget(clear_cache)

        clear_history = QCheckBox(tr("Browsing history"))
        clear_history.setChecked(False)
        layout.addWidget(clear_history)

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            # Clear browser data
            from PyQt6.QtWebEngineCore import QWebEngineProfile
            import shutil
            from pathlib import Path

            profile = QWebEngineProfile.defaultProfile()
            browser_path = Path.home() / ".config" / "ailinux" / "browser"

            try:
                if clear_cache.isChecked():
                    # Clear cache directory
                    cache_path = browser_path / "cache"
                    if cache_path.exists():
                        shutil.rmtree(cache_path)
                        cache_path.mkdir(parents=True, exist_ok=True)
                    # Clear WebEngine cache
                    profile.clearHttpCache()

                if clear_cookies.isChecked():
                    # Clear WebEngine cookies
                    profile.cookieStore().deleteAllCookies()
                    # Also delete persistent cookie storage files
                    cookies_db = browser_path / "Cookies"
                    cookies_journal = browser_path / "Cookies-journal"
                    for f in [cookies_db, cookies_journal]:
                        if f.exists():
                            f.unlink()
                    # Clear Local Storage and Session Storage
                    for subdir in ["Local Storage", "Session Storage", "IndexedDB"]:
                        storage_path = browser_path / subdir
                        if storage_path.exists():
                            shutil.rmtree(storage_path)

                if clear_history.isChecked():
                    profile.clearAllVisitedLinks()
                    # Clear visited links database
                    visited_db = browser_path / "Visited Links"
                    if visited_db.exists():
                        visited_db.unlink()

                QMessageBox.information(
                    self,
                    tr("Success"),
                    tr("Browser data cleared successfully.")
                )
            except Exception as e:
                QMessageBox.warning(
                    self,
                    tr("Error"),
                    f"{tr('Failed to clear browser data')}: {e}"
                )

    def _reset_to_defaults(self):
        """Reset all settings to defaults"""
        reply = QMessageBox.question(
            self, tr("Reset Settings"),
            tr("Reset all settings to default values?"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.settings.clear()
            self._load_settings()
            QMessageBox.information(self, tr("Reset"), tr("Settings reset to defaults."))

    def _test_connection(self):
        """Test server connection"""
        try:
            # Update API client
            self.api_client.base_url = self.server_url.text()

            # Test auth
            if self.client_id.text() and self.client_secret.text():
                result = self.api_client.get_auth_token(
                    self.client_id.text(),
                    self.client_secret.text()
                )
                if result:
                    QMessageBox.information(
                        self, "Success",
                        f"Connected!\nTier: {result.get('tier', 'unknown')}"
                    )
                    return

            # Test basic connection
            tier_info = self.api_client.get_tier_info()
            QMessageBox.information(
                self, "Success",
                f"Server reachable!\nTier: {tier_info.get('tier', 'unknown')}"
            )

        except Exception as e:
            QMessageBox.warning(self, "Error", f"Connection failed:\n{e}")
