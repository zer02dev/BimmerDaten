"""
winkfp_logs_tab.py
"Logs" sub-tab: WinKFP error logs grouped into events with explained error codes,
and the result files of WinKFP special functions (IDENT / AIF / REF ...).
"""
from __future__ import annotations

import logging
import os
from collections import Counter
from collections.abc import Callable
from datetime import datetime
from html import escape as html_escape
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from winkfp_errors import LogEvent, collapse_repeated, group_events, tip_for
from winkfp_parser import (
    WinkfpPaths,
    find_error_logs,
    find_out_files,
    parse_error_log,
    parse_error_texts,
    read_install_info,
)

logger = logging.getLogger("bimmerdaten.winkfp_logs_tab")

EVENT_COLUMNS = ["Time", "×", "Code", "PABD / module", "Job / argument", "Message", "Explanation"]

OUT_FILE_TITLES = {
    "IDENT": "ECU identification (Read ident)",
    "AIF": "User info field (Read UIF)",
    "REF": "Data / HW reference, ZIF",
    "INNENTMP": "ECU internal temperature",
    "CABDPAR": "PABD parameters",
}


def _fmt_time(stamp: datetime | None) -> str:
    return stamp.strftime("%Y-%m-%d %H:%M:%S") if stamp else ""


def _fmt_mtime(path: Path) -> str:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
    except OSError:
        return ""


