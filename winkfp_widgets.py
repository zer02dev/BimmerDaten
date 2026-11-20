"""
winkfp_widgets.py
Shared Qt helpers and the common look of the WinKFP sub-tabs.

All WinKFP sub-tabs (current and future) should use the colours and helpers from
this module so the whole tab stays readable on top of the app's Win98 style.
"""
from __future__ import annotations

import logging
from collections.abc import Callable

from PyQt6.QtCore import QEvent, QObject, QRectF, Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import QAbstractItemView, QHeaderView, QTableWidget, QTreeWidget, QWidget

logger = logging.getLogger("bimmerdaten.winkfp_widgets")

# Text colours: dark enough to read on white and on the grey Win98 background.
COLOR_ERROR = "#a8001c"
COLOR_WARNING = "#8a4b00"
COLOR_INFO = "#0f4c8a"
COLOR_OK = "#176b1d"
COLOR_MUTED = "#3f3f3f"
COLOR_CODING = "#7a4a00"
COLOR_SWT = "#5b2d8c"

ROW_HEIGHT = 26
BASE_FONT = '"Segoe UI", "Tahoma", sans-serif'

# Applied to the whole WinKFP panel; overrides the app-wide Win98 fonts
# (Courier New 11px in tables / trees / text views) for better readability.
WINKFP_STYLE = f"""
QWidget {{
    font-family: {BASE_FONT};
    font-size: 13px;
}}
QLabel {{
    color: #111111;
}}
QTableWidget, QTreeWidget, QListWidget {{
    font-family: {BASE_FONT};
    font-size: 13px;
    color: #111111;
    background-color: #ffffff;
    alternate-background-color: #eef2f8;
    gridline-color: #c8ccd4;
}}
QTreeWidget::item, QListWidget::item {{
    padding: 3px 2px;
}}
QTableWidget::item {{
    padding: 2px 6px;
}}
QTableWidget::item:selected, QTreeWidget::item:selected, QListWidget::item:selected {{
    background-color: #000080;
    color: #ffffff;
}}
QHeaderView::section {{
    background-color: #e2dfd8;
    color: #111111;
    font-family: {BASE_FONT};
    font-size: 13px;
    font-weight: bold;
    padding: 4px 6px;
    border: 1px solid #a0a0a0;
}}
QTextEdit, QTextBrowser, QPlainTextEdit {{
    font-family: {BASE_FONT};
    font-size: 13px;
    color: #111111;
    background-color: #ffffff;
}}
QPlainTextEdit#mono {{
    font-family: "Consolas", "Courier New", monospace;
    font-size: 13px;
}}
QLineEdit, QComboBox {{
    font-family: {BASE_FONT};
    font-size: 13px;
    padding: 3px;
}}
QPushButton {{
    font-size: 13px;
    padding: 4px 12px;
}}
QTabBar::tab {{
    font-size: 13px;
    padding: 5px 12px;
}}
QCheckBox {{
    font-size: 13px;
}}

QToolTip {{
    background-color: #ffffe1;
    color: #000000;
    border: 1px solid #808080;
    padding: 4px;
    font-family: "Segoe UI", "Tahoma", sans-serif;
    font-size: 12px;
}}
"""

# Styles for HTML shown in QTextBrowser detail panes.
HTML_STYLE = f"""
<style>
body {{ font-family: {BASE_FONT}; font-size: 13px; color: #111111; }}
h3 {{ font-size: 16px; margin-bottom: 4px; }}
h4 {{ font-size: 14px; margin-bottom: 2px; }}
td, th {{ font-size: 13px; }}
th {{ background-color: #e2dfd8; }}
a {{ color: {COLOR_INFO}; }}
</style>
"""


def html_page(body: str) -> str:
    """Wrap detail-pane HTML with the common style."""
    return f"<html><head>{HTML_STYLE}</head><body>{body}</body></html>"


