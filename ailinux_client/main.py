#!/usr/bin/env python3
"""
AILinux Client - Main Entry Point
==================================

Usage:
    python -m ailinux_client                 # Normal mode
    python -m ailinux_client --desktop       # Desktop mode (fullscreen panel)
    python -m ailinux_client --server URL    # Custom server
    python -m ailinux_client --hwinfo        # Show hardware info
"""
import sys
import os
import argparse
import signal
import atexit
import logging
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Setup logging early
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("ailinux.main")

# ============================================================================
# Hardware Detection & Qt Optimization (BEFORE QApplication!)
# ============================================================================

def setup_hardware_acceleration():
    """Setup Qt environment variables based on hardware capabilities.
    MUST be called BEFORE QApplication is created!
    """
    try:
        from .core.hardware_detect import hardware_detector, get_qt_hints

        logger.info("Detecting hardware capabilities...")
        hints = get_qt_hints()

        # Set Qt rendering backend based on hardware
        if hints.get('use_opengl', False):
            # Enable OpenGL acceleration
            os.environ.setdefault('QT_QUICK_BACKEND', 'opengl')
            os.environ.setdefault('QSG_RENDER_LOOP', 'basic')  # More stable

            # Enable GPU rasterization for WebEngine
            os.environ.setdefault('QTWEBENGINE_CHROMIUM_FLAGS',
                '--enable-gpu-rasterization --enable-native-gpu-memory-buffers '
                '--enable-accelerated-video-decode --enable-accelerated-mjpeg-decode')

            logger.info("OpenGL acceleration enabled")
        else:
            # Software rendering fallback
            os.environ.setdefault('QT_QUICK_BACKEND', 'software')
            os.environ.setdefault('LIBGL_ALWAYS_SOFTWARE', '1')
            logger.info("Using software rendering (no GPU acceleration detected)")

        # Performance tier optimizations
        tier = hints.get('performance_tier', 'medium')
        if tier == 'high':
            # High performance system - enable all effects
            os.environ.setdefault('QT_ENABLE_HIGHDPI_SCALING', '1')
            os.environ.setdefault('QT_SCALE_FACTOR_ROUNDING_POLICY', 'PassThrough')
        elif tier == 'low':
            # Low performance - reduce effects
            os.environ.setdefault('QT_QUICK_CONTROLS_STYLE', 'Basic')
            os.environ.setdefault('QT_ENABLE_GLYPH_CACHE_WORKAROUND', '1')

        # Thread pool size
        thread_count = hints.get('thread_count', 4)
        os.environ.setdefault('QT_THREAD_COUNT', str(thread_count))

        # V-Sync
        if hints.get('enable_vsync', True):
            os.environ.setdefault('QSG_RENDER_TIMING', '1')

        logger.info(f"Hardware optimization: tier={tier}, threads={thread_count}")
        return hints

    except Exception as e:
        logger.warning(f"Hardware detection failed, using defaults: {e}")
        return {}

# Run hardware setup BEFORE importing Qt
_hw_hints = setup_hardware_acceleration()

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QSurfaceFormat

# IMPORTANT: Import WebEngine BEFORE QApplication is created
from PyQt6.QtWebEngineWidgets import QWebEngineView  # noqa: F401


def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description="AILinux Desktop Client",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        "--desktop", "--desktop-mode",
        action="store_true",
        help="Launch in full desktop mode with panel"
    )

    parser.add_argument(
        "--weather",
        default=os.getenv("WEATHER_LOCATION", ""),
        help="Weather location for panel"
    )

    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging"
    )

    parser.add_argument(
        "--hwinfo",
        action="store_true",
        help="Show hardware information and exit"
    )

    parser.add_argument(
        "--software-render",
        action="store_true",
        help="Force software rendering (disable GPU)"
    )

    parser.add_argument(
        "--enable-autostart",
        action="store_true",
        help="Enable autostart on boot (systemd)"
    )

    parser.add_argument(
        "--disable-autostart",
        action="store_true",
        help="Disable autostart on boot (systemd)"
    )

    return parser.parse_args()


def manage_autostart(enable: bool) -> bool:
    """Enable or disable systemd autostart service."""
    import subprocess
    try:
        action = "enable" if enable else "disable"
        result = subprocess.run(
            ["systemctl", "--user", action, "ailinux-client"],
            capture_output=True,
            text=True
        )
        return result.returncode == 0
    except Exception as e:
        logger.error(f"Failed to {action} autostart: {e}")
        return False


def is_autostart_enabled() -> bool:
    """Check if autostart is enabled."""
    import subprocess
    try:
        result = subprocess.run(
            ["systemctl", "--user", "is-enabled", "ailinux-client"],
            capture_output=True,
            text=True
        )
        return result.stdout.strip() == "enabled"
    except Exception:
        return False


