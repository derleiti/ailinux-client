"""
Widget Process Manager
======================

Multiprocessing infrastructure for running widgets in separate processes
while embedding them in the main window.

Benefits:
- Better performance (each widget has its own event loop)
- Crash isolation (widget crash doesn't bring down the whole app)
- Better resource management (each process can be prioritized)

Architecture:
- Main process: Main window, orchestrates widget processes
- Widget processes: Each widget type runs in its own process
- IPC: Uses multiprocessing.Queue for commands and responses
- Embedding: Uses X11 window IDs (XEmbed protocol on Linux)
"""
import os
import sys
import logging
import multiprocessing as mp
from multiprocessing import Process, Queue, Event
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, Callable, List
from enum import Enum, auto
import json
import time
import signal

logger = logging.getLogger("ailinux.widget_process")


class WidgetType(Enum):
    """Types of widgets that can run in separate processes"""
    BROWSER = auto()
    TERMINAL = auto()
    FILE_BROWSER = auto()
    CHAT = auto()


@dataclass
class IPCMessage:
    """Message format for inter-process communication"""
    msg_type: str  # 'command', 'response', 'event', 'error'
    action: str    # Action to perform or event name
    data: Dict[str, Any] = field(default_factory=dict)
    msg_id: int = 0
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict:
        return {
            'msg_type': self.msg_type,
            'action': self.action,
            'data': self.data,
            'msg_id': self.msg_id,
            'timestamp': self.timestamp
        }

    @classmethod
    def from_dict(cls, d: Dict) -> 'IPCMessage':
        return cls(
            msg_type=d.get('msg_type', 'command'),
            action=d.get('action', ''),
            data=d.get('data', {}),
            msg_id=d.get('msg_id', 0),
            timestamp=d.get('timestamp', time.time())
        )


class WidgetProcessBase:
    """
    Base class for widgets running in separate processes.

    Subclass this for each widget type (BrowserProcess, TerminalProcess, etc.)
    """

    def __init__(self, widget_type: WidgetType, cmd_queue: Queue, resp_queue: Queue,
                 shutdown_event: Event, config: Dict = None):
        self.widget_type = widget_type
        self.cmd_queue = cmd_queue
        self.resp_queue = resp_queue
        self.shutdown_event = shutdown_event
        self.config = config or {}
        self.window_id: Optional[int] = None
        self._running = False
        self._msg_counter = 0

    def run(self):
        """Main entry point for the widget process"""
        # Setup signal handlers
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)

        try:
            # Initialize PyQt in this process
            from PyQt6.QtWidgets import QApplication
            self.app = QApplication(sys.argv)

            # Create the widget
            self.widget = self._create_widget()
            self.widget.show()

            # Get window ID for embedding
            self.window_id = int(self.widget.winId())
            self._send_response('window_id', {'window_id': self.window_id})

            self._running = True

            # Setup command processing timer
            from PyQt6.QtCore import QTimer
            self.cmd_timer = QTimer()
            self.cmd_timer.timeout.connect(self._process_commands)
            self.cmd_timer.start(50)  # Check every 50ms

            # Run event loop
            self.app.exec()

        except Exception as e:
            logger.error(f"Widget process error: {e}")
            self._send_response('error', {'error': str(e)})
        finally:
            self._running = False

    def _create_widget(self):
        """Override in subclass to create the actual widget"""
        raise NotImplementedError

    def _process_commands(self):
        """Process pending commands from the main process"""
        if self.shutdown_event.is_set():
            self._shutdown()
            return

        try:
            while not self.cmd_queue.empty():
                msg_dict = self.cmd_queue.get_nowait()
                msg = IPCMessage.from_dict(msg_dict)
                self._handle_command(msg)
        except Exception as e:
            logger.error(f"Command processing error: {e}")

    def _handle_command(self, msg: IPCMessage):
        """Handle a command from the main process"""
        action = msg.action
        data = msg.data

        # Common commands
        if action == 'show':
            self.widget.show()
        elif action == 'hide':
            self.widget.hide()
        elif action == 'set_visible':
            self.widget.setVisible(data.get('visible', True))
        elif action == 'resize':
            self.widget.resize(data.get('width', 800), data.get('height', 600))
        elif action == 'move':
            self.widget.move(data.get('x', 0), data.get('y', 0))
        elif action == 'focus':
            self.widget.setFocus()
            self.widget.activateWindow()
        elif action == 'shutdown':
            self._shutdown()
        else:
            # Widget-specific command
            self._handle_widget_command(action, data, msg.msg_id)

    def _handle_widget_command(self, action: str, data: Dict, msg_id: int):
        """Override in subclass to handle widget-specific commands"""
        pass

    def _send_response(self, action: str, data: Dict = None, msg_id: int = 0):
        """Send a response to the main process"""
        msg = IPCMessage(
            msg_type='response',
            action=action,
            data=data or {},
            msg_id=msg_id
        )
        self.resp_queue.put(msg.to_dict())

    def _send_event(self, event_name: str, data: Dict = None):
        """Send an event to the main process"""
        msg = IPCMessage(
            msg_type='event',
            action=event_name,
            data=data or {}
        )
        self.resp_queue.put(msg.to_dict())

    def _handle_signal(self, signum, frame):
        """Handle termination signals"""
        self._shutdown()

    def _shutdown(self):
        """Clean shutdown"""
        self._running = False
        if hasattr(self, 'cmd_timer'):
            self.cmd_timer.stop()
        if hasattr(self, 'app'):
            self.app.quit()


