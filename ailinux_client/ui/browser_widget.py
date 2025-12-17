"""
Browser Widget - Integrierter Webbrowser mit Tabs, Lesezeichen und KI-Features

Features:
- Tabbed browsing with new tab button
- Bookmark management (encrypted storage with server sync)
- Favorites bar for quick access
- Developer tools (F12)
- Context menu with AI options
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit,
    QPushButton, QMenu, QProgressBar, QTabWidget, QTabBar,
    QDialog, QListWidget, QListWidgetItem, QLabel, QInputDialog,
    QMessageBox, QToolButton, QSizePolicy, QSplitter, QDockWidget,
    QFrame, QScrollArea
)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings, QWebEngineProfile
from PyQt6.QtCore import Qt, pyqtSignal, QUrl, QSize, QTimer, QSettings
from PyQt6.QtGui import QAction, QIcon, QShortcut, QKeySequence
import json
import logging
from pathlib import Path

logger = logging.getLogger("ailinux.browser")

# Try to import encrypted settings
try:
    from ..core.encrypted_settings import get_encrypted_settings
    HAS_ENCRYPTED_SETTINGS = True
except ImportError:
    HAS_ENCRYPTED_SETTINGS = False
    logger.warning("Encrypted settings not available, using plain file storage")


class BookmarkManager:
    """
    Verwaltet Lesezeichen mit verschlüsselter Speicherung.

    Wenn encrypted_settings verfügbar und entsperrt ist, werden Lesezeichen
    verschlüsselt gespeichert. Ansonsten Fallback auf plain JSON.

    Lesezeichen können gepinnt werden - gepinnte Lesezeichen werden immer
    im Overflow-Menü angezeigt, unabhängig von der Fenstergröße.
    """

    DEFAULT_BOOKMARKS = [
        {"title": "AILinux Search", "url": "https://search.ailinux.me", "folder": "default", "pinned": True},
        {"title": "DuckDuckGo", "url": "https://duckduckgo.com", "folder": "default", "pinned": False},
        {"title": "GitHub", "url": "https://github.com", "folder": "dev", "pinned": True},
        {"title": "Stack Overflow", "url": "https://stackoverflow.com", "folder": "dev", "pinned": False},
        {"title": "Python Docs", "url": "https://docs.python.org/3/", "folder": "dev", "pinned": False},
    ]

    def __init__(self):
        self.bookmarks_file = Path.home() / ".config" / "ailinux" / "bookmarks.json"
        self.bookmarks = []
        self.favorites = []  # Quick access bar
        self.load()

    def _use_encrypted(self) -> bool:
        """Check if encrypted storage is available and unlocked."""
        if HAS_ENCRYPTED_SETTINGS:
            settings = get_encrypted_settings()
            return settings.is_unlocked()
        return False

    def load(self):
        """Lade Lesezeichen (verschlüsselt wenn möglich)"""
        if self._use_encrypted():
            settings = get_encrypted_settings()
            self.bookmarks = settings.get_bookmarks()
            self.favorites = settings.get_favorites()
            if not self.bookmarks:
                # Initialize with defaults
                for bm in self.DEFAULT_BOOKMARKS:
                    settings.add_bookmark(bm["url"], bm["title"], bm.get("folder", "default"))
                self.bookmarks = settings.get_bookmarks()
            logger.info(f"Loaded {len(self.bookmarks)} bookmarks from encrypted storage")
        else:
            # Fallback to plain file
            if self.bookmarks_file.exists():
                try:
                    data = json.loads(self.bookmarks_file.read_text())
                    if isinstance(data, list):
                        self.bookmarks = data
                        self.favorites = []
                    else:
                        self.bookmarks = data.get("bookmarks", [])
                        self.favorites = data.get("favorites", [])
                except:
                    self.bookmarks = []
                    self.favorites = []
            else:
                self.bookmarks = self.DEFAULT_BOOKMARKS.copy()
                self.favorites = self.DEFAULT_BOOKMARKS[:3]  # First 3 as favorites
                self.save()

    def save(self):
        """Speichere Lesezeichen (verschlüsselt wenn möglich)"""
        if self._use_encrypted():
            # Already saved by add/remove methods
            pass
        else:
            # Plain file storage
            self.bookmarks_file.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "bookmarks": self.bookmarks,
                "favorites": self.favorites
            }
            self.bookmarks_file.write_text(json.dumps(data, indent=2))

    def add(self, title: str, url: str, folder: str = "default", pinned: bool = False) -> bool:
        """Lesezeichen hinzufügen"""
        # Duplikate vermeiden
        for b in self.bookmarks:
            if b.get("url") == url:
                return False

        if self._use_encrypted():
            settings = get_encrypted_settings()
            result = settings.add_bookmark(url, title, folder)
            if result:
                self.bookmarks = settings.get_bookmarks()
                # Update pinned status in local copy
                for b in self.bookmarks:
                    if b.get("url") == url:
                        b["pinned"] = pinned
                        break
            return result
        else:
            self.bookmarks.append({"title": title, "url": url, "folder": folder, "pinned": pinned})
            self.save()
            return True

    def remove(self, url: str):
        """Lesezeichen entfernen"""
        if self._use_encrypted():
            settings = get_encrypted_settings()
            # Find bookmark ID by URL
            for bm in self.bookmarks:
                if bm.get("url") == url:
                    settings.remove_bookmark(bm.get("id", ""))
                    break
            self.bookmarks = settings.get_bookmarks()
        else:
            self.bookmarks = [b for b in self.bookmarks if b.get("url") != url]
            self.save()

    def is_bookmarked(self, url: str) -> bool:
        """Prüfe ob URL bereits gespeichert"""
        return any(b.get("url") == url for b in self.bookmarks)

    def is_pinned(self, url: str) -> bool:
        """Prüfe ob Lesezeichen gepinnt ist"""
        for b in self.bookmarks:
            if b.get("url") == url:
                return b.get("pinned", False)
        return False

    def toggle_pin(self, url: str) -> bool:
        """Pin-Status eines Lesezeichens umschalten"""
        for b in self.bookmarks:
            if b.get("url") == url:
                b["pinned"] = not b.get("pinned", False)
                self.save()
                return b["pinned"]
        return False

    def set_pinned(self, url: str, pinned: bool):
        """Pin-Status setzen"""
        for b in self.bookmarks:
            if b.get("url") == url:
                b["pinned"] = pinned
                self.save()
                return True
        return False

    def get_pinned(self) -> list:
        """Alle gepinnten Lesezeichen abrufen"""
        return [b for b in self.bookmarks if b.get("pinned", False)]

    def get_all(self) -> list:
        """Alle Lesezeichen abrufen"""
        return self.bookmarks.copy()

    def get_favorites(self) -> list:
        """Favoriten für Quick-Access-Bar abrufen"""
        if self._use_encrypted():
            settings = get_encrypted_settings()
            return settings.get_favorites()
        return self.favorites.copy()

    def add_favorite(self, url: str, title: str) -> bool:
        """Zu Favoriten hinzufügen (max 10)"""
        if self._use_encrypted():
            settings = get_encrypted_settings()
            result = settings.add_favorite(url, title)
            self.favorites = settings.get_favorites()
            return result
        else:
            # Remove if exists
            self.favorites = [f for f in self.favorites if f.get("url") != url]
            self.favorites.append({"url": url, "title": title})
            self.favorites = self.favorites[-10:]  # Keep max 10
            self.save()
            return True

    def remove_favorite(self, url: str) -> bool:
        """Aus Favoriten entfernen"""
        if self._use_encrypted():
            settings = get_encrypted_settings()
            result = settings.remove_favorite(url)
            self.favorites = settings.get_favorites()
            return result
        else:
            self.favorites = [f for f in self.favorites if f.get("url") != url]
            self.save()
            return True

    def is_favorite(self, url: str) -> bool:
        """Prüfe ob URL ein Favorit ist"""
        favorites = self.get_favorites()
        return any(f.get("url") == url for f in favorites)

    def get_folders(self) -> list:
        """Alle Ordner abrufen"""
        folders = set()
        for bm in self.bookmarks:
            folders.add(bm.get("folder", "default"))
        return sorted(list(folders))


class BookmarkDialog(QDialog):
    """Dialog zur Lesezeichen-Verwaltung"""

    bookmark_selected = pyqtSignal(str)  # URL

    def __init__(self, bookmark_manager: BookmarkManager, parent=None):
        super().__init__(parent)
        self.bookmark_manager = bookmark_manager
        self.setup_ui()
        self.load_bookmarks()

    def setup_ui(self):
        self.setWindowTitle("⭐ Lesezeichen")
        self.setMinimumSize(400, 500)
        self.setStyleSheet("""
            QDialog {
                background-color: #1e1e2e;
                color: #cdd6f4;
            }
            QListWidget {
                background-color: #313244;
                color: #cdd6f4;
                border: 1px solid #45475a;
                border-radius: 6px;
            }
            QListWidget::item {
                padding: 10px;
                border-bottom: 1px solid #45475a;
            }
            QListWidget::item:hover {
                background-color: #45475a;
            }
            QListWidget::item:selected {
                background-color: #89b4fa;
                color: #1e1e2e;
            }
            QPushButton {
                background-color: #89b4fa;
                color: #1e1e2e;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #b4befe;
            }
            QPushButton#deleteBtn {
                background-color: #f38ba8;
            }
            QPushButton#deleteBtn:hover {
                background-color: #eba0ac;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # Header
        header = QLabel("⭐ Deine Lesezeichen")
        header.setStyleSheet("font-size: 16px; font-weight: bold; color: #89b4fa;")
        layout.addWidget(header)

        # Liste
        self.list_widget = QListWidget()
        self.list_widget.itemDoubleClicked.connect(self.open_bookmark)
        layout.addWidget(self.list_widget)

        # Buttons
        btn_layout = QHBoxLayout()

        open_btn = QPushButton("🔗 Öffnen")
        open_btn.clicked.connect(self.open_selected)
        btn_layout.addWidget(open_btn)

        delete_btn = QPushButton("🗑️ Löschen")
        delete_btn.setObjectName("deleteBtn")
        delete_btn.clicked.connect(self.delete_selected)
        btn_layout.addWidget(delete_btn)

        close_btn = QPushButton("✖ Schließen")
        close_btn.clicked.connect(self.close)
        btn_layout.addWidget(close_btn)

        layout.addLayout(btn_layout)

    def load_bookmarks(self):
        """Lade Lesezeichen in Liste"""
        self.list_widget.clear()
        for bookmark in self.bookmark_manager.get_all():
            item = QListWidgetItem(f"⭐ {bookmark['title']}\n   {bookmark['url']}")
            item.setData(Qt.ItemDataRole.UserRole, bookmark["url"])
            self.list_widget.addItem(item)

    def open_bookmark(self, item):
        """Lesezeichen öffnen"""
        url = item.data(Qt.ItemDataRole.UserRole)
        if url:
            self.bookmark_selected.emit(url)
            self.accept()

    def open_selected(self):
        """Ausgewähltes Lesezeichen öffnen"""
        item = self.list_widget.currentItem()
        if item:
            self.open_bookmark(item)

    def delete_selected(self):
        """Ausgewähltes Lesezeichen löschen"""
        item = self.list_widget.currentItem()
        if item:
            url = item.data(Qt.ItemDataRole.UserRole)
            self.bookmark_manager.remove(url)
            self.load_bookmarks()


