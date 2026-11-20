"""
winkfp_widgets.py
Shared Qt helpers and the common look of the WinKFP sub-tabs.

All WinKFP sub-tabs (current and future) should use the colours and helpers from
this module so the whole tab stays readable on top of the app's Win98 style.
"""
from __future__ import annotations

import logging
from collections.abc import Callable

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import QAbstractItemView, QHeaderView, QTableWidget, QTreeWidget

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
