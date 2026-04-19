"""AI Search Widget — Perplexity-style AI-powered web search.

Uses backend endpoint POST /v1/client/search.
Introduced in v5.0.0 "Brumo 2".
"""
from __future__ import annotations
from typing import Optional

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QCheckBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QScrollArea, QSizePolicy, QTextBrowser, QVBoxLayout, QWidget,
)


class SearchWorker(QThread):
    finished_ok = pyqtSignal(dict)
    failed = pyqtSignal(str)

    def __init__(self, api_client, query: str, deep: bool = False):
        super().__init__()
        self.api = api_client
        self.query = query
        self.deep = deep

    def run(self) -> None:
        try:
            result = self.api.ai_search(self.query, max_results=6, deep=self.deep)
            if not isinstance(result, dict):
                self.failed.emit("Unexpected response format")
                return
            self.finished_ok.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))


class AISearchWidget(QWidget):
    def __init__(self, api_client, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.api = api_client
        self._worker: Optional[SearchWorker] = None
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        row = QHBoxLayout()
        row.setSpacing(6)
        self.query_edit = QLineEdit()
        self.query_edit.setPlaceholderText("Ask anything — e.g. 'latest kernel 7.4 regression on AMD'")
        self.query_edit.returnPressed.connect(self.start_search)
        row.addWidget(self.query_edit, 1)

        self.search_btn = QPushButton("🔍  Search")
        self.search_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.search_btn.clicked.connect(self.start_search)
        row.addWidget(self.search_btn)

        self.deep_check = QCheckBox("Deep")
        self.deep_check.setToolTip("Slower, costs more tokens — backend fetches full page content.")
        row.addWidget(self.deep_check)
        root.addLayout(row)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        root.addWidget(sep)

        self.answer_view = QTextBrowser()
        self.answer_view.setOpenExternalLinks(True)
        self.answer_view.setPlaceholderText(
            "AI answer will appear here.\n\nPowered by your TriForce backend — "
            "uses your daily token quota. Results cite web sources."
        )
        self.answer_view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        root.addWidget(self.answer_view, 3)

        sources_label = QLabel("Sources")
        sources_label.setStyleSheet("font-weight: bold; color: #888; padding-top: 4px;")
        root.addWidget(sources_label)

        self.sources_scroll = QScrollArea()
        self.sources_scroll.setWidgetResizable(True)
        self.sources_scroll.setMaximumHeight(180)
        self.sources_container = QWidget()
        self.sources_layout = QVBoxLayout(self.sources_container)
        self.sources_layout.setContentsMargins(4, 4, 4, 4)
        self.sources_layout.setSpacing(4)
        self.sources_layout.addStretch(1)
        self.sources_scroll.setWidget(self.sources_container)
        root.addWidget(self.sources_scroll, 1)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #888; font-size: 11px; padding-top: 2px;")
        root.addWidget(self.status_label)

        shortcut = QShortcut(QKeySequence("Ctrl+K"), self)
        shortcut.activated.connect(self.query_edit.setFocus)

    def start_search(self) -> None:
        q = self.query_edit.text().strip()
        if not q:
            return
        if self._worker is not None and self._worker.isRunning():
            return

        self.search_btn.setEnabled(False)
        self.search_btn.setText("⏳  Searching...")
        self.answer_view.setMarkdown("_Searching..._")
        self._clear_sources()
        self.status_label.setText("")

        self._worker = SearchWorker(self.api, q, deep=self.deep_check.isChecked())
        self._worker.finished_ok.connect(self._on_ok)
        self._worker.failed.connect(self._on_fail)
        self._worker.finished.connect(self._on_done)
        self._worker.start()

    def _on_ok(self, result: dict) -> None:
        answer = result.get("answer") or result.get("text") or "(no answer returned)"
        self.answer_view.setMarkdown(str(answer))
        for src in (result.get("sources") or []):
            self._add_source(src)
        tokens = result.get("used_tokens") or result.get("tokens")
        if tokens:
            self.status_label.setText(f"{tokens} tokens used")

    def _on_fail(self, msg: str) -> None:
        self.answer_view.setMarkdown(f"**Search failed**\n\n`{msg}`")
        self.status_label.setText("error")

    def _on_done(self) -> None:
        self.search_btn.setEnabled(True)
        self.search_btn.setText("🔍  Search")
        self._worker = None

    def _clear_sources(self) -> None:
        while self.sources_layout.count() > 1:
            item = self.sources_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def _add_source(self, src: dict) -> None:
        url = src.get("url") or ""
        title = src.get("title") or url or "(source)"
        snippet = src.get("snippet") or src.get("content") or ""

        box = QFrame()
        box.setFrameShape(QFrame.Shape.StyledPanel)
        box.setStyleSheet("QFrame { border: 1px solid #333; border-radius: 4px; padding: 4px; }")
        vl = QVBoxLayout(box)
        vl.setContentsMargins(6, 4, 6, 4)
        vl.setSpacing(2)

        title_lbl = QLabel(f'<a href="{url}" style="color:#4ab8e0; text-decoration:none;">{title}</a>')
        title_lbl.setOpenExternalLinks(True)
        title_lbl.setWordWrap(True)
        vl.addWidget(title_lbl)

        if snippet:
            snip = QLabel(snippet[:240] + ("…" if len(snippet) > 240 else ""))
            snip.setStyleSheet("color: #bbb; font-size: 11px;")
            snip.setWordWrap(True)
            vl.addWidget(snip)

        self.sources_layout.insertWidget(self.sources_layout.count() - 1, box)
