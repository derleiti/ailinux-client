"""
AILinux Client - Theme Manager
==============================

Manages custom themes/skins with:
- Import/export theme files (.ailinux-theme)
- Embedded wallpapers (base64)
- Color schemes
- Widget styling
- Community theme sharing
"""
import json
import base64
import os
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, asdict, field
from datetime import datetime

logger = logging.getLogger("ailinux.theme_manager")


@dataclass
class ThemeColors:
    """Color scheme for a theme"""
    primary: str = "#3b82f6"           # Blue accent
    secondary: str = "#6366f1"          # Indigo
    accent: str = "#8b5cf6"             # Purple
    background: str = "#0a0a1a"         # Dark background
    surface: str = "#1a1a2e"            # Surface/card background
    text_primary: str = "#e0e0e0"       # Primary text
    text_secondary: str = "#a0a0a0"     # Secondary text
    border: str = "rgba(255,255,255,0.1)"
    success: str = "#4ade80"            # Green
    warning: str = "#fbbf24"            # Yellow
    error: str = "#ef4444"              # Red


@dataclass
class ThemeWidgets:
    """Widget styling settings"""
    border_radius: int = 10             # Border radius in px
    transparency: float = 0.85          # Widget background transparency
    blur_enabled: bool = True           # Enable blur effect (if supported)
    shadow_enabled: bool = True         # Enable drop shadows
    animation_speed: str = "normal"     # slow, normal, fast


@dataclass
class ThemeFont:
    """Font settings"""
    family: str = "Segoe UI, Ubuntu, sans-serif"
    size_base: int = 13
    size_small: int = 11
    size_large: int = 16
    monospace: str = "JetBrains Mono, Fira Code, monospace"


@dataclass
class ThemeOverlay:
    """Overlay settings for wallpaper contrast"""
    enabled: bool = True
    color: str = "10, 10, 20"           # RGB values
    opacity: float = 0.65               # 0.0 - 1.0


@dataclass
class ThemeMetadata:
    """Theme metadata"""
    name: str = "Default"
    author: str = "AILinux"
    version: str = "1.0.0"
    description: str = "Default AILinux theme"
    created: str = ""
    tags: List[str] = field(default_factory=list)
    preview_url: str = ""               # URL to preview image