def main():
    """Main entry point"""
    args = parse_args()

    # Handle --hwinfo command (no GUI needed)
    if args.hwinfo:
        try:
            from .core.hardware_detect import hardware_detector
            print(hardware_detector.get_summary())
            return 0
        except Exception as e:
            print(f"Hardware detection failed: {e}")
            return 1

    # Handle autostart commands (no GUI needed)
    if args.enable_autostart:
        if manage_autostart(True):
            print("✓ Autostart enabled")
            return 0
        else:
            print("✗ Failed to enable autostart")
            return 1

    if args.disable_autostart:
        if manage_autostart(False):
            print("✓ Autostart disabled")
            return 0
        else:
            print("✗ Failed to disable autostart")
            return 1

    # Force software rendering if requested
    if args.software_render:
        os.environ['QT_QUICK_BACKEND'] = 'software'
        os.environ['LIBGL_ALWAYS_SOFTWARE'] = '1'
        os.environ['QTWEBENGINE_CHROMIUM_FLAGS'] = '--disable-gpu'
        logger.info("Forced software rendering mode")

    # Debug logging
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    logger.info(f"Starting AILinux Client (desktop_mode={args.desktop})")
    logger.info(f"Server: https://api.ailinux.me")

    # Setup OpenGL surface format for better rendering
    surface_format = QSurfaceFormat()
    surface_format.setSwapBehavior(QSurfaceFormat.SwapBehavior.DoubleBuffer)
    surface_format.setSwapInterval(1)  # V-Sync

    # Enable antialiasing if GPU is available
    if _hw_hints.get('antialiasing', False) and not args.software_render:
        surface_format.setSamples(4)  # 4x MSAA
    else:
        surface_format.setSamples(0)

    QSurfaceFormat.setDefaultFormat(surface_format)

    # High DPI support - MUST be called before QApplication
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    # Create Qt application
    app = QApplication(sys.argv)
    app.setApplicationName("AILinux Client")
    app.setOrganizationName("AILinux")
    app.setOrganizationDomain("ailinux.me")

    # Dark theme
    app.setStyleSheet("""
        QWidget {
            background-color: #1a1a1a;
            color: #e0e0e0;
        }
        QLineEdit, QTextEdit, QPlainTextEdit {
            background-color: #252525;
            border: 1px solid #333;
            border-radius: 4px;
            padding: 4px;
        }
        QPushButton {
            background-color: #3b82f6;
            color: white;
            border: none;
            border-radius: 4px;
            padding: 6px 16px;
        }
        QPushButton:hover {
            background-color: #2563eb;
        }
        QPushButton:pressed {
            background-color: #1d4ed8;
        }
        QScrollBar:vertical {
            background: #252525;
            width: 10px;
        }
        QScrollBar::handle:vertical {
            background: #444;
            border-radius: 5px;
        }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
            height: 0px;
        }
    """)

    # Initialize API client
    from .core.api_client import APIClient
    api_client = APIClient()

    # Show login dialog if not authenticated
    if not api_client.is_authenticated():
        from .ui.login_dialog import LoginDialog
        login_dialog = LoginDialog(api_client)
        if login_dialog.exec() != login_dialog.DialogCode.Accepted:
            logger.info("Login cancelled")
            return 0

    # Create main window
    from .ui.main_window import MainWindow

    window = MainWindow(
        api_client=api_client,
        desktop_mode=args.desktop

    )

    # Register window for cleanup (SIGTERM, crash handling)
    try:
        from run import set_main_window
        set_main_window(window)
        logger.info("MainWindow registered for cleanup")
    except ImportError:
        pass  # run.py not in path

    # Set weather location if provided
    if args.weather and hasattr(window, 'desktop_panel'):
        window.desktop_panel.set_weather_location(args.weather)

    # Show window on primary screen and bring to front
    if args.desktop:
        window.showFullScreen()
    else:
        # Ensure window is visible on primary screen
        screen = app.primaryScreen()
        if screen:
            screen_geometry = screen.availableGeometry()
            # Center window on primary screen
            window_width = min(1600, screen_geometry.width() - 100)
            window_height = min(1000, screen_geometry.height() - 100)
            x = screen_geometry.x() + (screen_geometry.width() - window_width) // 2
            y = screen_geometry.y() + (screen_geometry.height() - window_height) // 2
            window.setGeometry(x, y, window_width, window_height)

        window.show()
        window.raise_()  # Bring to front
        window.activateWindow()  # Activate window

    logger.info("Window shown")

    # Run event loop
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