class BrowserTab(QWidget):
    """Einzelner Browser-Tab"""

    text_selected = pyqtSignal(str)
    title_changed = pyqtSignal(str)
    url_changed = pyqtSignal(str)
    loading_progress = pyqtSignal(int)
    new_tab_requested = pyqtSignal(str)  # URL für neuen Tab

    # Class-level persistent profile (shared across all tabs)
    _profile = None

    @classmethod
    def get_profile(cls):
        """Get or create the persistent browser profile"""
        if cls._profile is None:
            from pathlib import Path

            # Create storage directory
            browser_path = Path.home() / ".config" / "ailinux" / "browser"
            browser_path.mkdir(parents=True, exist_ok=True)

            # Create a NAMED profile - this enables persistence!
            cls._profile = QWebEngineProfile("ailinux", None)

            # Set our custom storage paths
            cls._profile.setPersistentStoragePath(str(browser_path))
            cls._profile.setCachePath(str(browser_path / "cache"))

            # Enable persistent cookies
            cls._profile.setPersistentCookiesPolicy(
                QWebEngineProfile.PersistentCookiesPolicy.AllowPersistentCookies
            )

            # Configure browser settings for proper input/interaction
            settings = cls._profile.settings()
            settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
            settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanOpenWindows, True)
            settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanAccessClipboard, True)
            settings.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)
            settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
            settings.setAttribute(QWebEngineSettings.WebAttribute.FocusOnNavigationEnabled, True)
            settings.setAttribute(QWebEngineSettings.WebAttribute.AllowRunningInsecureContent, False)
            settings.setAttribute(QWebEngineSettings.WebAttribute.PluginsEnabled, True)
            settings.setAttribute(QWebEngineSettings.WebAttribute.FullScreenSupportEnabled, True)
            settings.setAttribute(QWebEngineSettings.WebAttribute.ScreenCaptureEnabled, True)
            settings.setAttribute(QWebEngineSettings.WebAttribute.WebGLEnabled, True)
            settings.setAttribute(QWebEngineSettings.WebAttribute.Accelerated2dCanvasEnabled, True)
            settings.setAttribute(QWebEngineSettings.WebAttribute.AutoLoadIconsForPage, True)
            settings.setAttribute(QWebEngineSettings.WebAttribute.TouchIconsEnabled, True)
            settings.setAttribute(QWebEngineSettings.WebAttribute.AllowWindowActivationFromJavaScript, True)

            # Set user agent
            cls._profile.setHttpUserAgent(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36 AILinux/1.0"
            )

            logger.info(f"Browser profile 'ailinux' created with storage at: {browser_path}")

        return cls._profile

    def __init__(self, url: str = "https://search.ailinux.me", parent=None):
        super().__init__(parent)
        self.settings = QSettings("AILinux", "Client")
        self.setup_ui(url)

    def setup_ui(self, url: str):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Get persistent profile
        profile = BrowserTab.get_profile()

        # Create page with our persistent profile
        from PyQt6.QtWebEngineCore import QWebEnginePage
        self.web_page = QWebEnginePage(profile, self)

        # WebEngine View with persistent profile page
        self.web_view = QWebEngineView()
        self.web_view.setPage(self.web_page)

        # CRITICAL: Ensure WebEngineView can receive focus, mouse and keyboard input
        self.web_view.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.web_view.setAttribute(Qt.WidgetAttribute.WA_InputMethodEnabled, True)
        self.web_view.setAttribute(Qt.WidgetAttribute.WA_AcceptTouchEvents, True)
        self.web_view.setAttribute(Qt.WidgetAttribute.WA_MouseTracking, True)
        self.web_view.setMouseTracking(True)

        # Set this widget as focus proxy so clicks go to web view
        self.setFocusProxy(self.web_view)

        # Now load the URL after setup
        self.web_view.setUrl(QUrl(url))

        # Context Menu für Text-Selektion
        self.web_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.web_view.customContextMenuRequested.connect(self.show_context_menu)

        layout.addWidget(self.web_view)

        # Signals verbinden
        self.web_view.titleChanged.connect(self.title_changed.emit)
        self.web_view.urlChanged.connect(lambda u: self.url_changed.emit(u.toString()))
        self.web_view.loadProgress.connect(self.loading_progress.emit)

        # Link in neuem Tab öffnen
        self.web_view.page().newWindowRequested.connect(self.handle_new_window)

    def handle_new_window(self, request):
        """Neue Fenster/Links als Tab öffnen"""
        self.new_tab_requested.emit(request.requestedUrl().toString())
        request.openIn(self.web_view.page())

    def navigate(self, url: str):
        """Zu URL navigieren"""
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        self.web_view.setUrl(QUrl(url))

    def show_context_menu(self, position):
        """Kontextmenü mit KI-Optionen"""
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #1e1e2e;
                color: #cdd6f4;
                border: 1px solid #45475a;
            }
            QMenu::item {
                padding: 8px 20px;
            }
            QMenu::item:selected {
                background-color: #45475a;
            }
        """)

        # Standard-Aktionen
        back_action = menu.addAction("◀ Zurück")
        back_action.triggered.connect(lambda: self.web_view.back())

        forward_action = menu.addAction("▶ Vorwärts")
        forward_action.triggered.connect(lambda: self.web_view.forward())

        reload_action = menu.addAction("🔄 Neu laden")
        reload_action.triggered.connect(lambda: self.web_view.reload())

        menu.addSeparator()

        # KI-Aktionen
        ai_menu = menu.addMenu("🤖 KI-Aktionen")

        # Auf markierten Text
        explain_action = ai_menu.addAction("💡 Erkläre markierten Text")
        explain_action.triggered.connect(lambda: self.ai_action("explain"))

        translate_action = ai_menu.addAction("🌍 Übersetzen")
        translate_action.triggered.connect(lambda: self.ai_action("translate"))

        summarize_action = ai_menu.addAction("📝 Zusammenfassen")
        summarize_action.triggered.connect(lambda: self.ai_action("summarize"))

        ai_menu.addSeparator()

        # Auf ganze Seite
        page_summarize = ai_menu.addAction("📄 Seite zusammenfassen")
        page_summarize.triggered.connect(lambda: self.ai_page_action("summarize"))

        page_extract = ai_menu.addAction("📋 Wichtiges extrahieren")
        page_extract.triggered.connect(lambda: self.ai_page_action("extract"))

        page_questions = ai_menu.addAction("❓ FAQ generieren")
        page_questions.triggered.connect(lambda: self.ai_page_action("questions"))

        menu.exec(self.web_view.mapToGlobal(position))

    def ai_action(self, action: str):
        """KI-Aktion auf selektierten Text"""
        self.web_view.page().runJavaScript(
            "window.getSelection().toString()",
            lambda text: self.text_selected.emit(f"{action}:{text}") if text else None
        )

    def ai_page_action(self, action: str):
        """KI-Aktion auf gesamte Seite"""
        # Extrahiere Text-Inhalt der Seite
        js_code = """
        (function() {
            var body = document.body;
            var clone = body.cloneNode(true);
            var scripts = clone.getElementsByTagName('script');
            var styles = clone.getElementsByTagName('style');
            while(scripts.length > 0) scripts[0].remove();
            while(styles.length > 0) styles[0].remove();
            return clone.innerText || clone.textContent;
        })();
        """
        url = self.web_view.url().toString()
        self.web_view.page().runJavaScript(
            js_code,
            lambda text: self.text_selected.emit(f"page_{action}:{url}|{text[:10000]}") if text else None
        )

    def get_url(self) -> str:
        """Aktuelle URL abrufen"""
        return self.web_view.url().toString()

    def get_title(self) -> str:
        """Aktueller Titel abrufen"""
        return self.web_view.title() or "Neuer Tab"

    def focus_web_view(self):
        """Focus the web view to enable keyboard/mouse input"""
        self.web_view.setFocus(Qt.FocusReason.OtherFocusReason)


class OverflowMenuButton(QToolButton):
    """
    Overflow-Menü-Button für Browser-Tabs und Lesezeichen.

    Zeigt ein Dropdown-Menü mit:
    - Offenen Browser-Tabs
    - Gepinnten Lesezeichen (📌)
    - Lesezeichen die nicht in die Leiste passen
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setText("≡")
        self.setToolTip("Overflow-Menü (Tabs & Lesezeichen)")
        self.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.setFixedSize(32, 24)
        self.setStyleSheet("""
            QToolButton {
                background-color: #45475a;
                color: #cdd6f4;
                border: none;
                border-radius: 4px;
                font-weight: bold;
                font-size: 14px;
            }
            QToolButton:hover {
                background-color: #585b70;
            }
            QToolButton::menu-indicator {
                image: none;
            }
        """)

        self.menu_style = """
            QMenu {
                background-color: #1e1e2e;
                color: #cdd6f4;
                border: 1px solid #45475a;
                border-radius: 6px;
                padding: 6px 0;
            }
            QMenu::item {
                padding: 8px 20px 8px 12px;
                border-radius: 3px;
                margin: 2px 6px;
            }
            QMenu::item:selected {
                background-color: #45475a;
            }
            QMenu::separator {
                height: 1px;
                background-color: #45475a;
                margin: 6px 12px;
            }
            QMenu::item:disabled {
                color: #6c7086;
            }
        """

        self._browser_widget = None
        self._hidden_bookmarks = []

    def set_browser_widget(self, widget):
        """Browser-Widget setzen für Tab-Zugriff"""
        self._browser_widget = widget

    def set_hidden_bookmarks(self, bookmarks: list):
        """Versteckte Lesezeichen setzen"""
        self._hidden_bookmarks = bookmarks

    def build_menu(self):
        """Menü aufbauen"""
        menu = QMenu(self)
        menu.setStyleSheet(self.menu_style)

        if not self._browser_widget:
            return menu

        # === Offene Tabs ===
        tab_widget = self._browser_widget.tab_widget
        if tab_widget.count() > 0:
            tabs_header = menu.addAction("📑 Offene Tabs")
            tabs_header.setEnabled(False)

            for i in range(tab_widget.count()):
                tab = tab_widget.widget(i)
                if tab:
                    title = tab_widget.tabText(i) or "Tab"
                    url = tab.get_url() if hasattr(tab, 'get_url') else ""

                    # Aktueller Tab markieren
                    prefix = "● " if i == tab_widget.currentIndex() else "  "
                    action = menu.addAction(f"{prefix}{title}")
                    action.triggered.connect(lambda checked, idx=i: tab_widget.setCurrentIndex(idx))
                    action.setToolTip(url)

            menu.addSeparator()

        # === Gepinnte Lesezeichen ===
        pinned = self._browser_widget.bookmark_manager.get_pinned()
        if pinned:
            pinned_header = menu.addAction("📌 Gepinnte Lesezeichen")
            pinned_header.setEnabled(False)

            for bm in pinned:
                title = bm.get('title', 'Unbenannt')[:30]
                url = bm.get('url', '')
                action = menu.addAction(f"  📌 {title}")
                action.setToolTip(url)
                action.triggered.connect(lambda checked, u=url: self._browser_widget.navigate(u))

            menu.addSeparator()

        # === Versteckte Lesezeichen (overflow) ===
        if self._hidden_bookmarks:
            overflow_header = menu.addAction("📚 Weitere Lesezeichen")
            overflow_header.setEnabled(False)

            for bm in self._hidden_bookmarks:
                title = bm.get('title', 'Unbenannt')[:30]
                url = bm.get('url', '')
                is_pinned = bm.get('pinned', False)
                icon = "📌" if is_pinned else "⭐"
                action = menu.addAction(f"  {icon} {title}")
                action.setToolTip(url)
                action.triggered.connect(lambda checked, u=url: self._browser_widget.navigate(u))

        # Wenn Menü leer
        if menu.isEmpty():
            empty_action = menu.addAction("Keine Einträge")
            empty_action.setEnabled(False)

        return menu

    def showMenu(self):
        """Menü anzeigen (überschrieben um dynamisch zu bauen)"""
        menu = self.build_menu()
        self.setMenu(menu)
        super().showMenu()


