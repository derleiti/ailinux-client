"""
Tor Toggle Widget - UI für Tor-Modus im Browser

Features:
- Ein/Aus Toggle mit Status-Anzeige
- Farbcodierung (Grün=Tor, Rot=Direct)
- New Identity Button
- .onion Indicator
"""

from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QPushButton, QLabel, 
    QMenu, QMessageBox, QToolButton
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QAction
import logging

logger = logging.getLogger("ailinux.tor.ui")


class TorToggleWidget(QWidget):
    """
    Kompaktes Tor-Toggle Widget für die Browser-Navigation.
    
    Zeigt:
    - 🧅 = Tor aktiv (grün)
    - 🌐 = Direktverbindung (normal)
    - 🔄 = Verbindung wird aufgebaut
    """
    
    tor_toggled = pyqtSignal(bool)  # True = Tor ein
    new_identity_requested = pyqtSignal()
    
    STATUS_ICONS = {
        "disconnected": "🌐",
        "connecting": "🔄",
        "connected": "🧅",
        "error": "⚠️"
    }
    
    STATUS_COLORS = {
        "disconnected": "#6c7086",  # Grau
        "connecting": "#f9e2af",    # Gelb
        "connected": "#a6e3a1",     # Grün
        "error": "#f38ba8"          # Rot
    }
    
    def __init__(self, tor_manager=None, parent=None):
        super().__init__(parent)
        self.tor_manager = tor_manager
        self._status = "disconnected"
        self.setup_ui()
        
        # TorManager Signals verbinden
        if self.tor_manager:
            self.tor_manager.status_changed.connect(self.update_status)
            self.tor_manager.tor_error.connect(self.show_error)
    
    def setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        
        # Haupt-Toggle Button
        self.toggle_btn = QToolButton()
        self.toggle_btn.setText("🌐")
        self.toggle_btn.setToolTip("Tor-Modus: Aus\nKlicken zum Aktivieren")
        self.toggle_btn.setFixedSize(36, 28)
        self.toggle_btn.clicked.connect(self.toggle_tor)
        self.toggle_btn.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        
        # Kontext-Menü
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #1e1e2e;
                color: #cdd6f4;
                border: 1px solid #45475a;
                border-radius: 4px;
            }
            QMenu::item {
                padding: 8px 20px;
            }
            QMenu::item:selected {
                background-color: #45475a;
            }
        """)
        
        # Menü-Aktionen
        self.action_toggle = menu.addAction("🧅 Tor aktivieren")
        self.action_toggle.triggered.connect(self.toggle_tor)
        
        menu.addSeparator()
        
        self.action_new_id = menu.addAction("🔄 Neue Identität")
        self.action_new_id.triggered.connect(self.request_new_identity)
        self.action_new_id.setEnabled(False)
        
        self.action_check = menu.addAction("✅ Verbindung prüfen")
        self.action_check.triggered.connect(self.check_connection)
        
        menu.addSeparator()
        
        self.action_onion = menu.addAction("🧅 .onion Test-Seite")
        self.action_onion.triggered.connect(self.open_onion_test)
        self.action_onion.setEnabled(False)
        
        self.toggle_btn.setMenu(menu)
        
        self._apply_style()
        layout.addWidget(self.toggle_btn)
    
    def _apply_style(self):
        """Style basierend auf Status anwenden"""
        color = self.STATUS_COLORS.get(self._status, "#6c7086")
        icon = self.STATUS_ICONS.get(self._status, "🌐")
        
        self.toggle_btn.setText(icon)
        self.toggle_btn.setStyleSheet(f"""
            QToolButton {{
                background-color: {color}22;
                color: {color};
                border: 2px solid {color};
                border-radius: 6px;
                font-size: 16px;
                font-weight: bold;
            }}
            QToolButton:hover {{
                background-color: {color}44;
            }}
            QToolButton::menu-indicator {{
                image: none;
                width: 0px;
            }}
        """)
        
        # Tooltip aktualisieren
        status_text = {
            "disconnected": "Tor-Modus: Aus\nKlicken zum Aktivieren",
            "connecting": "Tor: Verbindung wird aufgebaut...",
            "connected": "Tor-Modus: Aktiv ✅\n.onion-Seiten verfügbar\nKlicken zum Deaktivieren",
            "error": "Tor: Fehler aufgetreten\nKlicken für Details"
        }
        self.toggle_btn.setToolTip(status_text.get(self._status, ""))
        
        # Menü-Aktionen aktualisieren
        if self._status == "connected":
            self.action_toggle.setText("🌐 Tor deaktivieren")
            self.action_new_id.setEnabled(True)
            self.action_onion.setEnabled(True)
        else:
            self.action_toggle.setText("🧅 Tor aktivieren")
            self.action_new_id.setEnabled(False)
            self.action_onion.setEnabled(False)
    
    def update_status(self, status: str):
        """Status aktualisieren"""
        self._status = status
        self._apply_style()
        logger.info(f"Tor toggle status updated: {status}")
    
    def toggle_tor(self):
        """Tor ein/ausschalten"""
        if not self.tor_manager:
            self.show_error("TorManager nicht verfügbar")
            return
        
        enabled = self.tor_manager.toggle()
        self.tor_toggled.emit(enabled)
    
    def request_new_identity(self):
        """Neue Tor-Identität anfordern"""
        if self.tor_manager and self.tor_manager.enabled:
            success = self.tor_manager.new_identity()
            if success:
                QMessageBox.information(
                    self, "Neue Identität",
                    "Neue Tor-Identität wurde angefordert.\n"
                    "Die IP-Adresse wird in wenigen Sekunden geändert."
                )
            else:
                QMessageBox.warning(
                    self, "Fehler",
                    "Konnte keine neue Identität anfordern."
                )
            self.new_identity_requested.emit()
    
    def check_connection(self):
        """Tor-Verbindung prüfen"""
        if not self.tor_manager:
            return
        
        if self.tor_manager.check_connection():
            QMessageBox.information(
                self, "Verbindung OK",
                "Tor-Verbindung funktioniert! ✅\n\n"
                "Du surfst jetzt anonym über das Tor-Netzwerk."
            )
        else:
            QMessageBox.warning(
                self, "Verbindung fehlgeschlagen",
                "Tor-Verbindung konnte nicht hergestellt werden.\n\n"
                "Mögliche Ursachen:\n"
                "- Tor ist nicht aktiv\n"
                "- Firewall blockiert Port 9050\n"
                "- Netzwerkprobleme"
            )
    
    def open_onion_test(self):
        """Test .onion Seite öffnen"""
        # Tor Project's offizielle .onion Seite
        test_url = "http://2gzyxa5ihm7nsggfxnu52rck2vv4rvmdlkiu3zzui5du4xyclen53wid.onion/"
        
        # Signal an Parent senden
        parent = self.parent()
        while parent:
            if hasattr(parent, 'navigate'):
                parent.navigate(test_url)
                break
            if hasattr(parent, 'add_tab'):
                parent.add_tab(test_url)
                break
            parent = parent.parent()
    
    def show_error(self, message: str):
        """Fehlermeldung anzeigen"""
        QMessageBox.critical(
            self, "Tor Fehler",
            f"Fehler bei der Tor-Verbindung:\n\n{message}\n\n"
            "Stelle sicher, dass Tor installiert ist:\n"
            "sudo apt install tor"
        )


class TorStatusIndicator(QLabel):
    """
    Kleiner Status-Indikator für .onion URLs.
    
    Zeigt an ob aktuelle Seite eine .onion-Adresse ist.
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(20, 20)
        self.hide()
    
    def check_url(self, url: str):
        """URL prüfen und Indikator anzeigen wenn .onion"""
        if ".onion" in url.lower():
            self.setText("🧅")
            self.setToolTip("Diese Seite ist ein Tor Hidden Service (.onion)")
            self.setStyleSheet("""
                QLabel {
                    background-color: #a6e3a122;
                    color: #a6e3a1;
                    border: 1px solid #a6e3a1;
                    border-radius: 4px;
                    padding: 2px;
                    font-size: 12px;
                }
            """)
            self.show()
        else:
            self.hide()