class ProcessHost:
    """
    Manages a widget process and provides IPC.

    Used by the main window to communicate with widget processes.
    """

    def __init__(self, widget_type: WidgetType, process_class: type,
                 config: Dict = None):
        self.widget_type = widget_type
        self.process_class = process_class
        self.config = config or {}

        # IPC queues
        self.cmd_queue = Queue()
        self.resp_queue = Queue()
        self.shutdown_event = Event()

        # Process handle
        self.process: Optional[Process] = None
        self.window_id: Optional[int] = None

        # Message tracking
        self._msg_counter = 0
        self._pending_responses: Dict[int, Callable] = {}

        # Callbacks
        self._event_handlers: Dict[str, List[Callable]] = {}

    def start(self) -> bool:
        """Start the widget process"""
        if self.process and self.process.is_alive():
            return True

        try:
            # Create and start process
            self.process = Process(
                target=self._run_process,
                args=(
                    self.process_class,
                    self.widget_type,
                    self.cmd_queue,
                    self.resp_queue,
                    self.shutdown_event,
                    self.config
                ),
                daemon=True
            )
            self.process.start()

            # Wait for window ID
            start_time = time.time()
            while time.time() - start_time < 10:  # 10 second timeout
                self._process_responses()
                if self.window_id:
                    logger.info(f"Widget process started: {self.widget_type.name} (window_id: {self.window_id})")
                    return True
                time.sleep(0.1)

            logger.error(f"Timeout waiting for window ID from {self.widget_type.name}")
            return False

        except Exception as e:
            logger.error(f"Failed to start widget process: {e}")
            return False

    @staticmethod
    def _run_process(process_class, widget_type, cmd_queue, resp_queue,
                     shutdown_event, config):
        """Entry point for the child process"""
        instance = process_class(
            widget_type, cmd_queue, resp_queue, shutdown_event, config
        )
        instance.run()

    def stop(self):
        """Stop the widget process"""
        if not self.process:
            return

        # Signal shutdown
        self.shutdown_event.set()
        self.send_command('shutdown')

        # Wait for graceful shutdown
        self.process.join(timeout=5)

        # Force terminate if still running
        if self.process.is_alive():
            self.process.terminate()
            self.process.join(timeout=2)

        self.process = None
        self.window_id = None

    def is_running(self) -> bool:
        """Check if process is running"""
        return self.process is not None and self.process.is_alive()

    def send_command(self, action: str, data: Dict = None,
                    callback: Callable = None) -> int:
        """Send a command to the widget process"""
        self._msg_counter += 1
        msg_id = self._msg_counter

        msg = IPCMessage(
            msg_type='command',
            action=action,
            data=data or {},
            msg_id=msg_id
        )

        if callback:
            self._pending_responses[msg_id] = callback

        self.cmd_queue.put(msg.to_dict())
        return msg_id

    def _process_responses(self):
        """Process responses from the widget process"""
        try:
            while not self.resp_queue.empty():
                msg_dict = self.resp_queue.get_nowait()
                msg = IPCMessage.from_dict(msg_dict)

                if msg.action == 'window_id':
                    self.window_id = msg.data.get('window_id')
                elif msg.msg_type == 'response':
                    callback = self._pending_responses.pop(msg.msg_id, None)
                    if callback:
                        callback(msg.data)
                elif msg.msg_type == 'event':
                    self._emit_event(msg.action, msg.data)
        except Exception as e:
            logger.error(f"Response processing error: {e}")

    def on_event(self, event_name: str, handler: Callable):
        """Register an event handler"""
        if event_name not in self._event_handlers:
            self._event_handlers[event_name] = []
        self._event_handlers[event_name].append(handler)

    def _emit_event(self, event_name: str, data: Dict):
        """Emit an event to registered handlers"""
        handlers = self._event_handlers.get(event_name, [])
        for handler in handlers:
            try:
                handler(data)
            except Exception as e:
                logger.error(f"Event handler error: {e}")

    def poll(self):
        """Poll for responses (call this regularly from main thread)"""
        self._process_responses()


