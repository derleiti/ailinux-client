"""
AILinux Chat Widget
===================

Chat interface with AI models.
Tier-based access:
- Tier 0: Ollama models only
- Tier 0.5+: Ollama + server models
- Tier 1+: Cloud models (token-based)
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit,
    QLineEdit, QPushButton, QComboBox, QLabel, QScrollArea,
    QListWidget, QListWidgetItem, QFrame, QApplication,
    QStyledItemDelegate, QStyle, QPlainTextEdit, QSizePolicy
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSize, QTimer, QEvent, QSettings
from PyQt6.QtGui import QTextCursor, QFont, QColor, QPalette, QFontMetrics, QKeyEvent
import logging
from typing import Optional, List, Dict, Any

from ..core.tier_manager import get_tier_manager
from ..core.markdown_renderer import render_markdown, get_renderer
from ..core.planning_prompt import get_planning_system_prompt, DEFAULT_SYSTEM_PROMPT

logger = logging.getLogger("ailinux.chat_widget")


class SearchableModelSelector(QWidget):
    """
    Searchable model selector with dropdown popup.

    Features:
    - Search input with filtering
    - Mouse wheel browsing
    - Grouped models (Ollama/Cloud)
    - Visual tier indicators
    """

    model_changed = pyqtSignal(object)  # Emits model data

    def __init__(self, parent=None):
        super().__init__(parent)
        self.models: List[Dict[str, Any]] = []
        self.filtered_models: List[Dict[str, Any]] = []
        self.current_model: Optional[Dict[str, Any]] = None
        self.popup_visible = False

        self._setup_ui()

    def _setup_ui(self):
        """Setup UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Main button that shows current selection
        self.select_btn = QPushButton("Auto (Default)")
        self.select_btn.setMinimumWidth(120)
        self.select_btn.setStyleSheet("""
            QPushButton {
                background: #333;
                color: #e0e0e0;
                border: 1px solid #444;
                border-radius: 4px;
                padding: 8px 12px;
                text-align: left;
                font-size: 12px;
            }
            QPushButton:hover {
                background: #3a3a3a;
                border-color: #555;
            }
            QPushButton::menu-indicator {
                subcontrol-position: right center;
                right: 8px;
            }
        """)
        self.select_btn.clicked.connect(self._toggle_popup)
        layout.addWidget(self.select_btn)

        # Popup frame
        self.popup = QFrame(self, Qt.WindowType.Popup)
        self.popup.setStyleSheet("""
            QFrame {
                background: #2a2a2a;
                border: 1px solid #444;
                border-radius: 6px;
            }
        """)
        popup_layout = QVBoxLayout(self.popup)
        popup_layout.setContentsMargins(8, 8, 8, 8)
        popup_layout.setSpacing(6)

        # Search input
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 Search models...")
        self.search_input.setStyleSheet("""
            QLineEdit {
                background: #333;
                color: #e0e0e0;
                border: 1px solid #444;
                border-radius: 4px;
                padding: 8px 10px;
                font-size: 12px;
            }
            QLineEdit:focus {
                border-color: #3b82f6;
            }
        """)
        self.search_input.textChanged.connect(self._filter_models)
        self.search_input.installEventFilter(self)
        popup_layout.addWidget(self.search_input)

        # Model list
        self.model_list = QListWidget()
        self.model_list.setMinimumHeight(300)
        self.model_list.setMinimumWidth(350)
        self.model_list.setStyleSheet("""
            QListWidget {
                background: #252525;
                color: #e0e0e0;
                border: 1px solid #333;
                border-radius: 4px;
                padding: 4px;
                font-size: 12px;
            }
            QListWidget::item {
                padding: 8px 10px;
                border-radius: 4px;
                margin: 2px 0;
            }
            QListWidget::item:hover {
                background: #3a3a3a;
            }
            QListWidget::item:selected {
                background: #3b82f6;
                color: white;
            }
            QListWidget::item:disabled {
                color: #666;
            }
        """)
        self.model_list.itemClicked.connect(self._on_item_clicked)
        self.model_list.itemDoubleClicked.connect(self._on_item_double_clicked)
        popup_layout.addWidget(self.model_list)

        # Info label
        self.info_label = QLabel()
        self.info_label.setStyleSheet("color: #888; font-size: 11px; padding: 4px;")
        popup_layout.addWidget(self.info_label)

        self.popup.hide()

    def eventFilter(self, obj, event):
        """Handle keyboard events in search"""
        if obj == self.search_input and event.type() == QEvent.Type.KeyPress:
            key = event.key()
            if key == Qt.Key.Key_Down:
                self.model_list.setFocus()
                if self.model_list.count() > 0:
                    self.model_list.setCurrentRow(0)
                return True
            elif key == Qt.Key.Key_Escape:
                self._hide_popup()
                return True
            elif key == Qt.Key.Key_Return:
                if self.model_list.currentItem():
                    self._on_item_double_clicked(self.model_list.currentItem())
                return True
        return super().eventFilter(obj, event)

    def wheelEvent(self, event):
        """Handle mouse wheel for quick model switching"""
        if not self.popup_visible:
            # Cycle through models with wheel
            delta = event.angleDelta().y()
            if delta != 0 and self.models:
                current_idx = -1
                if self.current_model:
                    for i, m in enumerate(self.models):
                        if m.get('id') == self.current_model.get('id'):
                            current_idx = i
                            break

                if delta > 0:  # Scroll up = previous
                    new_idx = max(0, current_idx - 1)
                else:  # Scroll down = next
                    new_idx = min(len(self.models) - 1, current_idx + 1)

                # Skip headers
                while new_idx < len(self.models) and self.models[new_idx].get('is_header'):
                    new_idx += 1 if delta < 0 else -1

                if 0 <= new_idx < len(self.models):
                    model = self.models[new_idx]
                    if not model.get('is_header') and not model.get('locked'):
                        self._select_model(model)

            event.accept()
        else:
            super().wheelEvent(event)

    def set_models(self, models: List[Dict[str, Any]]):
        """Set available models"""
        self.models = models
        self.filtered_models = models.copy()
        self._update_list()

    def _toggle_popup(self):
        """Toggle popup visibility"""
        if self.popup_visible:
            self._hide_popup()
        else:
            self._show_popup()

    def _show_popup(self):
        """Show popup"""
        # Position popup below button
        pos = self.select_btn.mapToGlobal(self.select_btn.rect().bottomLeft())
        self.popup.move(pos)
        self.popup.show()
        self.popup_visible = True
        self.search_input.setFocus()
        self.search_input.clear()
        self._filter_models("")

    def _hide_popup(self):
        """Hide popup"""
        self.popup.hide()
        self.popup_visible = False

    def _filter_models(self, text: str):
        """Filter models by search text"""
        text = text.lower().strip()
        self.filtered_models = []

        for model in self.models:
            if model.get('is_header'):
                self.filtered_models.append(model)
            elif text == "" or text in model.get('name', '').lower():
                self.filtered_models.append(model)

        # Remove empty headers
        cleaned = []
        for i, model in enumerate(self.filtered_models):
            if model.get('is_header'):
                # Check if next non-header item exists
                has_items = False
                for j in range(i + 1, len(self.filtered_models)):
                    if self.filtered_models[j].get('is_header'):
                        break
                    has_items = True
                    break
                if has_items:
                    cleaned.append(model)
            else:
                cleaned.append(model)

        self.filtered_models = cleaned
        self._update_list()

    def _update_list(self):
        """Update list widget"""
        self.model_list.clear()

        for model in self.filtered_models:
            item = QListWidgetItem()

            if model.get('is_header'):
                # Header item
                item.setText(model['name'])
                item.setFlags(Qt.ItemFlag.NoItemFlags)
                item.setBackground(QColor("#1a1a1a"))
                font = item.font()
                font.setBold(True)
                item.setFont(font)
            else:
                # Model item
                name = model.get('name', 'Unknown')
                provider = model.get('provider', '')

                if model.get('locked'):
                    item.setText(f"🔒 {name}")
                    item.setForeground(QColor("#666"))
                elif model.get('local'):
                    item.setText(f"💻 {name}")
                else:
                    # Cloud model with provider icon
                    icons = {
                        'anthropic': '🟠',
                        'openai': '🟢',
                        'google': '🔵',
                        'mistral': '🟣',
                    }
                    icon = icons.get(provider, '☁️')
                    item.setText(f"{icon} {name}")

            item.setData(Qt.ItemDataRole.UserRole, model)
            self.model_list.addItem(item)

        # Update info
        total = len([m for m in self.filtered_models if not m.get('is_header')])
        self.info_label.setText(f"{total} models available • Scroll to browse")

    def _on_item_clicked(self, item: QListWidgetItem):
        """Handle single click - highlight"""
        model = item.data(Qt.ItemDataRole.UserRole)
        if model and not model.get('is_header'):
            self.model_list.setCurrentItem(item)

    def _on_item_double_clicked(self, item: QListWidgetItem):
        """Handle double click - select"""
        model = item.data(Qt.ItemDataRole.UserRole)
        if model and not model.get('is_header') and not model.get('locked'):
            self._select_model(model)
            self._hide_popup()

    def _select_model(self, model: Dict[str, Any]):
        """Select a model"""
        self.current_model = model

        # Update button text
        name = model.get('name', 'Unknown')
        if model.get('local'):
            self.select_btn.setText(f"💻 {name}")
        else:
            self.select_btn.setText(f"☁️ {name}")

        self.model_changed.emit(model.get('id'))

    def get_current_model(self) -> Optional[str]:
        """Get current model ID"""
        if self.current_model:
            return self.current_model.get('id')
        return None

    def get_current_model_data(self) -> Optional[Dict]:
        """Get current model data"""
        return self.current_model

    def set_auto(self):
        """Reset to auto selection"""
        self.current_model = None
        self.select_btn.setText("Auto (Default)")
        self.model_changed.emit(None)