class ClosableTabBar(QTabBar):
    """Tab-Bar mit Close-Button und Neuer-Tab-Button"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMovable(True)
        self.setTabsClosable(True)
        self.setExpanding(False)
        self.setStyleSheet("""
            QTabBar {
                background-color: #181825;
            }
            QTabBar::tab {
                background-color: #313244;
                color: #cdd6f4;
                padding: 8px 12px;
                margin-right: 2px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                max-width: 200px;
            }
            QTabBar::tab:selected {
                background-color: #45475a;
            }
            QTabBar::tab:hover:!selected {
                background-color: #3b3d4f;
            }
            QTabBar::close-button {
                image: none;
                background: transparent;
                border: none;
            }
            QTabBar::close-button:hover {
                background: #f38ba8;
                border-radius: 4px;
            }
        """)


class BrowserWidget(QWidget):
    """Integrierter Browser mit Tabs, Lesezeichen und KI-Integration"""

    text_selected = pyqtSignal(str)  # Für KI-Analyse von Text
    url_changed = pyqtSignal(str)

    # Search engine URL patterns
    SEARCH_ENGINES = {
        "Google": "https://www.google.com/search?q={}",
        "DuckDuckGo": "https://duckduckgo.com/?q={}",
        "Bing": "https://www.bing.com/search?q={}",
        "Brave Search": "https://search.brave.com/search?q={}",
        "Ecosia": "https://www.ecosia.org/search?q={}",
        "StartPage": "https://www.startpage.com/sp/search?query={}",
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.settings = QSettings("AILinux", "Client")
        self._load_settings()
        self.bookmark_manager = BookmarkManager()
        self.tabs = []
        self._bookmark_buttons = []  # Track bookmark buttons for overflow
        self._hidden_bookmarks = []  # Bookmarks hidden due to overflow
        self.overflow_btn = None
        self.setup_ui()
        self._apply_theme_colors()

    def _load_settings(self):
        """Load browser settings"""
        self.homepage = self.settings.value("browser_homepage", "https://www.google.com")
        self.search_engine = self.settings.value("browser_search_engine", "Google")
        self.new_tab_url = self.settings.value("browser_new_tab_url", "about:blank")
        self.enable_js = self.settings.value("browser_enable_js", True, type=bool)
        self.block_popups = self.settings.value("browser_block_popups", True, type=bool)
        self.block_third_party_cookies = self.settings.value("browser_block_third_party_cookies", False, type=bool)

    def clear_browser_data(self, clear_cookies: bool = True, clear_cache: bool = True, clear_history: bool = False):
        """
        Clear browser data (cookies, cache, history).

        Args:
            clear_cookies: Clear all cookies
            clear_cache: Clear browser cache
            clear_history: Clear browsing history
        """
        import shutil
        from pathlib import Path

        profile = QWebEngineProfile.defaultProfile()
        cookie_path = Path.home() / ".config" / "ailinux" / "browser"

        try:
            if clear_cache:
                cache_path = cookie_path / "cache"
                if cache_path.exists():
                    shutil.rmtree(cache_path)
                    cache_path.mkdir(parents=True, exist_ok=True)
                # Also clear in-memory cache
                profile.clearHttpCache()
                logger.info("Browser cache cleared")

            if clear_cookies:
                # Clear all cookies from the cookie store
                profile.cookieStore().deleteAllCookies()
                logger.info("Browser cookies cleared")

            if clear_history:
                # Clear visited links
                profile.clearAllVisitedLinks()
                logger.info("Browser history cleared")

            QMessageBox.information(
                self,
                "Browserdaten gelöscht",
                "Die ausgewählten Browserdaten wurden erfolgreich gelöscht."
            )
        except Exception as e:
            logger.error(f"Failed to clear browser data: {e}")
            QMessageBox.warning(
                self,
                "Fehler",
                f"Fehler beim Löschen der Browserdaten: {e}"
            )

    def apply_settings(self):
        """Apply settings from QSettings (called when settings change)"""
        self._load_settings()
        self._apply_theme_colors()
        # Note: JavaScript setting requires page reload to take effect

    def _apply_theme_colors(self):
        """
        Apply theme colors from settings to browser UI.
        Follows WCAG contrast guidelines for visibility.
        """
        # Read theme colors from settings
        primary = self.settings.value("theme_color_primary", "#3b82f6")
        secondary = self.settings.value("theme_color_secondary", "#6366f1")
        surface = self.settings.value("theme_color_surface", "#1a1a2e")
        text_color = self.settings.value("theme_color_text", "#e0e0e0")
        border_radius = self.settings.value("widget_border_radius", 10, type=int)
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
        surface_lighter = hex_to_rgba(surface, min(1.0, transparency - 0.1))

        # Button style
        btn_style = f"""
            QPushButton {{
                background-color: {surface_rgba};
                color: {text_color};
                border: none;
                border-radius: {border_radius - 4}px;
                padding: 5px;
                font-size: 14px;
            }}
            QPushButton:hover {{
                background-color: {primary};
                color: white;
            }}
        """

        # Apply to navigation buttons
        for btn in [self.back_btn, self.forward_btn, self.refresh_btn, self.home_btn,
                    self.bookmark_btn, self.bookmarks_btn, self.new_tab_btn]:
            if hasattr(self, btn.objectName()) or btn:
                btn.setStyleSheet(btn_style)

        # URL Bar styling
        if hasattr(self, 'url_bar'):
            self.url_bar.setStyleSheet(f"""
                QLineEdit {{
                    background-color: {surface_rgba};
                    color: {text_color};
                    border: 1px solid rgba(255, 255, 255, 0.1);
                    border-radius: {border_radius - 4}px;
                    padding: 6px 10px;
                    font-size: 13px;
                    selection-background-color: {primary};
                }}
                QLineEdit:focus {{
                    border-color: {primary};
                }}
            """)

        # Progress bar
        if hasattr(self, 'progress'):
            self.progress.setStyleSheet(f"""
                QProgressBar {{
                    background-color: {surface_lighter};
                    border: none;
                }}
                QProgressBar::chunk {{
                    background-color: {primary};
                }}
            """)

        # Bookmark bar
        if hasattr(self, 'bookmark_bar'):
            self.bookmark_bar.setStyleSheet(f"background-color: {surface_lighter};")

        # Tab widget
        if hasattr(self, 'tab_widget'):
            self.tab_widget.setStyleSheet(f"""
                QTabWidget::pane {{
                    border: none;
                    background-color: {surface_rgba};
                }}
                QTabBar::tab {{
                    background: {surface_lighter};
                    color: {text_color};
                    padding: 6px 12px;
                    border-top-left-radius: {border_radius - 6}px;
                    border-top-right-radius: {border_radius - 6}px;
                    margin-right: 2px;
                }}
                QTabBar::tab:selected {{
                    background: {surface_rgba};
                    color: white;
                }}
                QTabBar::tab:hover {{
                    background: {primary};
                    color: white;
                }}
            """)

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Allow browser to shrink and expand freely
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumHeight(150)

        # Navigation Bar
        nav_layout = QHBoxLayout()
        nav_layout.setContentsMargins(5, 5, 5, 5)
        nav_layout.setSpacing(5)

        # Navigation Buttons Style
        btn_style = """
            QPushButton {
                background-color: #313244;
                color: #cdd6f4;
                border: none;
                border-radius: 4px;
                padding: 5px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #45475a;
            }
        """

        self.back_btn = QPushButton("◀")
        self.back_btn.setFixedSize(32, 28)
        self.back_btn.setStyleSheet(btn_style)
        self.back_btn.setToolTip("Zurück")
        self.back_btn.clicked.connect(self.go_back)
        nav_layout.addWidget(self.back_btn)

        self.forward_btn = QPushButton("▶")
        self.forward_btn.setFixedSize(32, 28)
        self.forward_btn.setStyleSheet(btn_style)
        self.forward_btn.setToolTip("Vorwärts")
        self.forward_btn.clicked.connect(self.go_forward)
        nav_layout.addWidget(self.forward_btn)

        self.refresh_btn = QPushButton("🔄")
        self.refresh_btn.setFixedSize(32, 28)
        self.refresh_btn.setStyleSheet(btn_style)
        self.refresh_btn.setToolTip("Aktualisieren")
        self.refresh_btn.clicked.connect(self.refresh)
        nav_layout.addWidget(self.refresh_btn)

        self.home_btn = QPushButton("🏠")
        self.home_btn.setFixedSize(32, 28)
        self.home_btn.setStyleSheet(btn_style)
        self.home_btn.setToolTip("Startseite")
        self.home_btn.clicked.connect(lambda: self.navigate(self.homepage))
        nav_layout.addWidget(self.home_btn)

        # URL Bar
        self.url_bar = QLineEdit()
        self.url_bar.setPlaceholderText("URL eingeben oder suchen...")
        self.url_bar.setMinimumWidth(200)
        self.url_bar.setMinimumHeight(32)
        self.url_bar.setStyleSheet("""
            QLineEdit {
                background-color: #313244;
                color: #cdd6f4;
                border: 1px solid #45475a;
                border-radius: 6px;
                padding: 6px 10px;
                font-size: 13px;
            }
            QLineEdit:focus {
                border-color: #89b4fa;
            }
        """)
        self.url_bar.returnPressed.connect(self.navigate_from_bar)
        nav_layout.addWidget(self.url_bar, 1)  # Stretch factor 1 - takes remaining space

        # Bookmark-Button (Star)
        self.bookmark_btn = QPushButton("☆")
        self.bookmark_btn.setFixedSize(32, 28)
        self.bookmark_btn.setStyleSheet(btn_style)
        self.bookmark_btn.setToolTip("Lesezeichen hinzufügen")
        self.bookmark_btn.clicked.connect(self.toggle_bookmark)
        nav_layout.addWidget(self.bookmark_btn)

        # Bookmarks-Manager Button
        self.bookmarks_btn = QPushButton("📚")
        self.bookmarks_btn.setFixedSize(32, 28)
        self.bookmarks_btn.setStyleSheet(btn_style)
        self.bookmarks_btn.setToolTip("Lesezeichen verwalten")
        self.bookmarks_btn.clicked.connect(self.show_bookmarks)
        nav_layout.addWidget(self.bookmarks_btn)

        # Neuer Tab Button
        self.new_tab_btn = QPushButton("➕")
        self.new_tab_btn.setFixedSize(32, 28)
        self.new_tab_btn.setStyleSheet(btn_style)
        self.new_tab_btn.setToolTip("Neuer Tab (Ctrl+T)")
        self.new_tab_btn.clicked.connect(lambda: self.add_tab())
        nav_layout.addWidget(self.new_tab_btn)

        layout.addLayout(nav_layout)

        # Progress Bar
        self.progress = QProgressBar()
        self.progress.setFixedHeight(2)
        self.progress.setTextVisible(False)
        self.progress.setStyleSheet("""
            QProgressBar {
                background-color: #1e1e2e;
                border: none;
            }
            QProgressBar::chunk {
                background-color: #89b4fa;
            }
        """)
        self.progress.hide()
        layout.addWidget(self.progress)

        # Lesezeichen-Schnellzugriffsleiste
        self.bookmark_bar = QWidget()
        self.bookmark_bar_layout = QHBoxLayout(self.bookmark_bar)
        self.bookmark_bar_layout.setContentsMargins(5, 2, 5, 2)
        self.bookmark_bar_layout.setSpacing(4)
        self.bookmark_bar.setStyleSheet("background-color: #181825;")
        self.update_bookmark_bar()
        layout.addWidget(self.bookmark_bar)

        # Tab Widget
        self.tab_widget = QTabWidget()
        self.tab_widget.setTabBar(ClosableTabBar())
        self.tab_widget.setDocumentMode(True)
        self.tab_widget.setStyleSheet("""
            QTabWidget::pane {
                border: none;
                background-color: #1e1e2e;
            }
        """)
        self.tab_widget.tabCloseRequested.connect(self.close_tab)
        self.tab_widget.currentChanged.connect(self.on_tab_changed)
        layout.addWidget(self.tab_widget)

        # Ersten Tab hinzufügen mit Homepage
        self.add_tab(self.homepage or "https://www.google.com")

        # Dev Tools Panel (initially hidden)
        self.dev_tools_view = None
        self.dev_tools_visible = False

        # Shortcuts
        self.setup_shortcuts()

    def add_tab(self, url: str = None):
        """Neuen Tab hinzufügen"""
        if url is None:
            url = self.new_tab_url if self.new_tab_url else self.homepage
        tab = BrowserTab(url)
        tab.text_selected.connect(self.text_selected.emit)
        tab.title_changed.connect(lambda title: self.update_tab_title(tab, title))
        tab.url_changed.connect(self.on_url_changed)
        tab.loading_progress.connect(self.on_loading_progress)
        tab.new_tab_requested.connect(self.add_tab)

        index = self.tab_widget.addTab(tab, "🌐 Laden...")
        self.tab_widget.setCurrentIndex(index)
        self.tabs.append(tab)
        return tab

    def close_tab(self, index: int):
        """Tab schließen"""
        if self.tab_widget.count() > 1:
            tab = self.tab_widget.widget(index)
            self.tab_widget.removeTab(index)
            if tab in self.tabs:
                self.tabs.remove(tab)
            tab.deleteLater()
        else:
            # Letzter Tab: Zur Startseite navigieren
            self.navigate(self.homepage)

    def current_tab(self) -> BrowserTab:
        """Aktuellen Tab abrufen"""
        return self.tab_widget.currentWidget()

    def update_tab_title(self, tab: BrowserTab, title: str):
        """Tab-Titel aktualisieren"""
        index = self.tab_widget.indexOf(tab)
        if index >= 0:
            # Titel kürzen wenn zu lang
            short_title = title[:25] + "..." if len(title) > 25 else title
            self.tab_widget.setTabText(index, short_title)
            self.tab_widget.setTabToolTip(index, title)

    def on_tab_changed(self, index: int):
        """Tab gewechselt"""
        tab = self.tab_widget.widget(index)
        if tab:
            url = tab.get_url()
            self.url_bar.setText(url)
            self.update_bookmark_button(url)
            # Focus web view to enable input
            if hasattr(tab, 'focus_web_view'):
                QTimer.singleShot(50, tab.focus_web_view)

    def on_url_changed(self, url: str):
        """URL im aktuellen Tab geändert"""
        if self.tab_widget.currentWidget():
            current_url = self.current_tab().get_url()
            self.url_bar.setText(current_url)
            self.url_changed.emit(current_url)
            self.update_bookmark_button(current_url)

    def on_loading_progress(self, progress: int):
        """Lade-Fortschritt"""
        if progress < 100:
            self.progress.show()
            self.progress.setValue(progress)
        else:
            self.progress.hide()

    def update_bookmark_button(self, url: str):
        """Bookmark-Button Status aktualisieren"""
        if self.bookmark_manager.is_bookmarked(url):
            self.bookmark_btn.setText("⭐")
            self.bookmark_btn.setToolTip("Lesezeichen entfernen")
        else:
            self.bookmark_btn.setText("☆")
            self.bookmark_btn.setToolTip("Lesezeichen hinzufügen")

    def toggle_bookmark(self):
        """Lesezeichen hinzufügen/entfernen"""
        tab = self.current_tab()
        if not tab:
            return

        url = tab.get_url()
        title = tab.get_title()

        if self.bookmark_manager.is_bookmarked(url):
            self.bookmark_manager.remove(url)
            self.bookmark_btn.setText("☆")
            self.bookmark_btn.setToolTip("Lesezeichen hinzufügen")
        else:
            # Titel bearbeiten?
            new_title, ok = QInputDialog.getText(
                self, "Lesezeichen hinzufügen",
                "Titel:", text=title
            )
            if ok:
                self.bookmark_manager.add(new_title or title, url)
                self.bookmark_btn.setText("⭐")
                self.bookmark_btn.setToolTip("Lesezeichen entfernen")

        # Lesezeichen-Leiste aktualisieren
        self.update_bookmark_bar()

    def show_bookmarks(self):
        """Lesezeichen-Dialog anzeigen"""
        dialog = BookmarkDialog(self.bookmark_manager, self)
        dialog.bookmark_selected.connect(self.navigate)
        dialog.exec()
        # Lesezeichen-Leiste aktualisieren (falls Lesezeichen gelöscht wurden)
        self.update_bookmark_bar()

    def navigate(self, url: str):
        """Im aktuellen Tab navigieren"""
        tab = self.current_tab()
        if tab:
            tab.navigate(url)

    def navigate_from_bar(self):
        """Navigation aus URL-Bar"""
        url = self.url_bar.text().strip()
        if url:
            # Prüfen ob Suche oder URL
            if " " in url or "." not in url:
                # Suche mit konfigurierter Suchmaschine
                import urllib.parse
                search_url = self.SEARCH_ENGINES.get(self.search_engine, self.SEARCH_ENGINES["Google"])
                url = search_url.format(urllib.parse.quote_plus(url))
            self.navigate(url)

    def go_back(self):
        """Zurück navigieren"""
        tab = self.current_tab()
        if tab:
            tab.web_view.back()

    def go_forward(self):
        """Vorwärts navigieren"""
        tab = self.current_tab()
        if tab:
            tab.web_view.forward()

    def refresh(self):
        """Seite neu laden"""
        tab = self.current_tab()
        if tab:
            tab.web_view.reload()

    def update_bookmark_bar(self):
        """Lesezeichen-Schnellzugriffsleiste aktualisieren mit Favoriten und Overflow-Menü"""
        # Alte Buttons entfernen
        while self.bookmark_bar_layout.count():
            item = self.bookmark_bar_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self._bookmark_buttons = []
        self._hidden_bookmarks = []

        btn_style = """
            QPushButton {
                background-color: #313244;
                color: #cdd6f4;
                border: none;
                border-radius: 4px;
                padding: 4px 10px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #45475a;
            }
        """

        pin_btn_style = """
            QPushButton {
                background-color: #3b3d4f;
                color: #f9e2af;
                border: 1px solid #f9e2af;
                border-radius: 4px;
                padding: 4px 10px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #45475a;
            }
        """

        # Favoriten zuerst (oder alle Lesezeichen wenn keine Favoriten)
        favorites = self.bookmark_manager.get_favorites()
        if not favorites:
            favorites = self.bookmark_manager.get_all()[:8]

        for bookmark in favorites[:10]:
            title = bookmark.get('title', 'Unbenannt')[:18]
            url = bookmark.get('url', '')
            is_pinned = self.bookmark_manager.is_pinned(url)

            # Gepinnte Lesezeichen haben ein spezielles Design
            icon = "📌" if is_pinned else "⭐"
            btn = QPushButton(f"{icon} {title}")
            btn.setStyleSheet(pin_btn_style if is_pinned else btn_style)
            btn.setToolTip(url)

            # Left click - open in current tab
            btn.clicked.connect(lambda checked, u=url: self.navigate(u))

            # Right click context menu
            btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            btn.customContextMenuRequested.connect(
                lambda pos, u=url, t=title, b=btn: self._show_bookmark_context_menu(pos, u, t, b)
            )

            self.bookmark_bar_layout.addWidget(btn)
            self._bookmark_buttons.append((btn, bookmark))

        # Add-to-favorites button
        add_fav_btn = QPushButton("➕")
        add_fav_btn.setFixedSize(24, 24)
        add_fav_btn.setStyleSheet(btn_style)
        add_fav_btn.setToolTip("Aktuelle Seite zu Favoriten hinzufügen")
        add_fav_btn.clicked.connect(self._add_current_to_favorites)
        self.bookmark_bar_layout.addWidget(add_fav_btn)

        # Overflow-Button (immer sichtbar)
        self.overflow_btn = OverflowMenuButton()
        self.overflow_btn.set_browser_widget(self)
        self.bookmark_bar_layout.addWidget(self.overflow_btn)

        # Stretch am Ende
        self.bookmark_bar_layout.addStretch()

        # Overflow-Check nach Layout-Update
        QTimer.singleShot(100, self._check_bookmark_overflow)

    def _show_bookmark_context_menu(self, pos, url: str, title: str, button: QPushButton):
        """Kontextmenü für Lesezeichen-Button anzeigen"""
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #1e1e2e;
                color: #cdd6f4;
                border: 1px solid #45475a;
                border-radius: 4px;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 20px;
                border-radius: 3px;
            }
            QMenu::item:selected {
                background-color: #45475a;
            }
        """)

        # Open in current tab
        action_open = menu.addAction("🔗 Öffnen")
        action_open.triggered.connect(lambda: self.navigate(url))

        # Open in new tab
        action_new_tab = menu.addAction("📑 In neuem Tab öffnen")
        action_new_tab.triggered.connect(lambda: self.add_tab(url))

        menu.addSeparator()

        # Add/Remove from favorites
        if self.bookmark_manager.is_favorite(url):
            action_fav = menu.addAction("💔 Aus Favoriten entfernen")
            action_fav.triggered.connect(lambda: self._remove_from_favorites(url))
        else:
            action_fav = menu.addAction("⭐ Zu Favoriten hinzufügen")
            action_fav.triggered.connect(lambda: self._add_to_favorites(url, title))

        # Pin/Unpin bookmark
        if self.bookmark_manager.is_pinned(url):
            action_pin = menu.addAction("📌 Pin entfernen")
            action_pin.triggered.connect(lambda: self._toggle_pin(url))
        else:
            action_pin = menu.addAction("📌 Pinnen (im Overflow-Menü)")
            action_pin.triggered.connect(lambda: self._toggle_pin(url))

        menu.addSeparator()

        # Remove bookmark
        action_remove = menu.addAction("🗑️ Lesezeichen entfernen")
        action_remove.triggered.connect(lambda: self._remove_bookmark(url))

        # Show menu at button position
        menu.exec(button.mapToGlobal(pos))

    def _add_current_to_favorites(self):
        """Aktuelle Seite zu Favoriten hinzufügen"""
        tab = self.current_tab()
        if tab:
            url = tab.web_view.url().toString()
            title = tab.web_view.title() or url
            if self.bookmark_manager.add_favorite(url, title):
                # Also add as bookmark if not exists
                if not self.bookmark_manager.is_bookmarked(url):
                    self.bookmark_manager.add(title, url)
                self.update_bookmark_bar()

    def _add_to_favorites(self, url: str, title: str):
        """URL zu Favoriten hinzufügen"""
        self.bookmark_manager.add_favorite(url, title)
        self.update_bookmark_bar()

    def _remove_from_favorites(self, url: str):
        """URL aus Favoriten entfernen"""
        self.bookmark_manager.remove_favorite(url)
        self.update_bookmark_bar()

    def _remove_bookmark(self, url: str):
        """Lesezeichen entfernen"""
        self.bookmark_manager.remove(url)
        self.bookmark_manager.remove_favorite(url)  # Also remove from favorites
        self.update_bookmark_bar()
        self.update_bookmark_button()  # Update star icon

    def _toggle_pin(self, url: str):
        """Pin-Status eines Lesezeichens umschalten"""
        self.bookmark_manager.toggle_pin(url)
        self.update_bookmark_bar()

    def _check_bookmark_overflow(self):
        """
        Prüft welche Lesezeichen-Buttons überlaufen und versteckt sie.
        Versteckte Lesezeichen werden im Overflow-Menü angezeigt.
        """
        if not self._bookmark_buttons:
            return

        # Verfügbare Breite berechnen (minus Overflow-Button und Add-Button)
        bar_width = self.bookmark_bar.width()
        reserved_width = 100  # Platz für ➕ und ≡ Buttons

        available_width = bar_width - reserved_width
        current_width = 0
        self._hidden_bookmarks = []

        for btn, bookmark in self._bookmark_buttons:
            btn_width = btn.sizeHint().width() + 8  # +8 für spacing

            if current_width + btn_width <= available_width:
                # Button passt noch
                btn.setVisible(True)
                current_width += btn_width
            else:
                # Button passt nicht mehr - verstecken
                btn.setVisible(False)
                self._hidden_bookmarks.append(bookmark)

        # Overflow-Menü mit versteckten Bookmarks aktualisieren
        if self.overflow_btn:
            self.overflow_btn.set_hidden_bookmarks(self._hidden_bookmarks)

            # Visuelles Feedback wenn Overflow-Items vorhanden
            if self._hidden_bookmarks:
                self.overflow_btn.setStyleSheet("""
                    QToolButton {
                        background-color: #89b4fa;
                        color: #1e1e2e;
                        border: none;
                        border-radius: 4px;
                        font-weight: bold;
                        font-size: 14px;
                    }
                    QToolButton:hover {
                        background-color: #b4befe;
                    }
                    QToolButton::menu-indicator {
                        image: none;
                    }
                """)
                self.overflow_btn.setToolTip(f"Overflow-Menü ({len(self._hidden_bookmarks)} versteckte Lesezeichen)")
            else:
                self.overflow_btn.setStyleSheet("""
                    QToolButton {
                        background-color: #45475a;
                        color: #cdd6f4;
                        border: none;
                        border-radius: 4px;
                        font-weight: bold;
                        font-size: 14px;
                    }
                    QToolButton:hover {
                        background-color: #585b70;
                    }
                    QToolButton::menu-indicator {
                        image: none;
                    }
                """)
                self.overflow_btn.setToolTip("Overflow-Menü (Tabs & Lesezeichen)")

    def resizeEvent(self, event):
        """Bei Größenänderung Overflow neu prüfen"""
        super().resizeEvent(event)
        # Verzögerung um Layout-Thrashing zu vermeiden
        QTimer.singleShot(50, self._check_bookmark_overflow)

    def setup_shortcuts(self):
        """Setup keyboard shortcuts for browser - using WidgetWithChildrenShortcut context"""
        # Use WidgetWithChildrenShortcut so shortcuts work when browser or children have focus
        # but don't interfere with web page input
        context = Qt.ShortcutContext.WidgetWithChildrenShortcut

        # Note: F5 is now global for lock screen, use Ctrl+R for refresh

        # F12 - Developer Tools
        shortcut = QShortcut(QKeySequence("F12"), self)
        shortcut.setContext(context)
        shortcut.activated.connect(self.toggle_dev_tools)

        # Ctrl+T - New Tab (handled via URL bar, not web view)
        shortcut = QShortcut(QKeySequence("Ctrl+T"), self.url_bar)
        shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
        shortcut.activated.connect(lambda: self.add_tab())

        # Ctrl+W - Close Tab (handled via URL bar)
        shortcut = QShortcut(QKeySequence("Ctrl+W"), self.url_bar)
        shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
        shortcut.activated.connect(self.close_current_tab)

        # Ctrl+L - Focus URL bar (global for browser widget)
        shortcut = QShortcut(QKeySequence("Ctrl+L"), self)
        shortcut.setContext(context)
        shortcut.activated.connect(self.focus_url_bar)

        # Ctrl+R - Reload (use Ctrl+R instead of F5 since F5 is global lock)
        shortcut = QShortcut(QKeySequence("Ctrl+R"), self.url_bar)
        shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
        shortcut.activated.connect(self.refresh)

    def toggle_dev_tools(self):
        """Toggle Developer Tools (F12)"""
        try:
            tab = self.current_tab()
            if not tab or not hasattr(tab, 'web_view'):
                logger.warning("No browser tab available for dev tools")
                return

            if self.dev_tools_visible and self.dev_tools_view:
                # Hide dev tools
                self.dev_tools_view.close()
                self.dev_tools_view.deleteLater()
                self.dev_tools_view = None
                self.dev_tools_visible = False
                logger.info("Dev tools closed")
            else:
                # Show dev tools
                self.dev_tools_view = QWebEngineView()
                self.dev_tools_view.setWindowTitle("Developer Tools - AILinux")
                self.dev_tools_view.setMinimumSize(800, 400)
                self.dev_tools_view.setStyleSheet("background: #1e1e2e;")

                # Connect dev tools to the current page
                if tab.web_view.page():
                    tab.web_view.page().setDevToolsPage(self.dev_tools_view.page())
                    self.dev_tools_view.show()
                    self.dev_tools_visible = True
                    logger.info("Dev tools opened")
        except Exception as e:
            logger.error(f"Error toggling dev tools: {e}")

    def close_current_tab(self):
        """Close the current tab"""
        index = self.tab_widget.currentIndex()
        if index >= 0:
            self.close_tab(index)

    def focus_url_bar(self):
        """Focus the URL bar"""
        self.url_bar.setFocus()
        self.url_bar.selectAll()
