"""
AILinux Key Capture Utilities
=============================

Provides key capture functionality for widgets with proper focus handling.
"""
import logging
from typing import Optional, Set, Dict, Callable
from dataclasses import dataclass

from PyQt6.QtCore import Qt, QEvent
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QWidget

from .shortcut_manager import ShortcutContext, get_shortcut_manager

logger = logging.getLogger("ailinux.key_capture")


@dataclass
class KeyBinding:
    """A key binding for a widget"""
    key: int
    modifiers: Qt.KeyboardModifier
    callback: Callable
    description: str = ""
    consume: bool = True  # If True, event is consumed and not propagated


class KeyCaptureMixin:
    """
    Mixin class for widgets that need custom key capture.

    Usage:
        class MyWidget(QWidget, KeyCaptureMixin):
            def __init__(self):
                super().__init__()
                self.init_key_capture(ShortcutContext.TERMINAL)

                # Register widget-specific bindings
                self.bind_key(Qt.Key.Key_Tab, self._handle_tab, "Insert tab")
                self.bind_key(Qt.Key.Key_Return, self._handle_enter, "Execute command")

            def keyPressEvent(self, event):
                if not self.handle_key_press(event):
                    super().keyPressEvent(event)
    """

    def init_key_capture(
        self,
        context: ShortcutContext,
        capture_all: bool = False
    ):
        """
        Initialize key capture for this widget.

        Args:
            context: The shortcut context for this widget
            capture_all: If True, capture all key events (for terminal-like widgets)
        """
        self._key_context = context
        self._key_bindings: Dict[tuple, KeyBinding] = {}
        self._capture_all = capture_all
        self._pass_through_keys: Set[int] = set()

        # Register with shortcut manager
        manager = get_shortcut_manager()
        if isinstance(self, QWidget):
            manager.register_widget_context(self, context)

    def bind_key(
        self,
        key: int,
        callback: Callable,
        description: str = "",
        modifiers: Qt.KeyboardModifier = Qt.KeyboardModifier.NoModifier,
        consume: bool = True
    ):
        """
        Bind a key to a callback for this widget.

        Args:
            key: Qt.Key value
            callback: Function to call
            description: Description for help
            modifiers: Required modifier keys
            consume: If True, don't propagate the event
        """
        # Convert modifiers to int value for dict key (PyQt6 compatible)
        mod_value = modifiers.value if hasattr(modifiers, 'value') else int(modifiers)
        binding_key = (key, mod_value)
        self._key_bindings[binding_key] = KeyBinding(
            key=key,
            modifiers=modifiers,
            callback=callback,
            description=description,
            consume=consume
        )

    def unbind_key(self, key: int, modifiers: Qt.KeyboardModifier = Qt.KeyboardModifier.NoModifier):
        """Remove a key binding"""
        mod_value = modifiers.value if hasattr(modifiers, 'value') else int(modifiers)
        binding_key = (key, mod_value)
        self._key_bindings.pop(binding_key, None)

    def set_pass_through(self, keys: Set[int]):
        """Set keys that should be passed through to parent"""
        self._pass_through_keys = keys

    def handle_key_press(self, event: QKeyEvent) -> bool:
        """
        Handle a key press event.
        Call this from keyPressEvent.

        Returns:
            True if the event was handled and should not propagate
        """
        key = event.key()
        modifiers = event.modifiers()

        # Check pass-through keys
        if key in self._pass_through_keys:
            return False

        # First check global shortcut manager for context shortcuts
        manager = get_shortcut_manager()
        if manager.handle_key_event(event, self._key_context):
            return True

        # Check local bindings
        # Try with exact modifiers
        mod_value = modifiers.value if hasattr(modifiers, 'value') else int(modifiers)
        binding_key = (key, mod_value)
        binding = self._key_bindings.get(binding_key)

        # If no exact match, try without modifiers for special keys
        if not binding and mod_value == 0:
            binding = self._key_bindings.get((key, 0))

        if binding:
            try:
                binding.callback()
                return binding.consume
            except Exception as e:
                logger.error(f"Key binding error for {key}: {e}")
                return False

        # If capture_all is set, consume all key events
        return self._capture_all

    def handle_event(self, event: QEvent) -> Optional[bool]:
        """
        Handle events that need to be intercepted before normal processing.
        Call this from event() method.

        Returns:
            True if handled, False if not handled, None to use default
        """
        if event.type() == QEvent.Type.KeyPress:
            key_event = event
            key = key_event.key()

            # Tab key needs special handling to prevent focus change
            if key == Qt.Key.Key_Tab:
                binding = self._key_bindings.get((Qt.Key.Key_Tab, 0))
                if binding:
                    try:
                        binding.callback()
                        return True
                    except Exception as e:
                        logger.error(f"Tab key error: {e}")

            # Backtab (Shift+Tab)
            elif key == Qt.Key.Key_Backtab:
                binding = self._key_bindings.get(
                    (Qt.Key.Key_Backtab, int(Qt.KeyboardModifier.ShiftModifier))
                )
                if not binding:
                    binding = self._key_bindings.get((Qt.Key.Key_Backtab, 0))
                if binding:
                    try:
                        binding.callback()
                        return True
                    except Exception as e:
                        logger.error(f"Backtab key error: {e}")

        return None

    def get_key_bindings_help(self) -> str:
        """Get help text for this widget's key bindings"""
        lines = []
        for (key, mods), binding in self._key_bindings.items():
            key_name = Qt.Key(key).name.replace("Key_", "")
            mod_str = ""
            # Convert mods to int for bitwise operations
            mods_int = mods.value if hasattr(mods, 'value') else mods
            ctrl_val = Qt.KeyboardModifier.ControlModifier.value if hasattr(Qt.KeyboardModifier.ControlModifier, 'value') else int(Qt.KeyboardModifier.ControlModifier)
            shift_val = Qt.KeyboardModifier.ShiftModifier.value if hasattr(Qt.KeyboardModifier.ShiftModifier, 'value') else int(Qt.KeyboardModifier.ShiftModifier)
            alt_val = Qt.KeyboardModifier.AltModifier.value if hasattr(Qt.KeyboardModifier.AltModifier, 'value') else int(Qt.KeyboardModifier.AltModifier)

            if mods_int & ctrl_val:
                mod_str += "Ctrl+"
            if mods_int & shift_val:
                mod_str += "Shift+"
            if mods_int & alt_val:
                mod_str += "Alt+"
            lines.append(f"{mod_str}{key_name}: {binding.description}")
        return "\n".join(lines)


class FocusAwareWidget(QWidget):
    """
    Base class for widgets that need focus-aware shortcut handling.
    Automatically notifies shortcut manager of focus changes.
    """

    def __init__(self, context: ShortcutContext, parent=None):
        super().__init__(parent)
        self._shortcut_context = context
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        # Register with shortcut manager
        manager = get_shortcut_manager()
        manager.register_widget_context(self, context)

    def focusInEvent(self, event):
        """Update shortcut context when this widget gets focus"""
        super().focusInEvent(event)
        manager = get_shortcut_manager()
        manager.set_context(self._shortcut_context)

    def focusOutEvent(self, event):
        """Reset shortcut context when this widget loses focus"""
        super().focusOutEvent(event)
        # Don't reset to GLOBAL here - let the next widget set its context
