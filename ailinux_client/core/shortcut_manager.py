"""
AILinux Shortcut Manager
========================

Centralized keyboard shortcut management with:
- Global shortcuts (work everywhere)
- Context-aware shortcuts (active widget specific)
- Conflict detection
- Dynamic registration/unregistration
"""
import logging
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Set
from enum import Enum, auto

from PyQt6.QtCore import Qt, QObject, pyqtSignal
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import QWidget, QApplication

logger = logging.getLogger("ailinux.shortcut_manager")


class ShortcutContext(Enum):
    """Context in which a shortcut is active"""
    GLOBAL = auto()          # Always active
    TERMINAL = auto()        # Only when terminal is focused
    CHAT = auto()            # Only when chat is focused
    BROWSER = auto()         # Only when browser is focused
    FILE_BROWSER = auto()    # Only when file browser is focused
    EDITOR = auto()          # Only when editor is focused


@dataclass
class ShortcutInfo:
    """Information about a registered shortcut"""
    key_sequence: str
    callback: Callable
    context: ShortcutContext
    description: str = ""
    enabled: bool = True
    category: str = "General"


class ShortcutManager(QObject):
    """
    Centralized shortcut manager for the application.

    Features:
    - Global shortcuts that work regardless of focus
    - Context-aware shortcuts for specific widgets
    - Conflict detection and resolution
    - Easy registration/unregistration
    - Shortcut listing for help dialogs
    """

    # Signal emitted when shortcut is triggered
    shortcut_triggered = pyqtSignal(str, str)  # key_sequence, description

    # Signal for context change
    context_changed = pyqtSignal(ShortcutContext)

    def __init__(self, parent: QWidget = None):
        super().__init__(parent)
        self.parent_widget = parent

        # Registered shortcuts: key_sequence -> ShortcutInfo
        self._shortcuts: Dict[str, ShortcutInfo] = {}

        # Qt QShortcut objects for global shortcuts
        self._qt_shortcuts: Dict[str, QShortcut] = {}

        # Current active context
        self._current_context: ShortcutContext = ShortcutContext.GLOBAL

        # Widget to context mapping
        self._widget_contexts: Dict[int, ShortcutContext] = {}

        # Blocked shortcuts (temporarily disabled)
        self._blocked: Set[str] = set()

    def register(
        self,
        key_sequence: str,
        callback: Callable,
        context: ShortcutContext = ShortcutContext.GLOBAL,
        description: str = "",
        category: str = "General",
        replace: bool = False
    ) -> bool:
        """
        Register a keyboard shortcut.

        Args:
            key_sequence: Key combination (e.g., "Ctrl+Shift+T", "F1")
            callback: Function to call when shortcut is triggered
            context: When the shortcut should be active
            description: Human-readable description
            category: Category for grouping in help
            replace: If True, replace existing shortcut

        Returns:
            True if registered successfully
        """
        # Normalize key sequence
        key_sequence = self._normalize_key(key_sequence)

        # Check for conflicts
        if key_sequence in self._shortcuts and not replace:
            existing = self._shortcuts[key_sequence]
            if existing.context == context:
                logger.warning(
                    f"Shortcut conflict: {key_sequence} already registered "
                    f"for context {context.name}"
                )
                return False

        # Create shortcut info
        info = ShortcutInfo(
            key_sequence=key_sequence,
            callback=callback,
            context=context,
            description=description,
            category=category
        )

        self._shortcuts[key_sequence] = info

        # For global shortcuts, create QShortcut
        if context == ShortcutContext.GLOBAL and self.parent_widget:
            self._create_qt_shortcut(key_sequence, callback)

        logger.debug(f"Registered shortcut: {key_sequence} ({context.name})")
        return True

    def unregister(self, key_sequence: str) -> bool:
        """Unregister a shortcut"""
        key_sequence = self._normalize_key(key_sequence)

        if key_sequence in self._shortcuts:
            del self._shortcuts[key_sequence]

            # Remove Qt shortcut if exists
            if key_sequence in self._qt_shortcuts:
                self._qt_shortcuts[key_sequence].deleteLater()
                del self._qt_shortcuts[key_sequence]

            logger.debug(f"Unregistered shortcut: {key_sequence}")
            return True
        return False

    def _normalize_key(self, key_sequence: str) -> str:
        """Normalize key sequence for consistent comparison"""
        # Use Qt's normalization
        ks = QKeySequence(key_sequence)
        return ks.toString()

    def _create_qt_shortcut(self, key_sequence: str, callback: Callable):
        """Create a Qt QShortcut for global shortcuts"""
        if not self.parent_widget:
            return

        # Remove existing if any
        if key_sequence in self._qt_shortcuts:
            self._qt_shortcuts[key_sequence].deleteLater()

        shortcut = QShortcut(QKeySequence(key_sequence), self.parent_widget)
        shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
        shortcut.activated.connect(lambda: self._on_shortcut_activated(key_sequence))
        self._qt_shortcuts[key_sequence] = shortcut

    def _on_shortcut_activated(self, key_sequence: str):
        """Handle shortcut activation"""
        if key_sequence in self._blocked:
            return

        info = self._shortcuts.get(key_sequence)
        if info and info.enabled:
            # Check context
            if info.context == ShortcutContext.GLOBAL or info.context == self._current_context:
                try:
                    info.callback()
                    self.shortcut_triggered.emit(key_sequence, info.description)
                except Exception as e:
                    logger.error(f"Shortcut callback error: {e}")

    def handle_key_event(self, event, widget_context: ShortcutContext = None) -> bool:
        """
        Handle a key event from a widget.
        Call this from widget's keyPressEvent to handle context-specific shortcuts.

        Args:
            event: QKeyEvent
            widget_context: The context of the widget calling this

        Returns:
            True if the event was handled by a shortcut
        """
        # Build key sequence from event
        key = event.key()
        modifiers = event.modifiers()

        # Skip pure modifier keys
        if key in (Qt.Key.Key_Control, Qt.Key.Key_Shift, Qt.Key.Key_Alt, Qt.Key.Key_Meta):
            return False

        # Build sequence
        sequence_parts = []
        if modifiers & Qt.KeyboardModifier.ControlModifier:
            sequence_parts.append("Ctrl")
        if modifiers & Qt.KeyboardModifier.ShiftModifier:
            sequence_parts.append("Shift")
        if modifiers & Qt.KeyboardModifier.AltModifier:
            sequence_parts.append("Alt")
        if modifiers & Qt.KeyboardModifier.MetaModifier:
            sequence_parts.append("Meta")

        # Add key name
        key_seq = QKeySequence(key)
        key_name = key_seq.toString()
        if key_name:
            sequence_parts.append(key_name)

        key_sequence = "+".join(sequence_parts)
        key_sequence = self._normalize_key(key_sequence)

        # Check if we have a shortcut for this
        info = self._shortcuts.get(key_sequence)
        if info and info.enabled and key_sequence not in self._blocked:
            # Check context match
            if info.context == ShortcutContext.GLOBAL:
                # Global shortcuts are handled by QShortcut, skip here
                return False
            elif widget_context and info.context == widget_context:
                try:
                    info.callback()
                    self.shortcut_triggered.emit(key_sequence, info.description)
                    return True
                except Exception as e:
                    logger.error(f"Shortcut callback error: {e}")

        return False

    def set_context(self, context: ShortcutContext):
        """Set current active context"""
        if context != self._current_context:
            self._current_context = context
            self.context_changed.emit(context)

    def register_widget_context(self, widget: QWidget, context: ShortcutContext):
        """Register a widget's context for automatic context switching"""
        self._widget_contexts[id(widget)] = context

    def get_widget_context(self, widget: QWidget) -> Optional[ShortcutContext]:
        """Get the context for a widget"""
        return self._widget_contexts.get(id(widget))

    def block_shortcut(self, key_sequence: str):
        """Temporarily block a shortcut"""
        self._blocked.add(self._normalize_key(key_sequence))

    def unblock_shortcut(self, key_sequence: str):
        """Unblock a shortcut"""
        self._blocked.discard(self._normalize_key(key_sequence))

    def block_all(self):
        """Block all shortcuts (e.g., for modal dialogs)"""
        self._blocked = set(self._shortcuts.keys())

    def unblock_all(self):
        """Unblock all shortcuts"""
        self._blocked.clear()

    def enable_shortcut(self, key_sequence: str, enabled: bool = True):
        """Enable or disable a shortcut"""
        key_sequence = self._normalize_key(key_sequence)
        if key_sequence in self._shortcuts:
            self._shortcuts[key_sequence].enabled = enabled

    def get_shortcuts_by_category(self) -> Dict[str, List[ShortcutInfo]]:
        """Get all shortcuts grouped by category"""
        result: Dict[str, List[ShortcutInfo]] = {}
        for info in self._shortcuts.values():
            if info.category not in result:
                result[info.category] = []
            result[info.category].append(info)
        return result

    def get_shortcuts_by_context(self, context: ShortcutContext) -> List[ShortcutInfo]:
        """Get all shortcuts for a specific context"""
        return [info for info in self._shortcuts.values() if info.context == context]

    def get_all_shortcuts(self) -> List[ShortcutInfo]:
        """Get all registered shortcuts"""
        return list(self._shortcuts.values())

    def get_shortcuts_html(self) -> str:
        """Generate HTML help for all shortcuts"""
        categories = self.get_shortcuts_by_category()
        html = []

        for category, shortcuts in sorted(categories.items()):
            html.append(f"<h3>{category}</h3>")
            html.append("<table>")
            for info in sorted(shortcuts, key=lambda x: x.key_sequence):
                context_str = f" ({info.context.name})" if info.context != ShortcutContext.GLOBAL else ""
                html.append(
                    f"<tr><td><b>{info.key_sequence}</b></td>"
                    f"<td>{info.description}{context_str}</td></tr>"
                )
            html.append("</table>")

        return "\n".join(html)


# Singleton instance
_shortcut_manager: Optional[ShortcutManager] = None


def get_shortcut_manager(parent: QWidget = None) -> ShortcutManager:
    """Get or create the global shortcut manager"""
    global _shortcut_manager
    if _shortcut_manager is None:
        _shortcut_manager = ShortcutManager(parent)
    elif parent and _shortcut_manager.parent_widget is None:
        _shortcut_manager.parent_widget = parent
    return _shortcut_manager


def register_shortcut(
    key_sequence: str,
    callback: Callable,
    context: ShortcutContext = ShortcutContext.GLOBAL,
    description: str = "",
    category: str = "General"
) -> bool:
    """Convenience function to register a shortcut"""
    return get_shortcut_manager().register(
        key_sequence, callback, context, description, category
    )
