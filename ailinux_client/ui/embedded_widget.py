"""
Embedded Widget Host
====================

A widget that embeds external process windows using X11 window IDs.
This allows widgets running in separate processes to appear as part
of the main window.

Works on Linux/X11 using the XEmbed protocol via Qt's QWindow.fromWinId()
"""
import logging
from typing import Optional, Callable, Dict, Any

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PyQt6.QtGui import QWindow

logger = logging.getLogger("ailinux.embedded_widget")


class EmbeddedWidgetHost(QWidget):
    """
    A widget that embeds an external window from another process.

    This allows widgets running in separate processes to be seamlessly
    integrated into the main application window.

    Usage:
        host = EmbeddedWidgetHost()
        host.embed(window_id)  # window_id from the child process
    """

    # Signals
    embedded = pyqtSignal(int)  # Emitted when window is embedded (window_id)
    unembedded = pyqtSignal()   # Emitted when window is unembedded
    error = pyqtSignal(str)     # Emitted on error

    def __init__(self, parent: QWidget = None, placeholder_text: str = "Loading..."):
        super().__init__(parent)

        self._window_id: Optional[int] = None
        self._embedded_window: Optional[QWindow] = None
        self._container: Optional[QWidget] = None

        # Layout
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)

        # Placeholder shown while not embedded
        self._placeholder = QLabel(placeholder_text)
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._placeholder.setStyleSheet("""
            QLabel {
                background: #1e1e2e;
                color: #6c7086;
                font-size: 14px;
            }
        """)
        self._layout.addWidget(self._placeholder)

    def embed(self, window_id: int) -> bool:
        """
        Embed an external window by its window ID.

        Args:
            window_id: The X11 window ID (or Windows HWND) to embed

        Returns:
            True if embedding succeeded
        """
        if window_id == self._window_id:
            return True

        # Remove existing embedded window if any
        if self._container:
            self.unembed()

        try:
            # Create QWindow from external window ID
            self._embedded_window = QWindow.fromWinId(window_id)
            if not self._embedded_window:
                raise RuntimeError(f"Failed to create QWindow from window ID {window_id}")

            # Create container widget to host the QWindow
            self._container = QWidget.createWindowContainer(
                self._embedded_window,
                self,
                Qt.WindowType.ForeignWindow
            )

            # Hide placeholder and add container
            self._placeholder.hide()
            self._layout.addWidget(self._container)

            self._window_id = window_id
            logger.info(f"Embedded window {window_id}")
            self.embedded.emit(window_id)
            return True

        except Exception as e:
            logger.error(f"Failed to embed window {window_id}: {e}")
            self.error.emit(str(e))
            return False

    def unembed(self):
        """Remove the embedded window"""
        if self._container:
            self._layout.removeWidget(self._container)
            self._container.deleteLater()
            self._container = None
            self._embedded_window = None
            self._window_id = None

            # Show placeholder again
            self._placeholder.show()

            self.unembedded.emit()
            logger.info("Window unembedded")

    def is_embedded(self) -> bool:
        """Check if a window is currently embedded"""
        return self._container is not None

    def get_window_id(self) -> Optional[int]:
        """Get the embedded window's ID"""
        return self._window_id

    def resizeEvent(self, event):
        """Handle resize to update embedded window size"""
        super().resizeEvent(event)
        if self._container:
            self._container.resize(self.size())


class ProcessWidgetWrapper(QWidget):
    """
    Wrapper widget that manages a widget process and embeds it.

    Combines ProcessHost + EmbeddedWidgetHost for a complete solution.
    """

    # Signals
    ready = pyqtSignal()  # Emitted when widget is ready (embedded)
    error = pyqtSignal(str)
    event = pyqtSignal(str, dict)  # event_name, data

    def __init__(self, widget_type, parent: QWidget = None):
        super().__init__(parent)

        from ..core.widget_process import ProcessHost, WidgetType, WidgetProcessManager

        self.widget_type = widget_type
        self._process_host: Optional[ProcessHost] = None
        self._poll_timer: Optional[QTimer] = None

        # Layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Embedded host
        self._embedded_host = EmbeddedWidgetHost(
            self,
            placeholder_text=f"Starting {widget_type.name}..."
        )
        layout.addWidget(self._embedded_host)

    def start(self, config: Dict[str, Any] = None) -> bool:
        """Start the widget process and embed it"""
        from ..core.widget_process import ProcessHost, WidgetProcessManager

        # Get process class for this widget type
        process_class = WidgetProcessManager.PROCESS_CLASSES.get(self.widget_type)
        if not process_class:
            self.error.emit(f"Unknown widget type: {self.widget_type}")
            return False

        # Create and start process host
        self._process_host = ProcessHost(self.widget_type, process_class, config)

        if not self._process_host.start():
            self.error.emit("Failed to start widget process")
            return False

        # Embed the window
        window_id = self._process_host.window_id
        if window_id and self._embedded_host.embed(window_id):
            # Start polling for responses
            self._poll_timer = QTimer(self)
            self._poll_timer.timeout.connect(self._poll)
            self._poll_timer.start(100)  # Poll every 100ms

            self.ready.emit()
            return True

        self.error.emit("Failed to embed widget window")
        return False

    def stop(self):
        """Stop the widget process"""
        if self._poll_timer:
            self._poll_timer.stop()
            self._poll_timer = None

        self._embedded_host.unembed()

        if self._process_host:
            self._process_host.stop()
            self._process_host = None

    def send_command(self, action: str, data: Dict = None,
                    callback: Callable = None) -> Optional[int]:
        """Send a command to the widget process"""
        if self._process_host:
            return self._process_host.send_command(action, data, callback)
        return None

    def on_event(self, event_name: str, handler: Callable):
        """Register an event handler"""
        if self._process_host:
            self._process_host.on_event(event_name, handler)

    def _poll(self):
        """Poll for responses from widget process"""
        if self._process_host:
            self._process_host.poll()

            # Check if process is still running
            if not self._process_host.is_running():
                self.error.emit("Widget process terminated unexpectedly")
                self.stop()

    def is_running(self) -> bool:
        """Check if widget process is running"""
        return self._process_host is not None and self._process_host.is_running()


# ============================================================================
# Convenience factory functions
# ============================================================================

def create_process_browser(parent: QWidget = None, config: Dict = None) -> ProcessWidgetWrapper:
    """Create a browser widget running in a separate process"""
    from ..core.widget_process import WidgetType
    widget = ProcessWidgetWrapper(WidgetType.BROWSER, parent)
    widget.start(config)
    return widget


def create_process_terminal(parent: QWidget = None, config: Dict = None) -> ProcessWidgetWrapper:
    """Create a terminal widget running in a separate process"""
    from ..core.widget_process import WidgetType
    widget = ProcessWidgetWrapper(WidgetType.TERMINAL, parent)
    widget.start(config)
    return widget


def create_process_file_browser(parent: QWidget = None, config: Dict = None) -> ProcessWidgetWrapper:
    """Create a file browser widget running in a separate process"""
    from ..core.widget_process import WidgetType
    widget = ProcessWidgetWrapper(WidgetType.FILE_BROWSER, parent)
    widget.start(config)
    return widget


def create_process_chat(parent: QWidget = None, config: Dict = None) -> ProcessWidgetWrapper:
    """Create a chat widget running in a separate process"""
    from ..core.widget_process import WidgetType
    widget = ProcessWidgetWrapper(WidgetType.CHAT, parent)
    widget.start(config)
    return widget