def style_table(table: QTableWidget) -> None:
    """Common table setup: readable row height, alternating rows, row selection."""
    table.setAlternatingRowColors(True)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.verticalHeader().setVisible(False)
    table.verticalHeader().setDefaultSectionSize(ROW_HEIGHT)
    table.setWordWrap(False)
    header = table.horizontalHeader()
    header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
    header.setStretchLastSection(True)
    header.setMinimumHeight(ROW_HEIGHT + 4)


def style_tree(tree: QTreeWidget) -> None:
    tree.setAlternatingRowColors(True)
    tree.setUniformRowHeights(True)
    tree.header().setMinimumHeight(ROW_HEIGHT + 4)


class Worker(QThread):
    """Run a function in a background thread and emit its result."""

    finishedWithResult = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, func: Callable[[], object], parent=None):
        super().__init__(parent)
        self._func = func

    def run(self):
        try:
            self.finishedWithResult.emit(self._func())
        except Exception as exc:
            logger.exception("WinKFP worker failed")
            self.failed.emit(str(exc))


class LoadingOverlay(QWidget):
    """Semi-transparent overlay with a spinning retro 'busy' wheel and a message.

    Usage: overlay = LoadingOverlay(widget); overlay.start("Loading…"); ... overlay.stop()
    The overlay covers its parent widget and follows its size.
    """

    DOTS = 12

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self._message = ""
        self._step = 0
        self._timer = QTimer(self)
        self._timer.setInterval(80)
        self._timer.timeout.connect(self._tick)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.hide()
        parent.installEventFilter(self)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched is self.parent() and event.type() in (QEvent.Type.Resize, QEvent.Type.Show):
            self.setGeometry(self.parent().rect())
        return False

    def start(self, message: str = "Loading…") -> None:
        self._message = message
        self.setGeometry(self.parent().rect())
        self.raise_()
        self.show()
        if not self._timer.isActive():
            self._timer.start()
        self.update()

    def set_message(self, message: str) -> None:
        self._message = message
        self.update()

    def stop(self) -> None:
        self._timer.stop()
        self.hide()

    def _tick(self) -> None:
        self._step = (self._step + 1) % self.DOTS
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(212, 208, 200, 170))

        # Win98-like dialog box in the middle
        box_w, box_h = 320, 150
        box = QRectF((self.width() - box_w) / 2, (self.height() - box_h) / 2, box_w, box_h)
        painter.fillRect(box, QColor("#d4d0c8"))
        painter.setPen(QPen(QColor("#ffffff"), 2))
        painter.drawLine(box.topLeft(), box.topRight())
        painter.drawLine(box.topLeft(), box.bottomLeft())
        painter.setPen(QPen(QColor("#808080"), 2))
        painter.drawLine(box.bottomLeft(), box.bottomRight())
        painter.drawLine(box.topRight(), box.bottomRight())
        title = QRectF(box.left() + 2, box.top() + 2, box.width() - 4, 22)
        painter.fillRect(title, QColor("#000080"))
        painter.setPen(QColor("#ffffff"))
        title_font = QFont("Segoe UI", 9)
        title_font.setBold(True)
        painter.setFont(title_font)
        painter.drawText(title.adjusted(8, 0, 0, 0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                         "Please wait")

        # spinning wheel of dots
        center_x = box.left() + 44
        center_y = box.top() + 24 + (box.height() - 24) / 2
        radius = 16
        painter.save()
        painter.translate(center_x, center_y)
        for i in range(self.DOTS):
            age = (self._step - i) % self.DOTS
            alpha = max(40, 255 - age * 20)
            painter.setBrush(QColor(0, 0, 128, alpha))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(QRectF(radius - 4, -3.5, 8, 7))
            painter.rotate(360 / self.DOTS)
        painter.restore()

        painter.setPen(QColor("#111111"))
        painter.setFont(QFont("Segoe UI", 10))
        text_rect = QRectF(box.left() + 80, box.top() + 30, box.width() - 92, box.height() - 40)
        painter.drawText(text_rect, int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
                         | int(Qt.TextFlag.TextWordWrap), self._message)
        painter.end()