class LogsTab(QWidget):
    def __init__(self, paths_provider: Callable[[], WinkfpPaths], parent=None):
        super().__init__(parent)
        self._paths_provider = paths_provider
        self._events: list[LogEvent] = []
        self._shown: list[LogEvent] = []
        self._texts: dict[int, str] = {}
        self._loaded = False
        self._build_ui()

    # --- UI ------------------------------------------------------------------

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        self.inner_tabs = QTabWidget()
        layout.addWidget(self.inner_tabs)

        # Error log page
        errors_page = QWidget()
        errors_layout = QVBoxLayout(errors_page)
        errors_layout.setContentsMargins(4, 4, 4, 4)

        bar = QHBoxLayout()
        bar.addWidget(QLabel("Log file:"))
        self.log_combo = QComboBox()
        self.log_combo.setMinimumWidth(320)
        self.log_combo.currentIndexChanged.connect(self._load_selected_log)
        bar.addWidget(self.log_combo, 1)
        self.group_check = QCheckBox("Group repeated errors")
        self.group_check.setChecked(True)
        self.group_check.toggled.connect(self._populate_events)
        bar.addWidget(self.group_check)
        self.refresh_btn = QPushButton("🔄 Refresh")
        self.refresh_btn.clicked.connect(self.reload)
        bar.addWidget(self.refresh_btn)
        self.open_folder_btn = QPushButton("📂 Open folder")
        self.open_folder_btn.clicked.connect(self._open_log_folder)
        bar.addWidget(self.open_folder_btn)
        errors_layout.addLayout(bar)

        self.summary_label = QLabel("")
        self.summary_label.setWordWrap(True)
        errors_layout.addWidget(self.summary_label)

        splitter = QSplitter(Qt.Orientation.Vertical)
        self.table = QTableWidget(0, len(EVENT_COLUMNS))
        self.table.setHorizontalHeaderLabels(EVENT_COLUMNS)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        self.table.currentCellChanged.connect(lambda row, *_: self._show_event(row))
        splitter.addWidget(self.table)

        self.details = QTextBrowser()
        splitter.addWidget(self.details)
        splitter.setSizes([380, 220])
        errors_layout.addWidget(splitter, 1)
        self.inner_tabs.addTab(errors_page, "❌ Error log")

        # Result files page
        results_page = QWidget()
        results_layout = QHBoxLayout(results_page)
        results_layout.setContentsMargins(4, 4, 4, 4)
        results_split = QSplitter(Qt.Orientation.Horizontal)
        self.out_list = QListWidget()
        self.out_list.currentItemChanged.connect(self._show_out_file)
        results_split.addWidget(self.out_list)
        self.out_text = QPlainTextEdit()
        self.out_text.setReadOnly(True)
        mono = QFont("Consolas")
        mono.setStyleHint(QFont.StyleHint.Monospace)
        self.out_text.setFont(mono)
        results_split.addWidget(self.out_text)
        results_split.setSizes([320, 800])
        results_layout.addWidget(results_split)
        self.inner_tabs.addTab(results_page, "📄 Results (IDENT / UIF / REF)")

    # --- loading -------------------------------------------------------------

    def showEvent(self, event):
        super().showEvent(event)
        if not self._loaded:
            self._loaded = True
            self.reload()

    def reload(self):
        paths = self._paths_provider()
        try:
            language = read_install_info(paths).language or "eng"
            self._texts = parse_error_texts(paths, language)
        except Exception:
            logger.exception("Failed to read WinKFP error texts")
            self._texts = {}

        current = self.log_combo.currentData()
        self.log_combo.blockSignals(True)
        self.log_combo.clear()
        for log_path in find_error_logs(paths):
            self.log_combo.addItem(f"{log_path.name}  ({_fmt_mtime(log_path)})", str(log_path))
        if self.log_combo.count() == 0:
            self.log_combo.addItem("(no error logs found)", None)
        if current is not None:
            idx = self.log_combo.findData(current)
            if idx >= 0:
                self.log_combo.setCurrentIndex(idx)
        self.log_combo.blockSignals(False)
        self._load_selected_log()

        self.out_list.clear()
        self.out_text.clear()
        for out_path in find_out_files(paths):
            prefix = out_path.stem.split("_", 1)[0].upper()
            title = OUT_FILE_TITLES.get(prefix, out_path.stem)
            item = QListWidgetItem(f"{title}\n{out_path.name} · {_fmt_mtime(out_path)}")
            item.setData(Qt.ItemDataRole.UserRole, str(out_path))
            self.out_list.addItem(item)
        if self.out_list.count():
            self.out_list.setCurrentRow(0)

    def _load_selected_log(self):
        path = self.log_combo.currentData()
        if not path:
            self._events = []
            self._populate_events()
            return
        try:
            self._events = group_events(parse_error_log(Path(path)))
        except Exception as exc:
            logger.exception("Failed to parse WinKFP log %s", path)
            self._events = []
            self.summary_label.setText(f"<span style='color:#b00020;'>Cannot read log: {html_escape(str(exc))}</span>")
        self._populate_events()

    # --- error events --------------------------------------------------------

    def _code_text(self, code: int) -> str:
        return self._texts.get(code, "")

    def _populate_events(self):
        events = collapse_repeated(self._events) if self.group_check.isChecked() else list(self._events)
        events.sort(key=lambda e: e.timestamp or datetime.min, reverse=True)
        self._shown = events

        self.table.setRowCount(len(events))
        for row, event in enumerate(events):
            primary = event.primary
            tip = event.tip
            values = [
                _fmt_time(event.timestamp),
                str(event.count) if event.count > 1 else "",
                ", ".join(str(c) for c in event.codes),
                event.where,
                primary.message_arg,
                primary.message_text or self._code_text(primary.code),
                tip.title if tip else "",
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                if col == EVENT_COLUMNS.index("Explanation") and tip:
                    item.setForeground(QColor("#1f5f9e"))
                self.table.setItem(row, col, item)
        self.table.resizeColumnsToContents()
        msg_col = EVENT_COLUMNS.index("Message")
        if self.table.columnWidth(msg_col) > 340:
            self.table.setColumnWidth(msg_col, 340)

        if not self._events:
            self.summary_label.setText("No error entries in this log.")
            self.details.clear()
            return
        total = len(self._events)
        stamps = [e.timestamp for e in self._events if e.timestamp]
        period = f"{_fmt_time(min(stamps))} – {_fmt_time(max(stamps))}" if stamps else ""
        counter = Counter(e.primary.code for e in self._events)
        top = ", ".join(f"<b>{code}</b> ×{count}" for code, count in counter.most_common(4))
        self.summary_label.setText(
            f"{total} error event(s) {('(' + str(len(events)) + ' distinct)') if self.group_check.isChecked() else ''}"
            f" · {period} · most frequent: {top}"
        )
        self.table.setCurrentCell(0, 0)

    def _show_event(self, row: int):
        if row < 0 or row >= len(self._shown):
            self.details.clear()
            return
        event = self._shown[row]
        html: list[str] = []
        tip = event.tip
        if tip is not None:
            html.append(
                f"<h3 style='color:#1f5f9e;'>💡 {html_escape(tip.title)}</h3>"
                f"<p><b>Cause:</b> {html_escape(tip.cause)}</p>"
                f"<p><b>What to do:</b> {html_escape(tip.fix)}</p>"
            )
        when = _fmt_time(event.timestamp)
        if event.count > 1:
            when += f" (×{event.count}, last {_fmt_time(event.last_timestamp)})"
        html.append(f"<p style='color:#666;'>{html_escape(when)}</p>")
        html.append("<table cellspacing='0' cellpadding='3' border='1' style='border-collapse:collapse;'>")
        html.append("<tr><th>Code</th><th>Category</th><th>Source</th><th>Function</th><th>Message</th><th>Code text</th></tr>")
        for entry in event.entries:
            entry_tip = tip_for(entry)
            code_text = self._code_text(entry.code)
            html.append(
                "<tr>"
                f"<td>{entry.code}</td><td>{html_escape(entry.category)}</td>"
                f"<td>{html_escape(entry.source)}</td><td>{html_escape(entry.function)}</td>"
                f"<td>{html_escape(entry.message)}</td>"
                f"<td>{html_escape(code_text or (entry_tip.title if entry_tip else ''))}</td>"
                "</tr>"
            )
        html.append("</table>")
        self.details.setHtml("".join(html))

    # --- result files --------------------------------------------------------

    def _show_out_file(self, current: QListWidgetItem | None, _previous=None):
        if current is None:
            self.out_text.clear()
            return
        path = Path(current.data(Qt.ItemDataRole.UserRole))
        try:
            text = path.read_text(encoding="latin-1", errors="replace")
        except OSError as exc:
            text = f"Cannot read {path}: {exc}"
        if not any(line.strip().strip("-") and not line.rstrip().endswith(":") for line in text.splitlines()):
            text += "\n\n(no values — the function returned no data, e.g. no ECU answered)"
        self.out_text.setPlainText(text)

    def _open_log_folder(self):
        path = self.log_combo.currentData()
        folder = Path(path).parent if path else self._paths_provider().bin_dir
        try:
            os.startfile(str(folder))  # noqa: S606 - opening a folder in Explorer
        except Exception:
            logger.exception("Cannot open folder %s", folder)