@dataclass
class Theme:
    """Complete theme definition"""
    metadata: ThemeMetadata = field(default_factory=ThemeMetadata)
    colors: ThemeColors = field(default_factory=ThemeColors)
    widgets: ThemeWidgets = field(default_factory=ThemeWidgets)
    font: ThemeFont = field(default_factory=ThemeFont)
    overlay: ThemeOverlay = field(default_factory=ThemeOverlay)

    # Wallpaper can be base64 encoded or a path/URL
    wallpaper_data: str = ""            # Base64 encoded image
    wallpaper_path: str = ""            # Local path or URL
    wallpaper_mode: str = "cover"       # cover, contain, tile, center

    # Custom CSS overrides (advanced users)
    custom_css: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert theme to dictionary"""
        return {
            "metadata": asdict(self.metadata),
            "colors": asdict(self.colors),
            "widgets": asdict(self.widgets),
            "font": asdict(self.font),
            "overlay": asdict(self.overlay),
            "wallpaper_data": self.wallpaper_data,
            "wallpaper_path": self.wallpaper_path,
            "wallpaper_mode": self.wallpaper_mode,
            "custom_css": self.custom_css,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Theme":
        """Create theme from dictionary"""
        theme = cls()

        if "metadata" in data:
            theme.metadata = ThemeMetadata(**data["metadata"])
        if "colors" in data:
            theme.colors = ThemeColors(**data["colors"])
        if "widgets" in data:
            theme.widgets = ThemeWidgets(**data["widgets"])
        if "font" in data:
            theme.font = ThemeFont(**data["font"])
        if "overlay" in data:
            theme.overlay = ThemeOverlay(**data["overlay"])

        theme.wallpaper_data = data.get("wallpaper_data", "")
        theme.wallpaper_path = data.get("wallpaper_path", "")
        theme.wallpaper_mode = data.get("wallpaper_mode", "cover")
        theme.custom_css = data.get("custom_css", "")

        return theme


class ThemeManager:
    """
    Manages themes for AILinux Client.

    Themes are stored in ~/.config/ailinux/themes/
    Theme files use .ailinux-theme extension (JSON format)
    """

    THEME_EXTENSION = ".ailinux-theme"
    THEME_DIR = Path.home() / ".config" / "ailinux" / "themes"
    WALLPAPER_CACHE_DIR = Path.home() / ".config" / "ailinux" / "wallpapers"

    def __init__(self):
        self._ensure_dirs()
        self._current_theme: Optional[Theme] = None
        self._installed_themes: Dict[str, Theme] = {}
        self._load_installed_themes()

    def _ensure_dirs(self):
        """Ensure theme directories exist"""
        self.THEME_DIR.mkdir(parents=True, exist_ok=True)
        self.WALLPAPER_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    def _load_installed_themes(self):
        """Load all installed themes from theme directory"""
        self._installed_themes = {}

        for theme_file in self.THEME_DIR.glob(f"*{self.THEME_EXTENSION}"):
            try:
                theme = self.load_theme(theme_file)
                if theme:
                    self._installed_themes[theme.metadata.name] = theme
            except Exception as e:
                logger.error(f"Failed to load theme {theme_file}: {e}")

        logger.info(f"Loaded {len(self._installed_themes)} installed themes")

    def get_installed_themes(self) -> List[Theme]:
        """Get list of installed themes"""
        return list(self._installed_themes.values())

    def get_theme_names(self) -> List[str]:
        """Get list of installed theme names"""
        return list(self._installed_themes.keys())

    def get_theme(self, name: str) -> Optional[Theme]:
        """Get theme by name"""
        return self._installed_themes.get(name)

    def load_theme(self, path: Path) -> Optional[Theme]:
        """Load theme from file"""
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)

            theme = Theme.from_dict(data)
            logger.info(f"Loaded theme: {theme.metadata.name}")
            return theme

        except Exception as e:
            logger.error(f"Failed to load theme from {path}: {e}")
            return None

    def save_theme(self, theme: Theme, path: Optional[Path] = None) -> bool:
        """Save theme to file"""
        try:
            if path is None:
                # Save to themes directory with sanitized name
                safe_name = "".join(c for c in theme.metadata.name if c.isalnum() or c in "._- ")
                path = self.THEME_DIR / f"{safe_name}{self.THEME_EXTENSION}"

            # Update created timestamp if not set
            if not theme.metadata.created:
                theme.metadata.created = datetime.now().isoformat()

            with open(path, "w", encoding="utf-8") as f:
                json.dump(theme.to_dict(), f, indent=2, ensure_ascii=False)

            # Add to installed themes
            self._installed_themes[theme.metadata.name] = theme

            logger.info(f"Saved theme: {theme.metadata.name} to {path}")
            return True

        except Exception as e:
            logger.error(f"Failed to save theme: {e}")
            return False

    def import_theme(self, file_path: str) -> Optional[Theme]:
        """Import theme from external file"""
        path = Path(file_path)

        if not path.exists():
            logger.error(f"Theme file not found: {file_path}")
            return None

        theme = self.load_theme(path)
        if theme:
            # Extract embedded wallpaper if present
            if theme.wallpaper_data:
                wallpaper_path = self._extract_wallpaper(theme)
                if wallpaper_path:
                    theme.wallpaper_path = str(wallpaper_path)

            # Save to local themes directory
            self.save_theme(theme)

        return theme

    def export_theme(self, theme: Theme, export_path: str, embed_wallpaper: bool = True) -> bool:
        """Export theme to file, optionally embedding wallpaper"""
        try:
            export_theme = Theme.from_dict(theme.to_dict())  # Copy

            # Embed wallpaper as base64 if requested
            if embed_wallpaper and theme.wallpaper_path and os.path.exists(theme.wallpaper_path):
                with open(theme.wallpaper_path, "rb") as f:
                    image_data = f.read()
                export_theme.wallpaper_data = base64.b64encode(image_data).decode("utf-8")
                export_theme.wallpaper_path = ""  # Clear path since we embedded it

            with open(export_path, "w", encoding="utf-8") as f:
                json.dump(export_theme.to_dict(), f, indent=2, ensure_ascii=False)

            logger.info(f"Exported theme to {export_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to export theme: {e}")
            return False

    def _extract_wallpaper(self, theme: Theme) -> Optional[Path]:
        """Extract embedded wallpaper to cache directory"""
        if not theme.wallpaper_data:
            return None

        try:
            # Decode base64 wallpaper
            image_data = base64.b64decode(theme.wallpaper_data)

            # Determine extension from data (simple magic byte check)
            ext = ".jpg"
            if image_data[:8] == b'\x89PNG\r\n\x1a\n':
                ext = ".png"
            elif image_data[:4] == b'RIFF' and image_data[8:12] == b'WEBP':
                ext = ".webp"

            # Save to cache
            safe_name = "".join(c for c in theme.metadata.name if c.isalnum() or c in "._- ")
            wallpaper_path = self.WALLPAPER_CACHE_DIR / f"{safe_name}_wallpaper{ext}"

            with open(wallpaper_path, "wb") as f:
                f.write(image_data)

            logger.info(f"Extracted wallpaper to {wallpaper_path}")
            return wallpaper_path

        except Exception as e:
            logger.error(f"Failed to extract wallpaper: {e}")
            return None

    def delete_theme(self, name: str) -> bool:
        """Delete an installed theme"""
        if name not in self._installed_themes:
            return False

        try:
            # Find and delete theme file
            safe_name = "".join(c for c in name if c.isalnum() or c in "._- ")
            theme_path = self.THEME_DIR / f"{safe_name}{self.THEME_EXTENSION}"

            if theme_path.exists():
                theme_path.unlink()

            del self._installed_themes[name]
            logger.info(f"Deleted theme: {name}")
            return True

        except Exception as e:
            logger.error(f"Failed to delete theme {name}: {e}")
            return False

    def create_theme_from_settings(self, settings, name: str, author: str = "",
                                   description: str = "") -> Theme:
        """Create a theme from current QSettings"""
        theme = Theme()

        # Metadata
        theme.metadata.name = name
        theme.metadata.author = author or "User"
        theme.metadata.description = description
        theme.metadata.created = datetime.now().isoformat()

        # Wallpaper
        theme.wallpaper_path = settings.value("desktop_background", "")

        # Overlay
        theme.overlay.opacity = settings.value("overlay_opacity", 65, type=int) / 100.0

        # Colors from settings (with defaults)
        theme.colors.primary = settings.value("theme_color_primary", "#3b82f6")
        theme.colors.background = settings.value("theme_color_background", "#0a0a1a")
        theme.colors.text_primary = settings.value("theme_color_text", "#e0e0e0")

        # Widget settings
        theme.widgets.border_radius = settings.value("widget_border_radius", 10, type=int)
        theme.widgets.transparency = settings.value("widget_transparency", 85, type=int) / 100.0

        # Font settings
        theme.font.family = settings.value("font_family", "Segoe UI, Ubuntu, sans-serif")
        theme.font.size_base = settings.value("font_size", 13, type=int)
        theme.font.monospace = settings.value("terminal/font_family", "JetBrains Mono, monospace")

        return theme

    def apply_theme_to_settings(self, theme: Theme, settings) -> None:
        """Apply theme to QSettings"""
        # Wallpaper
        if theme.wallpaper_path:
            settings.setValue("desktop_background", theme.wallpaper_path)

        # Overlay
        settings.setValue("overlay_opacity", int(theme.overlay.opacity * 100))

        # All Colors
        settings.setValue("theme_color_primary", theme.colors.primary)
        settings.setValue("theme_color_secondary", theme.colors.secondary)
        settings.setValue("theme_color_accent", theme.colors.accent)
        settings.setValue("theme_color_background", theme.colors.background)
        settings.setValue("theme_color_surface", theme.colors.surface)
        settings.setValue("theme_color_text", theme.colors.text_primary)
        settings.setValue("theme_color_text_secondary", theme.colors.text_secondary)
        settings.setValue("theme_color_border", theme.colors.border)
        settings.setValue("theme_color_success", theme.colors.success)
        settings.setValue("theme_color_warning", theme.colors.warning)
        settings.setValue("theme_color_error", theme.colors.error)

        # Widget settings
        settings.setValue("widget_border_radius", theme.widgets.border_radius)
        settings.setValue("widget_transparency", int(theme.widgets.transparency * 100))
        settings.setValue("widget_blur_enabled", theme.widgets.blur_enabled)
        settings.setValue("widget_shadow_enabled", theme.widgets.shadow_enabled)

        # Font settings
        settings.setValue("font_family", theme.font.family)
        settings.setValue("font_size", theme.font.size_base)
        settings.setValue("terminal/font_family", theme.font.monospace)

        # Save current theme name
        settings.setValue("current_theme", theme.metadata.name)

        settings.sync()
        logger.info(f"Applied theme: {theme.metadata.name}")

    def generate_stylesheet(self, theme: Theme) -> str:
        """Generate Qt stylesheet from theme"""
        c = theme.colors
        w = theme.widgets
        f = theme.font
        o = theme.overlay

        # Calculate overlay background
        overlay_bg = f"rgba({o.color}, {o.opacity:.2f})" if o.enabled else "transparent"

        # Widget transparency
        widget_alpha = int(w.transparency * 255)
        surface_rgba = self._hex_to_rgba(c.surface, w.transparency)

        stylesheet = f"""
        /* AILinux Theme: {theme.metadata.name} */

        QMainWindow {{
            background: {c.background};
        }}

        QWidget#centralWidget {{
            background: {overlay_bg};
        }}

        /* Menus */
        QMenuBar {{
            background: rgba(20, 20, 30, 0.9);
            color: {c.text_secondary};
            border-bottom: 1px solid {c.border};
        }}
        QMenuBar::item:selected {{
            background: {c.primary};
            color: white;
        }}
        QMenu {{
            background: {surface_rgba};
            color: {c.text_primary};
            border: 1px solid {c.border};
            border-radius: {w.border_radius}px;
        }}
        QMenu::item:selected {{
            background: {c.primary};
        }}

        /* Toolbar */
        QToolBar {{
            background: rgba(20, 20, 30, 0.85);
            border: none;
            spacing: 6px;
            padding: 6px;
        }}

        /* Buttons */
        QPushButton {{
            background: rgba(255, 255, 255, 0.08);
            color: {c.text_secondary};
            border: 1px solid {c.border};
            border-radius: {w.border_radius - 4}px;
            padding: 8px 16px;
            font-size: {f.size_base}px;
        }}
        QPushButton:hover {{
            background: {c.primary};
            color: white;
        }}
        QPushButton:pressed {{
            background: {c.secondary};
        }}

        /* Input fields */
        QLineEdit, QTextEdit, QPlainTextEdit {{
            background: {surface_rgba};
            color: {c.text_primary};
            border: 1px solid {c.border};
            border-radius: {w.border_radius - 2}px;
            padding: 8px;
            font-size: {f.size_base}px;
        }}
        QLineEdit:focus, QTextEdit:focus {{
            border-color: {c.primary};
        }}

        /* Scroll bars */
        QScrollBar:vertical {{
            background: transparent;
            width: 10px;
            border-radius: 5px;
        }}
        QScrollBar::handle:vertical {{
            background: rgba(255, 255, 255, 0.2);
            border-radius: 5px;
            min-height: 30px;
        }}
        QScrollBar::handle:vertical:hover {{
            background: {c.primary};
        }}

        /* Status bar */
        QStatusBar {{
            background: rgba(15, 15, 25, 0.9);
            color: {c.text_secondary};
            border-top: 1px solid {c.border};
        }}

        /* Splitter */
        QSplitter::handle {{
            background: {c.border};
        }}
        QSplitter::handle:hover {{
            background: {c.primary};
        }}

        /* Tree/List views */
        QTreeView, QListView {{
            background: {surface_rgba};
            color: {c.text_primary};
            border: none;
            border-radius: {w.border_radius}px;
        }}
        QTreeView::item:hover, QListView::item:hover {{
            background: rgba(255, 255, 255, 0.08);
        }}
        QTreeView::item:selected, QListView::item:selected {{
            background: {c.primary};
        }}

        /* Tab widget */
        QTabWidget::pane {{
            background: {surface_rgba};
            border-radius: {w.border_radius}px;
        }}
        QTabBar::tab {{
            background: rgba(255, 255, 255, 0.05);
            color: {c.text_secondary};
            padding: 8px 16px;
            border-top-left-radius: {w.border_radius - 2}px;
            border-top-right-radius: {w.border_radius - 2}px;
        }}
        QTabBar::tab:selected {{
            background: {c.primary};
            color: white;
        }}

        /* Custom CSS */
        {theme.custom_css}
        """

        return stylesheet

    def _hex_to_rgba(self, hex_color: str, alpha: float) -> str:
        """Convert hex color to rgba string"""
        hex_color = hex_color.lstrip("#")
        if len(hex_color) == 6:
            r = int(hex_color[0:2], 16)
            g = int(hex_color[2:4], 16)
            b = int(hex_color[4:6], 16)
            return f"rgba({r}, {g}, {b}, {alpha:.2f})"
        return hex_color


# Built-in themes
BUILTIN_THEMES = {
    "Dark Space": Theme(
        metadata=ThemeMetadata(
            name="Dark Space",
            author="AILinux",
            description="Deep space dark theme with blue accents",
            tags=["dark", "space", "blue"]
        ),
        colors=ThemeColors(
            primary="#3b82f6",
            secondary="#6366f1",
            background="#0a0a1a",
            surface="#1a1a2e",
        ),
        overlay=ThemeOverlay(opacity=0.65),
    ),

    "Cyberpunk": Theme(
        metadata=ThemeMetadata(
            name="Cyberpunk",
            author="AILinux",
            description="Neon cyberpunk theme with pink and cyan",
            tags=["dark", "neon", "cyberpunk"]
        ),
        colors=ThemeColors(
            primary="#ec4899",
            secondary="#06b6d4",
            accent="#a855f7",
            background="#0f0f1a",
            surface="#1a1a2e",
            text_primary="#f0f0f0",
        ),
        overlay=ThemeOverlay(color="15, 5, 20", opacity=0.70),
    ),

    "Forest": Theme(
        metadata=ThemeMetadata(
            name="Forest",
            author="AILinux",
            description="Natural green forest theme",
            tags=["dark", "green", "nature"]
        ),
        colors=ThemeColors(
            primary="#22c55e",
            secondary="#14b8a6",
            accent="#84cc16",
            background="#0a1a0f",
            surface="#1a2e1f",
            text_primary="#d0e0d0",
        ),
        overlay=ThemeOverlay(color="5, 15, 10", opacity=0.60),
    ),

    "Sunset": Theme(
        metadata=ThemeMetadata(
            name="Sunset",
            author="AILinux",
            description="Warm sunset theme with orange and red",
            tags=["dark", "warm", "sunset"]
        ),
        colors=ThemeColors(
            primary="#f97316",
            secondary="#ef4444",
            accent="#eab308",
            background="#1a0f0a",
            surface="#2e1a1a",
            text_primary="#f0e0d0",
        ),
        overlay=ThemeOverlay(color="20, 10, 5", opacity=0.60),
    ),

    "Ocean": Theme(
        metadata=ThemeMetadata(
            name="Ocean",
            author="AILinux",
            description="Deep ocean blue theme",
            tags=["dark", "blue", "ocean"]
        ),
        colors=ThemeColors(
            primary="#0ea5e9",
            secondary="#06b6d4",
            accent="#3b82f6",
            background="#0a0f1a",
            surface="#1a2030",
            text_primary="#d0e0f0",
        ),
        overlay=ThemeOverlay(color="5, 10, 20", opacity=0.65),
    ),
}


def get_theme_manager() -> ThemeManager:
    """Get singleton theme manager instance"""
    if not hasattr(get_theme_manager, "_instance"):
        get_theme_manager._instance = ThemeManager()

        # Install built-in themes if not present
        for name, theme in BUILTIN_THEMES.items():
            if name not in get_theme_manager._instance._installed_themes:
                get_theme_manager._instance.save_theme(theme)

    return get_theme_manager._instance