# ============================================================================
# Concrete Widget Process Implementations
# ============================================================================

class BrowserWidgetProcess(WidgetProcessBase):
    """Browser widget running in separate process"""

    def _create_widget(self):
        from PyQt6.QtWebEngineWidgets import QWebEngineView
        from PyQt6.QtCore import QUrl

        browser = QWebEngineView()
        browser.setUrl(QUrl(self.config.get('home_url', 'https://www.google.com')))
        browser.resize(800, 600)

        # Connect signals to send events
        browser.urlChanged.connect(
            lambda url: self._send_event('url_changed', {'url': url.toString()})
        )
        browser.titleChanged.connect(
            lambda title: self._send_event('title_changed', {'title': title})
        )
        browser.loadStarted.connect(
            lambda: self._send_event('load_started')
        )
        browser.loadFinished.connect(
            lambda ok: self._send_event('load_finished', {'success': ok})
        )

        return browser

    def _handle_widget_command(self, action: str, data: Dict, msg_id: int):
        if action == 'navigate':
            from PyQt6.QtCore import QUrl
            self.widget.setUrl(QUrl(data.get('url', '')))
        elif action == 'back':
            self.widget.back()
        elif action == 'forward':
            self.widget.forward()
        elif action == 'reload':
            self.widget.reload()
        elif action == 'stop':
            self.widget.stop()
        elif action == 'get_url':
            self._send_response('url', {'url': self.widget.url().toString()}, msg_id)
        elif action == 'get_title':
            self._send_response('title', {'title': self.widget.title()}, msg_id)


class TerminalWidgetProcess(WidgetProcessBase):
    """Terminal widget running in separate process"""

    def _create_widget(self):
        # Use the existing terminal widget
        try:
            from ailinux_client.ui.terminal_widget import TerminalWidget
            terminal = TerminalWidget()
        except ImportError:
            # Fallback to simple text widget
            from PyQt6.QtWidgets import QTextEdit
            terminal = QTextEdit()
            terminal.setPlaceholderText("Terminal (process mode)")

        terminal.resize(800, 600)
        return terminal

    def _handle_widget_command(self, action: str, data: Dict, msg_id: int):
        if action == 'send_input':
            if hasattr(self.widget, 'send_input'):
                self.widget.send_input(data.get('text', ''))
        elif action == 'clear':
            if hasattr(self.widget, 'clear'):
                self.widget.clear()
        elif action == 'new_tab':
            if hasattr(self.widget, 'add_tab'):
                self.widget.add_tab(
                    working_dir=data.get('working_dir'),
                    title=data.get('title')
                )


class FileBrowserWidgetProcess(WidgetProcessBase):
    """File browser widget running in separate process"""

    def _create_widget(self):
        try:
            from ailinux_client.ui.file_browser import FileBrowserWidget
            browser = FileBrowserWidget()
        except ImportError:
            from PyQt6.QtWidgets import QTreeView
            from PyQt6.QtWidgets import QFileSystemModel
            browser = QTreeView()
            model = QFileSystemModel()
            model.setRootPath('')
            browser.setModel(model)

        browser.resize(300, 600)
        return browser

    def _handle_widget_command(self, action: str, data: Dict, msg_id: int):
        if action == 'navigate':
            if hasattr(self.widget, 'navigate_to'):
                self.widget.navigate_to(data.get('path', ''))
        elif action == 'refresh':
            if hasattr(self.widget, 'refresh'):
                self.widget.refresh()
        elif action == 'get_current_path':
            path = getattr(self.widget, 'current_path', '')
            self._send_response('current_path', {'path': path}, msg_id)


