"""
AILinux File Browser
====================

Simple file browser with tree view and customizable colors.
Includes typical file manager shortcuts (F2=rename, F5=copy, F6=move, F7=mkdir, F8=delete)
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTreeView,
    QLineEdit, QPushButton, QMenu,
    QToolButton, QInputDialog, QMessageBox,
    QStyledItemDelegate, QStyleOptionViewItem, QFileDialog
)
from PyQt6.QtCore import Qt, QDir, pyqtSignal, QModelIndex, QSettings, QEvent, QUrl
from PyQt6.QtGui import QAction, QFileSystemModel, QColor, QPainter, QPalette, QKeyEvent, QDesktopServices
import os
import shutil
import subprocess
import logging
from pathlib import Path

# Key capture utilities
try:
    from ..core.shortcut_manager import ShortcutContext, get_shortcut_manager
    from ..core.key_capture import KeyCaptureMixin
    HAS_KEY_CAPTURE = True
except ImportError:
    HAS_KEY_CAPTURE = False
    ShortcutContext = None
    KeyCaptureMixin = object

logger = logging.getLogger("ailinux.file_browser")


class FileColorDelegate(QStyledItemDelegate):
    """
    Custom delegate to color files based on type
    """

    def __init__(self, model: QFileSystemModel, parent=None):
        super().__init__(parent)
        self.model = model
        self.settings = QSettings("AILinux", "Client")
        self._load_colors()

    def _load_colors(self):
        """Load colors from settings"""
        self.colors = {
            'folder': self.settings.value("fb_color_folder", "#4fc3f7"),
            'python': self.settings.value("fb_color_python", "#4caf50"),
            'js': self.settings.value("fb_color_js", "#ffeb3b"),
            'html': self.settings.value("fb_color_html", "#ff9800"),
            'image': self.settings.value("fb_color_image", "#e91e63"),
            'archive': self.settings.value("fb_color_archive", "#9c27b0"),
            'exec': self.settings.value("fb_color_exec", "#f44336"),
            'text': self.settings.value("fb_color_text", "#e0e0e0"),
        }

        # File extension mapping
        self.ext_map = {
            # Python
            '.py': 'python', '.pyw': 'python', '.pyi': 'python',
            # JavaScript/TypeScript
            '.js': 'js', '.jsx': 'js', '.ts': 'js', '.tsx': 'js',
            '.mjs': 'js', '.cjs': 'js', '.vue': 'js', '.svelte': 'js',
            # HTML/CSS
            '.html': 'html', '.htm': 'html', '.css': 'html',
            '.scss': 'html', '.sass': 'html', '.less': 'html',
            '.xml': 'html', '.svg': 'html',
            # Images
            '.png': 'image', '.jpg': 'image', '.jpeg': 'image',
            '.gif': 'image', '.bmp': 'image', '.ico': 'image',
            '.webp': 'image', '.tiff': 'image', '.psd': 'image',
            # Archives
            '.zip': 'archive', '.tar': 'archive', '.gz': 'archive',
            '.bz2': 'archive', '.xz': 'archive', '.7z': 'archive',
            '.rar': 'archive', '.deb': 'archive', '.rpm': 'archive',
            # Executables
            '.exe': 'exec', '.msi': 'exec', '.app': 'exec',
            '.sh': 'exec', '.bash': 'exec', '.zsh': 'exec',
            '.bat': 'exec', '.cmd': 'exec', '.ps1': 'exec',
            '.AppImage': 'exec', '.run': 'exec',
        }

    def reload_colors(self):
        """Reload colors from settings"""
        self._load_colors()

    def _get_file_color(self, index: QModelIndex) -> str:
        """Get color for file based on type"""
        path = self.model.filePath(index)

        # Folder
        if self.model.isDir(index):
            return self.colors['folder']

        # Check extension
        ext = Path(path).suffix.lower()
        if ext in self.ext_map:
            return self.colors[self.ext_map[ext]]

        # Check if executable (Unix)
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return self.colors['exec']

        # Default text color
        return self.colors['text']

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        """Custom paint with file type colors"""
        # Only color the name column (column 0)
        if index.column() == 0:
            color = self._get_file_color(index)
            # Create a modified option with custom color
            opt = QStyleOptionViewItem(option)
            opt.palette.setColor(QPalette.ColorRole.Text, QColor(color))
            opt.palette.setColor(QPalette.ColorRole.HighlightedText, QColor(color))
            super().paint(painter, opt, index)
        else:
            super().paint(painter, option, index)


class FileBrowser(QWidget, KeyCaptureMixin):
    """
    File browser widget with typical file manager shortcuts.

    Features:
    - Tree view of filesystem
    - Navigation (back, up, home)
    - Path bar
    - Context menu with Cut/Copy/Paste
    - Customizable file type colors
    - File manager shortcuts (F2, F5-F8, Delete, etc.)

    Shortcuts:
    - F2: Rename selected item
    - F5: Copy selected item (to clipboard)
    - F6: Move selected item (cut to clipboard)
    - F7: Create new folder
    - F8 / Delete: Delete selected item
    - Ctrl+C: Copy
    - Ctrl+X: Cut
    - Ctrl+V: Paste
    - Ctrl+N: New file
    - Ctrl+Shift+N: New folder
    - Backspace: Go up one directory
    - Enter: Open selected item
    """

    file_selected = pyqtSignal(str)  # Full path
    directory_changed = pyqtSignal(str)
    open_terminal_requested = pyqtSignal(str)  # Request to open terminal at path

    # Class-level clipboard (shared across all instances)
    _clipboard_path: str = None
    _clipboard_is_cut: bool = False

    def __init__(self, parent=None):
        super().__init__(parent)
        self.settings = QSettings("AILinux", "Client")
        self.current_path = str(Path.home())
        self.history: list = []
        self.history_index = -1

        self._setup_ui()
        self._setup_key_bindings()
        self._navigate_to(self.current_path)

    def _setup_key_bindings(self):
        """Setup file manager keyboard shortcuts"""
        if HAS_KEY_CAPTURE:
            self.init_key_capture(ShortcutContext.FILE_BROWSER, capture_all=False)

            # F2: Rename
            self.bind_key(Qt.Key.Key_F2, self._rename_selected, "Rename (F2)")

            # Note: F5 is global lock screen, use Ctrl+C for copy

            # F6: Move (cut to clipboard)
            self.bind_key(Qt.Key.Key_F6, self._cut_selected, "Move/Cut (F6)")

            # F7: New folder
            self.bind_key(Qt.Key.Key_F7, self._new_folder, "New Folder (F7)")

            # F8: Delete
            self.bind_key(Qt.Key.Key_F8, self._delete_selected, "Delete (F8)")

            # Delete key: Delete
            self.bind_key(Qt.Key.Key_Delete, self._delete_selected, "Delete")

            # Backspace: Go up
            self.bind_key(Qt.Key.Key_Backspace, self._go_up, "Go Up")

            # Enter: Open selected
            self.bind_key(Qt.Key.Key_Return, self._open_selected, "Open")
            self.bind_key(Qt.Key.Key_Enter, self._open_selected, "Open")

            # Ctrl+C: Copy
            self.bind_key(Qt.Key.Key_C, self._copy_selected, "Copy",
                         Qt.KeyboardModifier.ControlModifier)

            # Ctrl+X: Cut
            self.bind_key(Qt.Key.Key_X, self._cut_selected, "Cut",
                         Qt.KeyboardModifier.ControlModifier)

            # Ctrl+V: Paste
            self.bind_key(Qt.Key.Key_V, self._paste, "Paste",
                         Qt.KeyboardModifier.ControlModifier)

            # Ctrl+N: New file
            self.bind_key(Qt.Key.Key_N, self._new_file, "New File",
                         Qt.KeyboardModifier.ControlModifier)

            # Ctrl+Shift+N: New folder
            self.bind_key(Qt.Key.Key_N, self._new_folder, "New Folder",
                         Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)

            # Ctrl+A: Select all
            self.bind_key(Qt.Key.Key_A, self._select_all, "Select All",
                         Qt.KeyboardModifier.ControlModifier)

            # Ctrl+H: Toggle hidden files
            self.bind_key(Qt.Key.Key_H, self._toggle_hidden, "Toggle Hidden",
                         Qt.KeyboardModifier.ControlModifier)

            # Ctrl+R / F5 alternative: Refresh
            self.bind_key(Qt.Key.Key_R, self._refresh, "Refresh",
                         Qt.KeyboardModifier.ControlModifier)

            # Alt+Home: Go home
            self.bind_key(Qt.Key.Key_Home, self._go_home, "Go Home",
                         Qt.KeyboardModifier.AltModifier)

            # Alt+Up: Go up
            self.bind_key(Qt.Key.Key_Up, self._go_up, "Go Up",
                         Qt.KeyboardModifier.AltModifier)

            # Alt+Left: Go back
            self.bind_key(Qt.Key.Key_Left, self._go_back, "Go Back",
                         Qt.KeyboardModifier.AltModifier)

    def keyPressEvent(self, event: QKeyEvent):
        """Handle keyboard input"""
        if HAS_KEY_CAPTURE and hasattr(self, '_key_bindings'):
            if self.handle_key_press(event):
                return
        super().keyPressEvent(event)

    def _get_selected_path(self) -> str:
        """Get currently selected path or current directory"""
        indexes = self.tree.selectedIndexes()
        if indexes:
            return self.model.filePath(indexes[0])
        return self.current_path

    def _rename_selected(self):
        """Rename selected item"""
        path = self._get_selected_path()
        if path and path != self.current_path:
            self._rename(path)

    def _copy_selected(self):
        """Copy selected item to clipboard"""
        path = self._get_selected_path()
        if path and path != self.current_path:
            self._copy(path)

    def _cut_selected(self):
        """Cut selected item to clipboard"""
        path = self._get_selected_path()
        if path and path != self.current_path:
            self._cut(path)

    def _delete_selected(self):
        """Delete selected item"""
        path = self._get_selected_path()
        if path and path != self.current_path:
            self._delete(path)

    def _open_selected(self):
        """Open selected item (navigate to dir or emit file_selected)"""
        indexes = self.tree.selectedIndexes()
        if indexes:
            index = indexes[0]
            self._on_double_click(index)

    def _select_all(self):
        """Select all items in current directory"""
        self.tree.selectAll()

    def _open_with_system(self, path: str):
        """Open file with system default application"""
        if not os.path.exists(path):
            return False

        try:
            # Try Qt's QDesktopServices first (cross-platform)
            url = QUrl.fromLocalFile(path)
            if QDesktopServices.openUrl(url):
                logger.info(f"Opened with system: {path}")
                return True

            # Fallback to platform-specific commands
            import platform
            system = platform.system()

            if system == "Linux":
                subprocess.Popen(["xdg-open", path], start_new_session=True)
            elif system == "Darwin":  # macOS
                subprocess.Popen(["open", path])
            elif system == "Windows":
                os.startfile(path)
            else:
                logger.warning(f"Unknown platform: {system}")
                return False

            logger.info(f"Opened with system fallback: {path}")
            return True

        except Exception as e:
            logger.error(f"Failed to open with system: {e}")
            QMessageBox.warning(self, "Error", f"Could not open file: {e}")
            return False

    def _open_with_application(self, path: str, app: str = None):
        """Open file with specific application"""
        if not os.path.exists(path):
            return False

        try:
            if app:
                subprocess.Popen([app, path], start_new_session=True)
            else:
                self._open_with_system(path)
            return True
        except Exception as e:
            logger.error(f"Failed to open with {app}: {e}")
            return False

    def _setup_ui(self):
        """Setup UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Toolbar
        toolbar = QWidget()
        toolbar.setStyleSheet("""
            background: rgba(30, 30, 30, 0.85);
            border-radius: 8px;
            padding: 4px;
            margin: 4px;
        """)
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(4, 4, 4, 4)
        toolbar_layout.setSpacing(4)

        # Back button
        self.back_btn = QToolButton()
        self.back_btn.setText("←")
        self.back_btn.setStyleSheet(self._btn_style())
        self.back_btn.clicked.connect(self._go_back)
        toolbar_layout.addWidget(self.back_btn)

        # Up button
        self.up_btn = QToolButton()
        self.up_btn.setText("↑")
        self.up_btn.setStyleSheet(self._btn_style())
        self.up_btn.clicked.connect(self._go_up)
        toolbar_layout.addWidget(self.up_btn)

        # Home button
        self.home_btn = QToolButton()
        self.home_btn.setText("⌂")
        self.home_btn.setStyleSheet(self._btn_style())
        self.home_btn.clicked.connect(self._go_home)
        toolbar_layout.addWidget(self.home_btn)

        # Refresh button
        self.refresh_btn = QToolButton()
        self.refresh_btn.setText("↻")
        self.refresh_btn.setStyleSheet(self._btn_style())
        self.refresh_btn.clicked.connect(self._refresh)
        toolbar_layout.addWidget(self.refresh_btn)

        # Hidden files toggle
        self.hidden_btn = QToolButton()
        self.hidden_btn.setText("👁")
        self.hidden_btn.setCheckable(True)
        self.hidden_btn.setChecked(self.settings.value("fb_show_hidden", False, type=bool))
        self.hidden_btn.setStyleSheet(self._btn_style())
        self.hidden_btn.setToolTip("Show hidden files")
        self.hidden_btn.clicked.connect(self._toggle_hidden)
        toolbar_layout.addWidget(self.hidden_btn)

        # Add stretch to push buttons to left
        toolbar_layout.addStretch()

        layout.addWidget(toolbar)

        # Path bar in separate row (better visibility when window is small)
        self.path_bar = QLineEdit()
        self.path_bar.setPlaceholderText("Pfad eingeben...")
        self.path_bar.setStyleSheet("""
            QLineEdit {
                background: rgba(20, 20, 20, 0.9);
                color: #e0e0e0;
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 12px;
                margin: 0 4px 4px 4px;
            }
            QLineEdit:focus {
                border-color: rgba(59, 130, 246, 0.8);
                background: rgba(30, 30, 30, 0.95);
            }
        """)
        self.path_bar.returnPressed.connect(self._on_path_entered)
        layout.addWidget(self.path_bar)

        # File system model
        self.model = QFileSystemModel()
        self.model.setRootPath("")
        self._update_filter()

        # Tree view
        self.tree = QTreeView()
        self.tree.setModel(self.model)
        self.tree.setRootIndex(self.model.index(self.current_path))

        # Custom delegate for file colors
        self.delegate = FileColorDelegate(self.model, self.tree)
        self.tree.setItemDelegate(self.delegate)

        # Show columns: Name, Size, Date Modified (hide Type column)
        self.tree.setColumnWidth(0, 180)  # Name
        self.tree.setColumnWidth(1, 70)   # Size
        self.tree.setColumnHidden(2, True)  # Hide Type column
        self.tree.setColumnWidth(3, 120)  # Date Modified

        # Update column visibility from settings
        self._update_columns()

        # Enable sorting - use model's native sorting (no proxy)
        self.model.sort(0, Qt.SortOrder.AscendingOrder)  # Default: sort by name
        self._current_sort_column = 0
        self._current_sort_order = Qt.SortOrder.AscendingOrder

        # Header click for sorting
        header = self.tree.header()
        header.setSectionsClickable(True)
        header.setStretchLastSection(True)
        header.sectionClicked.connect(self._on_header_clicked)

        self.tree.setStyleSheet("""
            QTreeView {
                background: rgba(15, 15, 25, 0.85);
                color: #e0e0e0;
                border: none;
                border-radius: 8px;
                margin: 0 4px 4px 4px;
                padding: 4px;
            }
            QTreeView::item {
                padding: 4px 2px;
                border-radius: 4px;
            }
            QTreeView::item:hover {
                background: rgba(255, 255, 255, 0.08);
            }
            QTreeView::item:selected {
                background: rgba(59, 130, 246, 0.6);
            }
            QHeaderView::section {
                background: rgba(30, 30, 40, 0.9);
                color: #a0a0a0;
                border: none;
                border-right: 1px solid rgba(255, 255, 255, 0.05);
                border-bottom: 1px solid rgba(255, 255, 255, 0.1);
                padding: 6px 8px;
                font-weight: 600;
                font-size: 11px;
            }
            QHeaderView::section:hover {
                background: rgba(50, 50, 60, 0.9);
                color: #e0e0e0;
            }
            QHeaderView::section:pressed {
                background: rgba(59, 130, 246, 0.6);
            }
            QScrollBar:vertical {
                background: rgba(0, 0, 0, 0.2);
                width: 8px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical {
                background: rgba(255, 255, 255, 0.2);
                border-radius: 4px;
                min-height: 30px;
            }
            QScrollBar::handle:vertical:hover {
                background: rgba(255, 255, 255, 0.3);
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0;
            }
        """)

        self.tree.doubleClicked.connect(self._on_double_click)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._show_context_menu)

        layout.addWidget(self.tree, 1)

    def _btn_style(self) -> str:
        return """
            QToolButton {
                background: rgba(255, 255, 255, 0.05);
                color: #c0c0c0;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 6px;
                padding: 6px 10px;
                font-size: 14px;
            }
            QToolButton:hover {
                background: rgba(255, 255, 255, 0.12);
                color: #ffffff;
                border-color: rgba(255, 255, 255, 0.15);
            }
            QToolButton:pressed {
                background: rgba(59, 130, 246, 0.4);
            }
            QToolButton:checked {
                background: rgba(59, 130, 246, 0.5);
                border-color: rgba(59, 130, 246, 0.6);
                color: #ffffff;
            }
        """

    def _update_filter(self):
        """Update file filter based on settings"""
        show_hidden = self.settings.value("fb_show_hidden", False, type=bool)
        filters = QDir.Filter.AllDirs | QDir.Filter.Files | QDir.Filter.NoDotAndDotDot
        if show_hidden:
            filters |= QDir.Filter.Hidden
        self.model.setFilter(filters)

    def _update_columns(self):
        """Update column visibility from settings"""
        show_size = self.settings.value("fb_show_size", True, type=bool)
        show_date = self.settings.value("fb_show_date", True, type=bool)
        self.tree.setColumnHidden(1, not show_size)  # Size
        self.tree.setColumnHidden(3, not show_date)  # Date

    def _toggle_hidden(self):
        """Toggle hidden files visibility"""
        self.settings.setValue("fb_show_hidden", self.hidden_btn.isChecked())
        self._update_filter()
        self._refresh()

    def apply_settings(self):
        """Apply settings from QSettings (called when settings change)"""
        # Update hidden files
        self.hidden_btn.setChecked(self.settings.value("fb_show_hidden", False, type=bool))
        self._update_filter()

        # Update columns
        self._update_columns()

        # Reload colors
        self.delegate.reload_colors()

        # Apply theme colors
        self._apply_theme_colors()

        # Refresh view
        self._refresh()

    def _apply_theme_colors(self):
        """Apply theme colors from settings to all UI elements"""
        # Read theme colors
        primary = self.settings.value("theme_color_primary", "#3b82f6")
        surface = self.settings.value("theme_color_surface", "#1a1a2e")
        text_color = self.settings.value("theme_color_text", "#e0e0e0")
        border_radius = self.settings.value("widget_border_radius", 10, type=int)
        transparency = self.settings.value("widget_transparency", 85, type=int) / 100.0

        # Convert hex to rgba
        def hex_to_rgba(hex_color, alpha):
            hex_color = hex_color.lstrip("#")
            r = int(hex_color[0:2], 16)
            g = int(hex_color[2:4], 16)
            b = int(hex_color[4:6], 16)
            return f"rgba({r}, {g}, {b}, {alpha:.2f})"

        surface_rgba = hex_to_rgba(surface, transparency)
        surface_light = hex_to_rgba(surface, min(1.0, transparency + 0.1))

        # Update TreeView style
        self.tree.setStyleSheet(f"""
            QTreeView {{
                background: {surface_rgba};
                color: {text_color};
                border: none;
                border-radius: {border_radius}px;
                margin: 0 4px 4px 4px;
                padding: 4px;
            }}
            QTreeView::item {{
                padding: 4px 8px;
                border-radius: {border_radius - 6}px;
            }}
            QTreeView::item:hover {{
                background: rgba(255, 255, 255, 0.08);
            }}
            QTreeView::item:selected {{
                background: {primary};
                color: white;
            }}
            QHeaderView::section {{
                background: {surface_light};
                color: {text_color};
                padding: 6px 8px;
                border: none;
                border-bottom: 1px solid rgba(255, 255, 255, 0.08);
                font-weight: bold;
            }}
            QScrollBar:vertical {{
                background: transparent;
                width: 10px;
                border-radius: 5px;
                margin: 2px;
            }}
            QScrollBar::handle:vertical {{
                background: rgba(255, 255, 255, 0.2);
                border-radius: 5px;
                min-height: 30px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {primary};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
            QScrollBar:horizontal {{
                background: transparent;
                height: 10px;
                border-radius: 5px;
                margin: 2px;
            }}
            QScrollBar::handle:horizontal {{
                background: rgba(255, 255, 255, 0.2);
                border-radius: 5px;
                min-width: 30px;
            }}
            QScrollBar::handle:horizontal:hover {{
                background: {primary};
            }}
        """)

        # Update path bar
        self.path_bar.setStyleSheet(f"""
            QLineEdit {{
                background: {surface_rgba};
                color: {text_color};
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: {border_radius - 4}px;
                padding: 6px 10px;
                font-size: 12px;
            }}
            QLineEdit:focus {{
                border-color: {primary};
            }}
        """)

    def _navigate_to(self, path: str):
        """Navigate to path"""
        path = str(Path(path).resolve())

        if not os.path.isdir(path):
            logger.warning(f"Not a directory: {path}")
            return

        # Update history
        if self.current_path != path:
            # Remove forward history
            if self.history_index < len(self.history) - 1:
                self.history = self.history[:self.history_index + 1]

            self.history.append(path)
            self.history_index = len(self.history) - 1

        self.current_path = path
        self.path_bar.setText(path)
        self.tree.setRootIndex(self.model.index(path))

        self.directory_changed.emit(path)

    def _on_path_entered(self):
        """Handle path bar entry"""
        path = self.path_bar.text()
        if os.path.isdir(path):
            self._navigate_to(path)
        elif os.path.isfile(path):
            self.file_selected.emit(path)

    def _on_header_clicked(self, column: int):
        """Handle header click for sorting"""
        # Skip hidden column (Type)
        if column == 2:
            return

        # Toggle sort order if same column, otherwise ascending
        if column == self._current_sort_column:
            if self._current_sort_order == Qt.SortOrder.AscendingOrder:
                self._current_sort_order = Qt.SortOrder.DescendingOrder
            else:
                self._current_sort_order = Qt.SortOrder.AscendingOrder
        else:
            self._current_sort_column = column
            self._current_sort_order = Qt.SortOrder.AscendingOrder

        # Apply sorting
        self.model.sort(self._current_sort_column, self._current_sort_order)

    def _on_double_click(self, index: QModelIndex):
        """Handle double click - open with system for files, navigate for directories"""
        path = self.model.filePath(index)

        if os.path.isdir(path):
            self._navigate_to(path)
        else:
            # Open file with system default application
            self._open_with_system(path)
            # Also emit signal for internal handling if needed
            self.file_selected.emit(path)

    def _go_back(self):
        """Go back in history"""
        if self.history_index > 0:
            self.history_index -= 1
            path = self.history[self.history_index]
            self.current_path = path
            self.path_bar.setText(path)
            self.tree.setRootIndex(self.model.index(path))

    def _go_up(self):
        """Go to parent directory"""
        parent = str(Path(self.current_path).parent)
        if parent != self.current_path:
            self._navigate_to(parent)

    def _go_home(self):
        """Go to home directory"""
        self._navigate_to(str(Path.home()))

    def _refresh(self):
        """Refresh current directory"""
        self.model.setRootPath("")
        self.model.setRootPath(self.current_path)
        self.tree.setRootIndex(self.model.index(self.current_path))

    def _show_context_menu(self, pos):
        """Show context menu"""
        index = self.tree.indexAt(pos)
        path = self.model.filePath(index) if index.isValid() else self.current_path

        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background: rgba(25, 25, 35, 0.95);
                color: #e0e0e0;
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 8px;
                padding: 4px;
            }
            QMenu::item {
                padding: 8px 20px;
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

        if os.path.isfile(path):
            # Open with system default app
            open_action = menu.addAction("🚀 Open", lambda: self._open_with_system(path))
            open_action.setShortcut("Return")

            # Open with submenu for common applications
            open_with_menu = menu.addMenu("Open with...")
            open_with_menu.addAction("Text Editor", lambda: self._open_with_application(path, "xdg-open"))
            open_with_menu.addAction("VS Code", lambda: self._open_with_application(path, "code"))
            open_with_menu.addAction("Terminal (view)", lambda: self._view_in_terminal(path))
            open_with_menu.addSeparator()
            open_with_menu.addAction("Choose Application...", lambda: self._choose_application(path))

            menu.addSeparator()

        # Cut/Copy/Paste section
        if index.isValid():
            cut_action = menu.addAction("✂ Cut", lambda: self._cut(path))
            cut_action.setShortcut("Ctrl+X")
            copy_action = menu.addAction("📋 Copy", lambda: self._copy(path))
            copy_action.setShortcut("Ctrl+C")

        # Paste (always visible but enabled only when clipboard has content)
        paste_action = menu.addAction("📄 Paste", lambda: self._paste())
        paste_action.setShortcut("Ctrl+V")
        paste_action.setEnabled(FileBrowser._clipboard_path is not None)

        menu.addSeparator()

        menu.addAction("New Folder", lambda: self._new_folder())
        menu.addAction("New File", lambda: self._new_file())

        if index.isValid():
            menu.addSeparator()
            menu.addAction("Rename", lambda: self._rename(path))
            menu.addAction("Delete", lambda: self._delete(path))

        menu.addSeparator()
        menu.addAction("Open Terminal Here", lambda: self._open_terminal(path))

        menu.exec(self.tree.mapToGlobal(pos))

    def _new_folder(self):
        """Create new folder"""
        name, ok = QInputDialog.getText(self, "New Folder", "Folder name:")
        if ok and name:
            new_path = Path(self.current_path) / name
            try:
                new_path.mkdir()
                self._refresh()
            except Exception as e:
                QMessageBox.warning(self, "Error", str(e))

    def _new_file(self):
        """Create new file"""
        name, ok = QInputDialog.getText(self, "New File", "File name:")
        if ok and name:
            new_path = Path(self.current_path) / name
            try:
                new_path.touch()
                self._refresh()
            except Exception as e:
                QMessageBox.warning(self, "Error", str(e))

    def _rename(self, path: str):
        """Rename file/folder"""
        old_name = Path(path).name
        new_name, ok = QInputDialog.getText(self, "Rename", "New name:", text=old_name)
        if ok and new_name and new_name != old_name:
            new_path = Path(path).parent / new_name
            try:
                os.rename(path, new_path)
                self._refresh()
            except Exception as e:
                QMessageBox.warning(self, "Error", str(e))

    def _delete(self, path: str):
        """Delete file/folder"""
        name = Path(path).name
        reply = QMessageBox.question(
            self, "Delete",
            f"Delete '{name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                if os.path.isdir(path):
                    import shutil
                    shutil.rmtree(path)
                else:
                    os.remove(path)
                self._refresh()
            except Exception as e:
                QMessageBox.warning(self, "Error", str(e))

    def _cut(self, path: str):
        """Cut file/folder to clipboard"""
        FileBrowser._clipboard_path = path
        FileBrowser._clipboard_is_cut = True
        logger.info(f"Cut: {path}")

    def _copy(self, path: str):
        """Copy file/folder to clipboard"""
        FileBrowser._clipboard_path = path
        FileBrowser._clipboard_is_cut = False
        logger.info(f"Copy: {path}")

    def _paste(self):
        """Paste file/folder from clipboard"""
        import shutil

        if not FileBrowser._clipboard_path:
            return

        src = FileBrowser._clipboard_path
        if not os.path.exists(src):
            QMessageBox.warning(self, "Error", f"Source no longer exists: {src}")
            FileBrowser._clipboard_path = None
            return

        src_name = Path(src).name
        dest = Path(self.current_path) / src_name

        # Handle name collision
        if dest.exists():
            # Generate unique name
            base = dest.stem
            suffix = dest.suffix
            counter = 1
            while dest.exists():
                new_name = f"{base}_copy{counter}{suffix}" if suffix else f"{base}_copy{counter}"
                dest = Path(self.current_path) / new_name
                counter += 1

        try:
            if os.path.isdir(src):
                if FileBrowser._clipboard_is_cut:
                    shutil.move(src, dest)
                else:
                    shutil.copytree(src, dest)
            else:
                if FileBrowser._clipboard_is_cut:
                    shutil.move(src, dest)
                else:
                    shutil.copy2(src, dest)

            # Clear clipboard after cut operation
            if FileBrowser._clipboard_is_cut:
                FileBrowser._clipboard_path = None
                FileBrowser._clipboard_is_cut = False

            logger.info(f"Pasted to: {dest}")
            self._refresh()
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Paste failed: {e}")

    def _open_terminal(self, path: str):
        """Signal to open terminal at path"""
        if os.path.isfile(path):
            path = str(Path(path).parent)
        # Emit signal for main window to open terminal
        self.open_terminal_requested.emit(path)

    def _view_in_terminal(self, path: str):
        """View file content in terminal using less/cat"""
        if os.path.isfile(path):
            parent_dir = str(Path(path).parent)
            filename = Path(path).name
            # Emit signal to open terminal with view command
            self.open_terminal_requested.emit(f"cd '{parent_dir}' && less '{filename}'")

    def _choose_application(self, path: str):
        """Let user choose an application to open the file"""
        app_path, ok = QInputDialog.getText(
            self, "Open with Application",
            "Enter application name or path:",
            text=""
        )
        if ok and app_path:
            self._open_with_application(path, app_path)

    def get_selected_path(self) -> str:
        """Get currently selected path"""
        indexes = self.tree.selectedIndexes()
        if indexes:
            return self.model.filePath(indexes[0])
        return self.current_path
