"""
AILinux Login Dialog
====================

Simple login dialog with username/password.
"""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QMessageBox
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
import logging

logger = logging.getLogger("ailinux.login_dialog")


class LoginDialog(QDialog):
    """Login dialog for AILinux Client"""

    def __init__(self, api_client, parent=None):
        super().__init__(parent)
        self.api_client = api_client
        self.logged_in = False

        self._setup_ui()

    def _setup_ui(self):
        """Setup dialog UI"""
        self.setWindowTitle("AILinux Login")
        self.setFixedSize(350, 200)
        self.setStyleSheet("""
            QDialog {
                background: #1a1a1a;
            }
            QLabel {
                color: #e0e0e0;
            }
            QLineEdit {
                background: #2d2d2d;
                color: #e0e0e0;
                border: 1px solid #444;
                border-radius: 4px;
                padding: 8px;
                font-size: 14px;
            }
            QLineEdit:focus {
                border-color: #3b82f6;
            }
            QPushButton {
                background: #3b82f6;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 10px 20px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #2563eb;
            }
            QPushButton:pressed {
                background: #1d4ed8;
            }
            QPushButton#cancelBtn {
                background: #444;
            }
            QPushButton#cancelBtn:hover {
                background: #555;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(25, 25, 25, 25)

        # Title
        title = QLabel("AILinux Login")
        title.setFont(QFont("", 16, QFont.Weight.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        # Email
        self.email_input = QLineEdit()
        self.email_input.setPlaceholderText("Email")
        layout.addWidget(self.email_input)

        # Password
        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("Password")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.returnPressed.connect(self._login)
        layout.addWidget(self.password_input)

        # Buttons
        btn_layout = QHBoxLayout()

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setObjectName("cancelBtn")
        self.cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.cancel_btn)

        self.login_btn = QPushButton("Login")
        self.login_btn.clicked.connect(self._login)
        btn_layout.addWidget(self.login_btn)

        layout.addLayout(btn_layout)

    def _login(self):
        """Attempt login"""
        email = self.email_input.text().strip()
        password = self.password_input.text()

        if not email or not password:
            QMessageBox.warning(self, "Error", "Please enter email and password")
            return

        # Disable buttons during login
        self.login_btn.setEnabled(False)
        self.login_btn.setText("Logging in...")

        # Try login
        if self.api_client.login(email, password):
            self.logged_in = True
            self.accept()
        else:
            QMessageBox.critical(self, "Login Failed", "Invalid email or password")
            self.login_btn.setEnabled(True)
            self.login_btn.setText("Login")
            self.password_input.clear()
            self.password_input.setFocus()
