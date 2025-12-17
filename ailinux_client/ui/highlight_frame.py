"""
AILinux Highlight Frame
=======================

Provides visual highlighting for active/focused widgets with customizable
glow effects and borders.
"""
from PyQt6.QtWidgets import QFrame, QVBoxLayout, QWidget, QGraphicsDropShadowEffect
from PyQt6.QtCore import Qt, QPropertyAnimation, QEasingCurve, pyqtProperty
from PyQt6.QtGui import QColor, QPainter, QPen, QPainterPath
import logging

logger = logging.getLogger("ailinux.highlight_frame")


class HighlightFrame(QFrame):
    """
    A frame that wraps a widget and provides visual highlighting when active.

    Features:
    - Animated border glow when active
    - Customizable highlight color
    - Smooth transitions
    - Drop shadow effect option
    """

    def __init__(self, widget: QWidget = None, parent=None):
        super().__init__(parent)
        self._is_active = False
        self._highlight_color = QColor("#3b82f6")
        self._border_width = 2
        self._border_radius = 10
        self._glow_intensity = 0.0
        self._use_shadow = True

        # Setup layout
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(3, 3, 3, 3)
        self._layout.setSpacing(0)

        # Add widget if provided
        self._content_widget = None
        if widget:
            self.set_widget(widget)

        # Setup animation
        self._animation = QPropertyAnimation(self, b"glow_intensity")
        self._animation.setDuration(200)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)

        # Setup shadow effect
        self._shadow_effect = QGraphicsDropShadowEffect(self)
        self._shadow_effect.setBlurRadius(0)
        self._shadow_effect.setOffset(0, 0)
        self._shadow_effect.setColor(self._highlight_color)

        # Base style
        self.setStyleSheet("""
            HighlightFrame {
                background: transparent;
                border: none;
            }
        """)

    def set_widget(self, widget: QWidget):
        """Set the content widget"""
        if self._content_widget:
            self._layout.removeWidget(self._content_widget)

        self._content_widget = widget
        self._layout.addWidget(widget)

    def widget(self) -> QWidget:
        """Get the content widget"""
        return self._content_widget

    def set_highlight_color(self, color: QColor):
        """Set the highlight color"""
        if isinstance(color, str):
            color = QColor(color)
        self._highlight_color = color
        self._shadow_effect.setColor(color)
        self.update()

    def set_border_radius(self, radius: int):
        """Set border radius"""
        self._border_radius = radius
        self.update()

    def set_border_width(self, width: int):
        """Set border width"""
        self._border_width = width
        self.update()

    def set_use_shadow(self, use_shadow: bool):
        """Enable/disable shadow glow effect"""
        self._use_shadow = use_shadow
        if use_shadow and self._is_active:
            self.setGraphicsEffect(self._shadow_effect)
        else:
            self.setGraphicsEffect(None)

    @pyqtProperty(float)
    def glow_intensity(self):
        return self._glow_intensity

    @glow_intensity.setter
    def glow_intensity(self, value):
        self._glow_intensity = value
        if self._use_shadow:
            self._shadow_effect.setBlurRadius(value * 20)
        self.update()

    def set_active(self, active: bool):
        """Set active state with animation"""
        if active == self._is_active:
            return

        self._is_active = active

        # Animate glow
        self._animation.stop()
        if active:
            self._animation.setStartValue(self._glow_intensity)
            self._animation.setEndValue(1.0)
            if self._use_shadow:
                self.setGraphicsEffect(self._shadow_effect)
        else:
            self._animation.setStartValue(self._glow_intensity)
            self._animation.setEndValue(0.0)

        self._animation.start()

        # Update immediately
        self.update()

    def is_active(self) -> bool:
        """Check if frame is active"""
        return self._is_active

    def paintEvent(self, event):
        """Custom paint with highlight border"""
        super().paintEvent(event)

        if self._glow_intensity <= 0:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Calculate color with intensity
        color = QColor(self._highlight_color)
        color.setAlphaF(self._glow_intensity * 0.8)

        # Draw rounded border
        pen = QPen(color, self._border_width)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        # Create rounded rect path
        rect = self.rect().adjusted(
            self._border_width // 2,
            self._border_width // 2,
            -self._border_width // 2,
            -self._border_width // 2
        )

        path = QPainterPath()
        path.addRoundedRect(rect.toRectF(), self._border_radius, self._border_radius)
        painter.drawPath(path)

        painter.end()


class HighlightManager:
    """
    Manages highlight frames for multiple widgets.

    Usage:
        manager = HighlightManager()
        manager.add_widget(terminal_widget, "terminal")
        manager.add_widget(chat_widget, "chat")

        # Set active widget
        manager.set_active("terminal")
    """

    def __init__(self, highlight_color: str = "#3b82f6"):
        self._frames: dict[str, HighlightFrame] = {}
        self._active_name: str = None
        self._highlight_color = QColor(highlight_color)

    def add_widget(self, widget: QWidget, name: str) -> HighlightFrame:
        """
        Wrap a widget in a HighlightFrame.

        Returns the HighlightFrame (use this instead of the original widget
        when adding to layouts).
        """
        frame = HighlightFrame(widget)
        frame.set_highlight_color(self._highlight_color)
        self._frames[name] = frame
        return frame

    def get_frame(self, name: str) -> HighlightFrame:
        """Get the highlight frame for a widget"""
        return self._frames.get(name)

    def get_widget(self, name: str) -> QWidget:
        """Get the content widget by name"""
        frame = self._frames.get(name)
        if frame:
            return frame.widget()
        return None

    def set_active(self, name: str):
        """Set the active widget by name"""
        if name == self._active_name:
            return

        # Deactivate previous
        if self._active_name and self._active_name in self._frames:
            self._frames[self._active_name].set_active(False)

        # Activate new
        if name in self._frames:
            self._frames[name].set_active(True)
            self._active_name = name
        else:
            self._active_name = None

    def set_active_by_widget(self, widget: QWidget):
        """Set active based on which widget (or its child) has focus"""
        for name, frame in self._frames.items():
            content = frame.widget()
            if content == widget or (content and content.isAncestorOf(widget)):
                self.set_active(name)
                return

        # No match found - deactivate all
        self.clear_active()

    def clear_active(self):
        """Clear active state from all frames"""
        if self._active_name and self._active_name in self._frames:
            self._frames[self._active_name].set_active(False)
        self._active_name = None

    def set_highlight_color(self, color: str):
        """Set highlight color for all frames"""
        self._highlight_color = QColor(color)
        for frame in self._frames.values():
            frame.set_highlight_color(self._highlight_color)

    def get_all_names(self) -> list:
        """Get list of all registered widget names"""
        return list(self._frames.keys())