class PromptInput(QPlainTextEdit):
    """
    Multi-line prompt input with Enter to send and Shift+Enter for newline.

    Features:
    - Enter sends message
    - Shift+Enter adds newline
    - Auto-resize up to 10 lines max height
    - Placeholder text
    """

    send_requested = pyqtSignal()

    # Max 10 lines (approx 22px per line + padding)
    MAX_LINES = 10
    LINE_HEIGHT = 22
    MIN_HEIGHT = 66  # 2 lines for better placeholder visibility
    MAX_HEIGHT = MIN_HEIGHT + (MAX_LINES - 2) * LINE_HEIGHT  # ~240px

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setPlaceholderText("Nachricht eingeben...")
        self.setMaximumHeight(self.MAX_HEIGHT)
        self.setMinimumHeight(self.MIN_HEIGHT)

        # Start with 2 lines height for better visibility
        self.setFixedHeight(self.MIN_HEIGHT)

        # Connect to auto-resize
        self.textChanged.connect(self._auto_resize)

        self.setStyleSheet("""
            QPlainTextEdit {
                background: rgba(20, 20, 30, 0.9);
                color: #e0e0e0;
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 8px;
                padding: 10px 12px;
                font-size: 13px;
                line-height: 1.4;
            }
            QPlainTextEdit:focus {
                border-color: rgba(59, 130, 246, 0.6);
                background: rgba(25, 25, 35, 0.95);
            }
        """)

    def keyPressEvent(self, event: QKeyEvent):
        """Handle Enter vs Shift+Enter"""
        if event.key() == Qt.Key.Key_Return or event.key() == Qt.Key.Key_Enter:
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                # Shift+Enter: Insert newline
                super().keyPressEvent(event)
            else:
                # Enter alone: Send message
                self.send_requested.emit()
        else:
            super().keyPressEvent(event)

    def _auto_resize(self):
        """Auto-resize based on content up to MAX_LINES"""
        # Count actual lines
        text = self.toPlainText()
        line_count = text.count('\n') + 1

        # Calculate height based on line count
        new_height = self.MIN_HEIGHT + max(0, line_count - 1) * self.LINE_HEIGHT

        # Clamp to min/max
        new_height = max(self.MIN_HEIGHT, min(self.MAX_HEIGHT, new_height))

        self.setFixedHeight(new_height)

    def get_text(self) -> str:
        """Get text content"""
        return self.toPlainText().strip()

    def clear_text(self):
        """Clear the input"""
        self.clear()
        self.setFixedHeight(self.MIN_HEIGHT)