class ChatWidgetProcess(WidgetProcessBase):
    """Chat widget running in separate process"""

    def _create_widget(self):
        try:
            from ailinux_client.ui.chat_widget import ChatWidget
            # Need to pass api_client - will use config
            from ailinux_client.core.api_client import APIClient
            api_client = APIClient(self.config.get('server_url', 'https://api.ailinux.me'))
            chat = ChatWidget(api_client)
        except ImportError:
            from PyQt6.QtWidgets import QTextEdit
            chat = QTextEdit()
            chat.setPlaceholderText("Chat (process mode)")

        chat.resize(400, 600)
        return chat

    def _handle_widget_command(self, action: str, data: Dict, msg_id: int):
        if action == 'send_message':
            if hasattr(self.widget, 'send_message'):
                self.widget.send_message(data.get('message', ''))
        elif action == 'clear':
            if hasattr(self.widget, 'clear_chat'):
                self.widget.clear_chat()
        elif action == 'set_model':
            if hasattr(self.widget, 'set_model'):
                self.widget.set_model(data.get('model', ''))


# ============================================================================
# Widget Process Manager
# ============================================================================

class WidgetProcessManager:
    """
    Manages all widget processes for the application.

    Usage:
        manager = WidgetProcessManager()
        manager.start_all()

        # Send commands
        manager.send_command(WidgetType.BROWSER, 'navigate', {'url': 'https://example.com'})

        # In main loop
        manager.poll()
    """

    PROCESS_CLASSES = {
        WidgetType.BROWSER: BrowserWidgetProcess,
        WidgetType.TERMINAL: TerminalWidgetProcess,
        WidgetType.FILE_BROWSER: FileBrowserWidgetProcess,
        WidgetType.CHAT: ChatWidgetProcess,
    }

    def __init__(self, config: Dict = None):
        self.config = config or {}
        self.hosts: Dict[WidgetType, ProcessHost] = {}

    def start(self, widget_type: WidgetType, widget_config: Dict = None) -> bool:
        """Start a specific widget process"""
        if widget_type in self.hosts and self.hosts[widget_type].is_running():
            return True

        process_class = self.PROCESS_CLASSES.get(widget_type)
        if not process_class:
            logger.error(f"Unknown widget type: {widget_type}")
            return False

        config = {**self.config, **(widget_config or {})}
        host = ProcessHost(widget_type, process_class, config)

        if host.start():
            self.hosts[widget_type] = host
            return True
        return False

    def start_all(self) -> Dict[WidgetType, bool]:
        """Start all widget processes"""
        results = {}
        for widget_type in WidgetType:
            results[widget_type] = self.start(widget_type)
        return results

    def stop(self, widget_type: WidgetType):
        """Stop a specific widget process"""
        if widget_type in self.hosts:
            self.hosts[widget_type].stop()
            del self.hosts[widget_type]

    def stop_all(self):
        """Stop all widget processes"""
        for host in list(self.hosts.values()):
            host.stop()
        self.hosts.clear()

    def send_command(self, widget_type: WidgetType, action: str,
                    data: Dict = None, callback: Callable = None) -> Optional[int]:
        """Send a command to a widget process"""
        host = self.hosts.get(widget_type)
        if host and host.is_running():
            return host.send_command(action, data, callback)
        return None

    def get_window_id(self, widget_type: WidgetType) -> Optional[int]:
        """Get the window ID for embedding"""
        host = self.hosts.get(widget_type)
        return host.window_id if host else None

    def on_event(self, widget_type: WidgetType, event_name: str, handler: Callable):
        """Register an event handler for a widget"""
        host = self.hosts.get(widget_type)
        if host:
            host.on_event(event_name, handler)

    def poll(self):
        """Poll all widget processes for responses"""
        for host in self.hosts.values():
            host.poll()

    def is_running(self, widget_type: WidgetType) -> bool:
        """Check if a widget process is running"""
        host = self.hosts.get(widget_type)
        return host.is_running() if host else False


# Global instance
_widget_manager: Optional[WidgetProcessManager] = None


def get_widget_manager(config: Dict = None) -> WidgetProcessManager:
    """Get or create the global widget process manager"""
    global _widget_manager
    if _widget_manager is None:
        _widget_manager = WidgetProcessManager(config)
    return _widget_manager
