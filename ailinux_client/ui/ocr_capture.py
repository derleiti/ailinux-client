"""OCR Quick Capture — Copa-lite inside the AILinux Client.

Triggered via menu action or shortcut (default Ctrl+Alt+O).
Flow:
  1. User clicks → client hides, screen dims with region selection overlay
  2. User drags rectangle around text
  3. Screenshot bytes sent to /v1/client/ocr/mistral
  4. Result shown in dialog + copied to clipboard

Introduced in v5.0.0 "Brumo 2".
"""
from __future__ import annotations
import io
from typing import Optional

from PyQt6.QtCore import QPoint, QRect, Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor, QGuiApplication, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (
    QApplication, QDialog, QHBoxLayout, QLabel, QMessageBox,
    QPushButton, QTextEdit, QVBoxLayout, QWidget,
)


class OCRWorker(QThread):
    finished_ok = pyqtSignal(dict)
    failed = pyqtSignal(str)

    def __init__(self, api_client, image_bytes: bytes, lang: str = "en"):
        super().__init__()
        self.api = api_client
        self.image_bytes = image_bytes
        self.lang = lang

    def run(self) -> None:
        try:
            result = self.api.ocr_mistral(self.image_bytes, lang=self.lang)
            if not isinstance(result, dict):
                self.failed.emit("Unexpected response format")
                return
            self.finished_ok.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))


class RegionSelectOverlay(QWidget):
    captured = pyqtSignal(QPixmap)
    cancelled = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setCursor(Qt.CursorShape.CrossCursor)

        screen = QGuiApplication.primaryScreen()
        self._screenshot = screen.grabWindow(0)
        self.setGeometry(screen.geometry())

        self._start: Optional[QPoint] = None
        self._end: Optional[QPoint] = None

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(0, 0, 0, 120))

        if self._start and self._end:
            rect = QRect(self._start, self._end).normalized()
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
            p.fillRect(rect, Qt.GlobalColor.transparent)
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            pen = QPen(QColor(74, 184, 224), 2)
            p.setPen(pen)
            p.drawRect(rect)
            p.setPen(QColor(255, 255, 255))
            p.drawText(rect.bottomRight() + QPoint(6, 16),
                       f"{rect.width()} x {rect.height()}")

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._start = event.pos()
            self._end = event.pos()
            self.update()

    def mouseMoveEvent(self, event) -> None:
        if self._start:
            self._end = event.pos()
            self.update()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton or not self._start:
            return
        self._end = event.pos()
        rect = QRect(self._start, self._end).normalized()
        self.hide()
        if rect.width() < 8 or rect.height() < 8:
            self.cancelled.emit()
            return
        cropped = self._screenshot.copy(rect)
        self.captured.emit(cropped)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
            self.cancelled.emit()


class OCRResultDialog(QDialog):
    def __init__(self, text: str, remaining: Optional[int] = None, entitled: bool = False,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("OCR Result")
        self.resize(600, 380)

        layout = QVBoxLayout(self)

        self.text_edit = QTextEdit()
        self.text_edit.setPlainText(text)
        self.text_edit.setReadOnly(False)
        layout.addWidget(self.text_edit, 1)

        info_row = QHBoxLayout()
        if entitled:
            info = QLabel("Entitled (unlimited scans)")
            info.setStyleSheet("color: #6a9;")
        elif remaining is not None:
            info = QLabel(f"Demo: {remaining} scans remaining this month")
            info.setStyleSheet("color: #e09d4a;" if remaining < 5 else "color: #888;")
        else:
            info = QLabel("")
        info_row.addWidget(info)
        info_row.addStretch(1)

        copy_btn = QPushButton("Copy to Clipboard")
        copy_btn.clicked.connect(self._copy)
        info_row.addWidget(copy_btn)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        info_row.addWidget(close_btn)

        layout.addLayout(info_row)

    def _copy(self) -> None:
        QApplication.clipboard().setText(self.text_edit.toPlainText())


class OCRQuickCapture:
    def __init__(self, parent_window, api_client) -> None:
        self.parent = parent_window
        self.api = api_client
        self._overlay: Optional[RegionSelectOverlay] = None
        self._worker: Optional[OCRWorker] = None
        self._progress: Optional[QMessageBox] = None

    def trigger(self) -> None:
        self.parent.hide()
        QApplication.processEvents()

        self._overlay = RegionSelectOverlay()
        self._overlay.captured.connect(self._on_captured)
        self._overlay.cancelled.connect(self._on_cancelled)
        self._overlay.showFullScreen()

    def _on_cancelled(self) -> None:
        self.parent.show()

    def _on_captured(self, pixmap: QPixmap) -> None:
        self.parent.show()

        img_bytes = self._pixmap_to_png(pixmap)
        if not img_bytes:
            QMessageBox.warning(self.parent, "OCR", "Failed to capture screenshot.")
            return

        self._progress = QMessageBox(self.parent)
        self._progress.setWindowTitle("OCR")
        self._progress.setText("Analyzing with Mistral AI OCR...")
        self._progress.setStandardButtons(QMessageBox.StandardButton.NoButton)
        self._progress.show()
        QApplication.processEvents()

        self._worker = OCRWorker(self.api, img_bytes, lang="en")
        self._worker.finished_ok.connect(self._on_ok)
        self._worker.failed.connect(self._on_fail)
        self._worker.finished.connect(self._on_done)
        self._worker.start()

    def _on_ok(self, result: dict) -> None:
        text = result.get("text") or ""
        remaining = result.get("remaining")
        entitled = bool(result.get("entitled"))

        dlg = OCRResultDialog(text, remaining=remaining, entitled=entitled, parent=self.parent)
        QApplication.clipboard().setText(text)
        dlg.exec()

    def _on_fail(self, msg: str) -> None:
        QMessageBox.warning(
            self.parent, "OCR failed",
            f"Could not extract text:\n\n{msg}\n\n"
            "Check your connection or that your tier includes OCR access."
        )

    def _on_done(self) -> None:
        if self._progress is not None:
            self._progress.hide()
            self._progress = None
        self._worker = None

    @staticmethod
    def _pixmap_to_png(pixmap: QPixmap) -> bytes:
        from PyQt6.QtCore import QBuffer, QByteArray, QIODevice
        ba = QByteArray()
        buf = QBuffer(ba)
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        pixmap.save(buf, "PNG")
        return bytes(ba)
