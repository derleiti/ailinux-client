"""Token Budget Widget — always-visible indicator in the status bar.

Shows current tier + today's token usage. Polls /v1/client/tokens/usage every
60 seconds while authenticated. Click → tooltip/details popup.

Introduced in v5.0.0 "Brumo 2".
"""
from __future__ import annotations
from typing import Optional

from PyQt6.QtCore import QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QCursor
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QProgressBar, QWidget


def _fmt(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}k"
    return str(n)


class TokenBudgetWidget(QWidget):
    upgrade_requested = pyqtSignal()
    POLL_MS = 60_000

    def __init__(self, api_client, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.api = api_client
        self._build_ui()
        self._timer = QTimer(self)
        self._timer.setInterval(self.POLL_MS)
        self._timer.timeout.connect(self.refresh)
        self._timer.start()
        QTimer.singleShot(2000, self.refresh)

    def _build_ui(self) -> None:
        row = QHBoxLayout(self)
        row.setContentsMargins(6, 0, 6, 0)
        row.setSpacing(6)

        self.tier_badge = QLabel("FREE")
        self.tier_badge.setStyleSheet(self._tier_badge_style("free"))
        self.tier_badge.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.tier_badge.mousePressEvent = self._on_click
        row.addWidget(self.tier_badge)

        self.usage_label = QLabel("— / —")
        self.usage_label.setStyleSheet("color: #bbb; font-size: 11px;")
        row.addWidget(self.usage_label)

        self.bar = QProgressBar()
        self.bar.setMinimum(0)
        self.bar.setMaximum(100)
        self.bar.setValue(0)
        self.bar.setTextVisible(False)
        self.bar.setFixedWidth(80)
        self.bar.setFixedHeight(8)
        self.bar.setStyleSheet("""
            QProgressBar { border: 1px solid #444; border-radius: 3px; background-color: #1a1a1a; }
            QProgressBar::chunk { background-color: #4ab8e0; border-radius: 2px; }
        """)
        row.addWidget(self.bar)

    @staticmethod
    def _tier_badge_style(tier: str) -> str:
        colors = {
            "free":       ("#666", "#fff"),
            "guest":      ("#666", "#fff"),
            "registered": ("#444", "#ccc"),
            "pro":        ("#2d7ac7", "#fff"),
            "unlimited":  ("#9746d3", "#fff"),
            "enterprise": ("#d39046", "#fff"),
            "admin":      ("#d34646", "#fff"),
        }
        bg, fg = colors.get(tier.lower(), ("#666", "#fff"))
        return (
            f"QLabel {{ background-color: {bg}; color: {fg}; padding: 2px 8px; "
            f"border-radius: 8px; font-size: 10px; font-weight: bold; }}"
        )

    def _on_click(self, _event) -> None:
        tier = (self.tier_badge.text() or "").lower()
        if tier in ("free", "guest", "registered"):
            self.upgrade_requested.emit()

    def refresh(self) -> None:
        if not getattr(self.api, "is_authenticated", lambda: False)():
            self.tier_badge.setText("GUEST")
            self.tier_badge.setStyleSheet(self._tier_badge_style("guest"))
            self.usage_label.setText("sign in")
            self.bar.setValue(0)
            return

        data = self.api.get_token_usage() or {}
        tier = (data.get("tier") or self.api.tier or "free")
        used = int(data.get("used_today") or 0)
        limit = int(data.get("daily_limit") or 0)

        self.tier_badge.setText(tier.upper())
        self.tier_badge.setStyleSheet(self._tier_badge_style(tier))

        if limit <= 0:
            self.usage_label.setText(f"{_fmt(used)} tokens")
            self.bar.setMaximum(1)
            self.bar.setValue(1)
        else:
            self.usage_label.setText(f"{_fmt(used)} / {_fmt(limit)}")
            self.bar.setMaximum(limit)
            self.bar.setValue(min(used, limit))
            pct = used / limit
            if pct >= 0.9:
                chunk = "#d34646"
            elif pct >= 0.7:
                chunk = "#e09d4a"
            else:
                chunk = "#4ab8e0"
            self.bar.setStyleSheet(f"""
                QProgressBar {{ border: 1px solid #444; border-radius: 3px; background-color: #1a1a1a; }}
                QProgressBar::chunk {{ background-color: {chunk}; border-radius: 2px; }}
            """)

        self.setToolTip(
            f"Tier: {tier}\n"
            f"Used today: {_fmt(used)}\n"
            f"Daily limit: {_fmt(limit) if limit else 'unlimited'}\n"
            f"Total used: {_fmt(data.get('used_total') or 0)}"
        )