class ChatWorker(QThread):
    """Background worker for chat requests with Planning Mode support and timing"""
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, api_client, message: str, model: str = None, system_prompt: str = None):
        super().__init__()
        self.api_client = api_client
        self.message = message
        self.model = model
        self.system_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT

    def run(self):
        import time
        try:
            start_time = time.time()
            result = self.api_client.chat(
                message=self.message,
                model=self.model,
                system_prompt=self.system_prompt
            )
            # Add response time to result
            result["response_time_ms"] = int((time.time() - start_time) * 1000)
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))


class ChatWidget(QWidget):
    """
    Chat interface widget

    Features:
    - Message history display
    - Input field with send button
    - Model selection
    - Loading indicator
    """

    def __init__(self, api_client, parent=None):
        super().__init__(parent)
        self.api_client = api_client
        self.worker: Optional[ChatWorker] = None
        self.messages: List[dict] = []
        self.settings = QSettings("AILinux", "Client")

        self._setup_ui()
        self._apply_theme_colors()

    def _setup_ui(self):
        """Setup UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Chat history
        self.chat_display = QTextEdit()
        self.chat_display.setReadOnly(True)
        self.chat_display.setFont(QFont("Monospace", 11))
        self.chat_display.setStyleSheet("""
            QTextEdit {
                background: rgba(15, 15, 25, 0.85);
                color: #e0e0e0;
                border: none;
                border-radius: 10px;
                padding: 12px;
                margin: 4px;
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
        layout.addWidget(self.chat_display, 1)

        # Input area container
        input_container = QWidget()
        input_container.setStyleSheet("""
            background: rgba(25, 25, 35, 0.9);
            border-radius: 10px;
            margin: 4px;
        """)
        input_container.setMaximumHeight(400)  # Max height for input area
        container_layout = QVBoxLayout(input_container)
        container_layout.setContentsMargins(10, 8, 10, 10)
        container_layout.setSpacing(6)

        # Row 1: Hint label (Enter/Shift+Enter explanation)
        hint_label = QLabel("Enter: Senden  •  Shift+Enter: Neue Zeile")
        hint_label.setStyleSheet("color: #666; font-size: 11px;")
        hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        container_layout.addWidget(hint_label)

        # Row 2: Model selector (full width)
        model_row = QWidget()
        model_row.setMaximumHeight(40)
        model_layout = QHBoxLayout(model_row)
        model_layout.setContentsMargins(0, 0, 0, 0)
        model_layout.setSpacing(8)

        model_label = QLabel("Modell:")
        model_label.setStyleSheet("color: #888; font-size: 12px;")
        model_label.setFixedWidth(50)
        model_layout.addWidget(model_label)

        self.model_selector = SearchableModelSelector()
        self.model_selector.setMaximumHeight(36)
        self._load_models()
        model_layout.addWidget(self.model_selector, 1)

        container_layout.addWidget(model_row)

        # Row 3: Prompt text field (expandable up to 10 lines)
        self.input_field = PromptInput()
        self.input_field.send_requested.connect(self._send_message)
        container_layout.addWidget(self.input_field)

        # Row 4: Full-width Send button
        self.send_btn = QPushButton("Senden")
        self.send_btn.setFixedHeight(38)
        self.send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.send_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 rgba(59, 130, 246, 0.9),
                    stop:1 rgba(99, 102, 241, 0.9));
                color: white;
                border: none;
                border-radius: 8px;
                padding: 10px 24px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 rgba(37, 99, 235, 1),
                    stop:1 rgba(79, 70, 229, 1));
            }
            QPushButton:pressed {
                background: rgba(29, 78, 216, 1);
            }
            QPushButton:disabled {
                background: rgba(60, 60, 70, 0.7);
                color: rgba(150, 150, 150, 0.7);
            }
        """)
        self.send_btn.clicked.connect(self._send_message)
        container_layout.addWidget(self.send_btn)

        # Row 5: Action buttons (Copy, CLI Agent, Settings)
        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        
        self.copy_btn = QPushButton("📋 Copy")
        self.copy_btn.setFixedHeight(32)
        self.copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.copy_btn.setStyleSheet("""
            QPushButton {
                background: rgba(60, 60, 70, 0.8);
                color: #a0a0a0;
                border: 1px solid #444;
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 12px;
            }
            QPushButton:hover {
                background: rgba(80, 80, 90, 1);
                color: white;
            }
        """)
        self.copy_btn.clicked.connect(self.copy_last_response)
        action_row.addWidget(self.copy_btn)
        
        self.cli_agent_btn = QPushButton("🚀 An CLI Agent")
        self.cli_agent_btn.setFixedHeight(32)
        self.cli_agent_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cli_agent_btn.setStyleSheet("""
            QPushButton {
                background: rgba(60, 60, 70, 0.8);
                color: #a0a0a0;
                border: 1px solid #444;
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 12px;
            }
            QPushButton:hover {
                background: rgba(59, 130, 246, 0.8);
                color: white;
            }
        """)
        self.cli_agent_btn.clicked.connect(lambda: self.send_to_cli_agent("claude-mcp"))
        action_row.addWidget(self.cli_agent_btn)
        
        self.planning_btn = QPushButton("🗺️ Planungsmodus")
        self.planning_btn.setFixedHeight(32)
        self.planning_btn.setCheckable(True)
        self.planning_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.planning_btn.setStyleSheet("""
            QPushButton {
                background: rgba(60, 60, 70, 0.8);
                color: #a0a0a0;
                border: 1px solid #444;
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 12px;
            }
            QPushButton:hover {
                background: rgba(34, 197, 94, 0.6);
                color: white;
            }
            QPushButton:checked {
                background: rgba(34, 197, 94, 0.8);
                color: white;
                border: 1px solid #22c55e;
            }
        """)
        self.planning_btn.setChecked(True)
        action_row.addWidget(self.planning_btn)
        
        action_row.addStretch()
        container_layout.addLayout(action_row)

        layout.addWidget(input_container)

    def _load_models(self):
        """Load available models from server (tier-based) or fallback to local"""
        models = []

        # Auto option (always first)
        models.append({
            'id': None,
            'name': 'Auto (Default)',
            'provider': 'auto',
            'local': False,
            'is_header': False,
        })

        # Try to get models from server first
        if self.api_client and self.api_client.is_authenticated():
            try:
                result = self.api_client._request("GET", "/v1/client/models")

                if result and "models" in result:
                    server_models = result.get("models", [])
                    tier = result.get("tier", "free")
                    tier_name = result.get("tier_name", "Free")
                    backend = result.get("backend", "ollama")

                    # Group by provider
                    ollama_models = []
                    cloud_models = []

                    for model_id in server_models:
                        if "/" in model_id:
                            provider, name = model_id.split("/", 1)
                        else:
                            provider = backend
                            name = model_id

                        model_data = {
                            'id': model_id,
                            'name': name,
                            'provider': provider,
                            'local': (provider == "ollama"),
                        }

                        if provider == "ollama":
                            ollama_models.append(model_data)
                        else:
                            cloud_models.append(model_data)

                    # Add Ollama header and models
                    if ollama_models:
                        models.append({
                            'name': f'── Ollama ({backend}) ──',
                            'is_header': True,
                        })
                        models.extend(ollama_models)

                    # Add Cloud header and models
                    if cloud_models:
                        models.append({
                            'name': f'── Cloud ({tier_name}) ──',
                            'is_header': True,
                        })
                        models.extend(cloud_models)

                    self.model_selector.set_models(models)
                    logger.info(f"Loaded {len(ollama_models)} Ollama + {len(cloud_models)} cloud models from server (tier: {tier})")
                    return

            except Exception as e:
                logger.warning(f"Failed to get models from server: {e}")

        # Fallback: Local Ollama models + tier_manager
        tier_mgr = get_tier_manager(self.api_client)
        ollama_models = self._get_ollama_models()
        model_groups = tier_mgr.get_model_groups(ollama_models)

        # Add Ollama models
        if model_groups["ollama"]:
            models.append({
                'name': '── Ollama (Local) ──',
                'is_header': True,
            })
            for model in model_groups["ollama"]:
                models.append({
                    'id': model['id'],
                    'name': model['name'],
                    'provider': 'ollama',
                    'local': True,
                    'size': model.get('size', ''),
                })

        # Add Cloud models (Tier 1+ only)
        if model_groups["cloud"]:
            can_use_cloud = tier_mgr.can_use_cloud_models()
            header_text = '── Cloud Models ──' if can_use_cloud else '── Cloud (Upgrade) 🔒 ──'
            models.append({
                'name': header_text,
                'is_header': True,
            })

            for model in model_groups["cloud"]:
                models.append({
                    'id': model['id'],
                    'name': model['name'],
                    'provider': model.get('provider', 'cloud'),
                    'local': False,
                    'locked': not model['available'],
                    'reason': model.get('reason', ''),
                })

        self.model_selector.set_models(models)
        logger.info(f"Loaded {len(model_groups.get('ollama', []))} Ollama + {len(model_groups.get('cloud', []))} cloud models (fallback)")


    def _get_ollama_models(self) -> list:
        """Get Ollama models from local server"""
        try:
            from ..core.ollama_client import OllamaClient
            ollama = OllamaClient()
            if not ollama.is_available():
                logger.info("Ollama not available")
                return []

            models = ollama.get_models()
            # Convert OllamaModel objects to dicts
            return [{"name": m.name, "id": m.name, "size": m.size} for m in models]
        except Exception as e:
            logger.warning(f"Failed to get Ollama models: {e}")
            return []

    def refresh_models(self):
        """Refresh model list (called after tier change)"""
        self._load_models()

    def _send_message(self):
        """Send message"""
        message = self.input_field.get_text()
        if not message:
            return

        # Get selected model from new selector
        model_data = self.model_selector.get_current_model_data()
        model = self.model_selector.get_current_model()

        # Check if model is locked (tier-restricted)
        if model_data and model_data.get('locked'):
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(
                self,
                "Tier 1+ Required",
                "Cloud models are available from Tier 1 (Pro).\n\n"
                "Upgrade at ailinux.me/pro to unlock this feature."
            )
            return

        # Check tier limits
        tier_mgr = get_tier_manager(self.api_client)
        if tier_mgr.has_request_limit():
            remaining = tier_mgr.get_remaining_requests()
            if remaining <= 0:
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.warning(
                    self,
                    "Daily Limit Reached",
                    f"You have reached your daily request limit.\n\n"
                    f"Upgrade to Tier 1 for unlimited requests."
                )
                return

        # Track request
        tier_mgr.track_request()

        # Add to display
        self._add_message("user", message)
        self.input_field.clear_text()

        # Disable input while processing
        self.input_field.setEnabled(False)
        self.send_btn.setEnabled(False)

        # Get system prompt based on planning mode
        system_prompt = None
        if hasattr(self, 'planning_btn') and self.planning_btn.isChecked():
            system_prompt = DEFAULT_SYSTEM_PROMPT
        
        # Start worker
        self.worker = ChatWorker(self.api_client, message, model, system_prompt)
        self.worker.finished.connect(self._on_response)
        self.worker.error.connect(self._on_error)
        self.worker.start()

    def _on_response(self, result: dict):
        """Handle response and update statusbar"""
        self.input_field.setEnabled(True)
        self.send_btn.setEnabled(True)

        response = result.get("response", "")
        model = result.get("model", "unknown")
        tokens_used = result.get("tokens_used", 0)
        response_time_ms = result.get("response_time_ms", 0)

        # Track token usage for cloud models
        if tokens_used > 0:
            tier_mgr = get_tier_manager(self.api_client)
            tier_mgr.track_tokens(tokens_used)

        # Update statusbar with response time and model
        main_window = self.window()
        if main_window and hasattr(main_window, "update_response_time"):
            main_window.update_response_time(response_time_ms, model)

        self._add_message("assistant", response, model)

    def _on_error(self, error: str):
        """Handle error"""
        self.input_field.setEnabled(True)
        self.send_btn.setEnabled(True)

        self._add_message("error", f"Error: {error}")

    def _add_message(self, role: str, content: str, model: str = None):
        """Add message to display with Markdown rendering for AI responses"""
        self.messages.append({"role": role, "content": content, "model": model})

        if role == "user":
            header = '<div style="margin: 10px 0;"><span style="color: #4ade80; font-weight: bold; font-size: 14px;">👤 Du:</span></div>'
            escaped = content.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            escaped = escaped.replace("\n", "<br>")
            body = f'<div style="margin-left: 10px; padding: 8px; background: #1a1a2e; border-radius: 8px; color: #e0e0e0;">{escaped}</div>'
            
        elif role == "assistant":
            model_str = f" ({model})" if model else ""
            header = f'<div style="margin: 10px 0;"><span style="color: #3b82f6; font-weight: bold; font-size: 14px;">🤖 NOVA{model_str}:</span></div>'
            body = render_markdown(content)
            
        else:
            header = '<div style="margin: 10px 0;"><span style="color: #ef4444; font-weight: bold; font-size: 14px;">⚠️ System:</span></div>'
            escaped = content.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            body = f'<div style="margin-left: 10px; padding: 8px; background: #2a1a1a; border-radius: 8px; color: #fca5a5;">{escaped}</div>'

        action_bar = ""
        if role == "assistant":
            action_bar = '<div style="margin: 8px 0 16px 10px;"><span style="color: #666; font-size: 11px;">[📋 Copy] [🚀 An CLI Agent] [💾 Speichern]</span></div>'

        html = f"{header}{body}{action_bar}<hr style='border-color: #333; margin: 16px 0;'>"

        cursor = self.chat_display.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertHtml(html)

        self.chat_display.verticalScrollBar().setValue(
            self.chat_display.verticalScrollBar().maximum()
        )
        
        if role == "assistant":
            self._last_ai_response = content
            self._last_ai_model = model

    def copy_last_response(self):
        """Copy last AI response to clipboard"""
        if hasattr(self, '_last_ai_response') and self._last_ai_response:
            QApplication.clipboard().setText(self._last_ai_response)
            logger.info("Response copied to clipboard")

    def send_to_cli_agent(self, agent_id: str = "claude-mcp"):
        """Send last AI response to CLI agent"""
        if hasattr(self, '_last_ai_response') and self._last_ai_response:
            try:
                renderer = get_renderer()
                code_blocks = renderer.extract_code_blocks(self._last_ai_response)
                
                if code_blocks:
                    message = code_blocks[0]["code"]
                else:
                    message = self._last_ai_response
                
                if self.api_client:
                    result = self.api_client._request("POST", f"/v1/cli-agents/{agent_id}/call", {
                        "message": message
                    })
                    logger.info(f"Sent to {agent_id}: {result}")
                    self._add_message("system", f"An {agent_id} gesendet!")
            except Exception as e:
                logger.error(f"Failed to send to CLI agent: {e}")
                self._add_message("error", f"Fehler: {e}")


    def focus_input(self):
        """Focus the input field"""
        self.input_field.setFocus()

    def clear_chat(self):
        """Clear chat history"""
        self.messages.clear()
        self.chat_display.clear()

    def apply_settings(self):
        """Apply settings from QSettings"""
        settings = QSettings("AILinux", "Client")

        # Default model
        default_model = settings.value("chat_default_model", "")
        if default_model and hasattr(self, 'model_selector'):
            # Try to select the default model
            try:
                self.model_selector.set_selection(default_model)
            except Exception:
                pass  # Model may not be in list

        # Font settings
        font_size = settings.value("chat_font_size", 12, type=int)
        if hasattr(self, 'chat_display'):
            font = self.chat_display.font()
            font.setPointSize(font_size)
            self.chat_display.setFont(font)

        if hasattr(self, 'input_field'):
            font = self.input_field.font()
            font.setPointSize(font_size)
            self.input_field.setFont(font)

        # Word wrap
        word_wrap = settings.value("chat_word_wrap", True, type=bool)
        if hasattr(self, 'chat_display'):
            self.chat_display.setLineWrapMode(
                QTextEdit.LineWrapMode.WidgetWidth if word_wrap else QTextEdit.LineWrapMode.NoWrap
            )

        # Apply theme colors
        self._apply_theme_colors()

    def _apply_theme_colors(self):
        """
        Apply theme colors from settings to all UI elements.
        Follows WCAG contrast guidelines for visibility.
        """
        # Read theme colors from settings
        primary = self.settings.value("theme_color_primary", "#3b82f6")
        secondary = self.settings.value("theme_color_secondary", "#6366f1")
        accent = self.settings.value("theme_color_accent", "#8b5cf6")
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
            # If contrast is poor, use white or black based on background
            return "#ffffff" if bg_lum < 0.5 else "#1a1a1a"

        # Ensure text contrast
        text_color = ensure_contrast(surface, text_color)

        surface_rgba = hex_to_rgba(surface, transparency)
        surface_darker = hex_to_rgba(surface, min(1.0, transparency + 0.1))

        # Chat display styling
        if hasattr(self, 'chat_display'):
            self.chat_display.setStyleSheet(f"""
                QTextEdit {{
                    background: {surface_rgba};
                    color: {text_color};
                    border: none;
                    border-radius: {border_radius}px;
                    padding: 12px;
                    margin: 4px;
                    selection-background-color: {primary};
                    selection-color: white;
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
            """)

        # Input field styling
        if hasattr(self, 'input_field'):
            self.input_field.setStyleSheet(f"""
                QPlainTextEdit {{
                    background: {surface_darker};
                    color: {text_color};
                    border: 1px solid rgba(255, 255, 255, 0.1);
                    border-radius: {border_radius - 2}px;
                    padding: 10px 12px;
                    font-size: 13px;
                    selection-background-color: {primary};
                    selection-color: white;
                }}
                QPlainTextEdit:focus {{
                    border-color: {primary};
                    background: {surface_rgba};
                }}
            """)

        # Send button styling with gradient
        if hasattr(self, 'send_btn'):
            # Parse primary and secondary for gradient
            self.send_btn.setStyleSheet(f"""
                QPushButton {{
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 {primary}, stop:1 {secondary});
                    color: white;
                    border: none;
                    border-radius: {border_radius - 2}px;
                    padding: 10px 24px;
                    font-weight: bold;
                    font-size: 14px;
                }}
                QPushButton:hover {{
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 {secondary}, stop:1 {accent});
                }}
                QPushButton:pressed {{
                    background: {accent};
                }}
                QPushButton:disabled {{
                    background: rgba(60, 60, 70, 0.7);
                    color: rgba(150, 150, 150, 0.7);
                }}
            """)

        # Model selector button
        if hasattr(self, 'model_selector') and hasattr(self.model_selector, 'select_btn'):
            self.model_selector.select_btn.setStyleSheet(f"""
                QPushButton {{
                    background: {surface_darker};
                    color: {text_color};
                    border: 1px solid rgba(255, 255, 255, 0.1);
                    border-radius: {border_radius - 4}px;
                    padding: 8px 12px;
                    text-align: left;
                    font-size: 12px;
                }}
                QPushButton:hover {{
                    background: {surface_rgba};
                    border-color: {primary};
                }}
            """)
