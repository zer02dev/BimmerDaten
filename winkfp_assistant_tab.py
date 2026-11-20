"""
winkfp_assistant_tab.py
"What to flash" sub-tab: enter an ECU's HW number (or ZB number) and optionally the
current ZB, get matching ZB numbers and the exact values for WinKFP.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from html import escape as html_escape

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from winkfp_assistant import AssistantResult, Candidate, FlashAssistant, expert_values
from winkfp_presets import ExpertPreset
from winkfp_families import HeaderCache, enrich_with_headers, load_family_records
from winkfp_parser import WinkfpPaths
from winkfp_widgets import (
    COLOR_ERROR,
    COLOR_INFO,
    COLOR_MUTED,
    COLOR_OK,
    COLOR_WARNING,
    LoadingOverlay,
    Worker,
    html_page,
    style_table,
)

logger = logging.getLogger("bimmerdaten.winkfp_assistant_tab")

COLUMNS = ["Family", "ZB number", "HW", "Newest?", "Newer ZB", "Software / vehicle", "Program file", "Data file"]

HELP_HTML = f"""
<h3>Which software fits my ECU?</h3>
<p>Enter the ECU's <b>HW number</b> (7 digits, e.g. <code>7806897</code>) — it is on the ECU label and in
WinKFP <i>Read ident</i> / Tool32 job <code>IDENT</code>. Or enter a <b>ZB number</b>.</p>
<p>For an exact answer also enter the <b>current ZB</b>: WinKFP <i>Special → Read UIF</i> shows the ZB of the
last programming. The assistant then follows the ZB history to the newest ZB — the same as
Comfort mode <i>Update ZUSB</i> (F3) does.</p>
<p style='color:{COLOR_MUTED};'>Only installed data is searched (DATA and families from update backups).</p>
"""


class AssistantTab(QWidget):
    savePresetRequested = pyqtSignal(object)  # ExpertPreset
    def __init__(self, paths_provider: Callable[[], WinkfpPaths], parent=None):
        super().__init__(parent)
        self._paths_provider = paths_provider
        self._assistant: FlashAssistant | None = None
        self._result: AssistantResult | None = None
        self._shown: list[Candidate] = []
        self._worker: Worker | None = None
        self._loaded = False
        self._build_ui()
        self._overlay = LoadingOverlay(self)

    # --- UI ------------------------------------------------------------------

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        bar = QHBoxLayout()
        bar.addWidget(QLabel("HW or ZB number:"))
        self.query_edit = QLineEdit()
        self.query_edit.setPlaceholderText("e.g. 7806897")
        self.query_edit.setMaximumWidth(180)
        self.query_edit.returnPressed.connect(self._search)
        bar.addWidget(self.query_edit)
        bar.addWidget(QLabel("Current ZB (optional):"))
        self.current_edit = QLineEdit()
        self.current_edit.setPlaceholderText("from Read UIF")
        self.current_edit.setMaximumWidth(180)
        self.current_edit.returnPressed.connect(self._search)
        bar.addWidget(self.current_edit)
        self.search_btn = QPushButton("🔎 Find software")
        self.search_btn.clicked.connect(self._search)
        bar.addWidget(self.search_btn)
        bar.addSpacing(16)
        bar.addWidget(QLabel("Filter:"))
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("e.g. E90 AT 130")
        self.filter_edit.setClearButtonEnabled(True)
        self.filter_edit.textChanged.connect(self._apply_filter)
        bar.addWidget(self.filter_edit, 1)
        layout.addLayout(bar)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.table = QTableWidget(0, len(COLUMNS))
        style_table(self.table)
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.currentCellChanged.connect(lambda row, *_: self._show_candidate(row))
        splitter.addWidget(self.table)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        self.result_view = QTextBrowser()
        self.result_view.setHtml(html_page(HELP_HTML))
        right_layout.addWidget(self.result_view, 1)
        self.copy_btn = QPushButton("📋 Copy Expert-mode values")
        self.copy_btn.setEnabled(False)
        self.copy_btn.clicked.connect(self._copy_values)
        self.preset_btn = QPushButton("💾 Save as preset")
        self.preset_btn.setToolTip("Save these values as a WinKFP Expert-mode preset (💾 Presets tab)")
        self.preset_btn.setEnabled(False)
        self.preset_btn.clicked.connect(self._save_preset)
        buttons_row = QHBoxLayout()
        buttons_row.addWidget(self.copy_btn)
        buttons_row.addWidget(self.preset_btn)
        right_layout.addLayout(buttons_row)
        splitter.addWidget(right)
        splitter.setSizes([760, 480])
        layout.addWidget(splitter, 1)

    # --- loading -------------------------------------------------------------

    def showEvent(self, event):
        super().showEvent(event)
        if not self._loaded:
            self._loaded = True
            self.reload()

    def reload(self):
        if self._worker is not None and self._worker.isRunning():
            return
        paths = self._paths_provider()
        self._assistant = None
        self.search_btn.setEnabled(False)
        self.status_label.setText("Loading installed flash data…")

        def job():
            cache = HeaderCache()
            records = load_family_records(paths, include_without_data=False)
            enrich_with_headers(records, cache)
            return FlashAssistant(paths, records, cache)

        worker = Worker(job, self)
        worker.finishedWithResult.connect(self._on_loaded)
        worker.failed.connect(lambda msg: self.status_label.setText(f"Failed: {html_escape(msg)}"))
        worker.finished.connect(self._overlay.stop)
        self._worker = worker
        self._overlay.start("Loading installed flash data (all families and ZB numbers)…")
        worker.start()

    def _on_loaded(self, assistant: FlashAssistant):
        self._assistant = assistant
        self.search_btn.setEnabled(True)
        rows = sum(len(f.rows) for f in assistant.families)
        self.status_label.setText(
            f"Ready — {len(assistant.families)} families with {rows} ZB numbers. Enter a HW or ZB number."
        )
        if self.query_edit.text().strip():
            self._search()

    # --- search ----------------------------------------------------------------

    def _search(self):
        if self._assistant is None:
            return
        result = self._assistant.search(self.query_edit.text(), self.current_edit.text())
        self._result = result
        self.filter_edit.blockSignals(True)
        self.filter_edit.clear()
        self.filter_edit.blockSignals(False)
        self._populate(result)

    def _populate(self, result: AssistantResult):
        self._shown = list(result.candidates)
        self.table.setRowCount(len(self._shown))
        bold_font = None
        for idx, cand in enumerate(self._shown):
            row = cand.row
            entry = row.entry
            items = [
                QTableWidgetItem(cand.record.name),
                QTableWidgetItem(entry.zb_nr),
                QTableWidgetItem(f"{entry.hw_nr}{entry.index}"),
                QTableWidgetItem("✅ newest" if cand.latest else ""),
                QTableWidgetItem("" if cand.latest else cand.family.chain(entry.zb_nr)[-1]),
                QTableWidgetItem(row.description),
                QTableWidgetItem(row.program_file),
                QTableWidgetItem(row.data_file or "—"),
            ]
            if cand.latest:
                items[3].setForeground(QColor(COLOR_OK))
            if not row.program_exists:
                items[6].setForeground(QColor(COLOR_ERROR))
            if not row.data_exists:
                items[7].setForeground(QColor(COLOR_ERROR))
            if cand is result.recommended:
                if bold_font is None:
                    bold_font = items[0].font()
                    bold_font.setBold(True)
                for item in items:
                    item.setFont(bold_font)
                    item.setBackground(QColor("#fff4d6"))
            for col, item in enumerate(items):
                self.table.setItem(idx, col, item)
        self._apply_filter()  # also clears row hiding left over from a previous search
        self.table.resizeColumnsToContents()
        desc_col = COLUMNS.index("Software / vehicle")
        if self.table.columnWidth(desc_col) > 420:
            self.table.setColumnWidth(desc_col, 420)

        lines: list[str] = []
        if result.kind == "hw" and result.number:
            fams = ", ".join(result.families) or "—"
            lines.append(f"<b>HW {html_escape(result.number)}</b> → family <b>{html_escape(fams)}</b>, "
                         f"{len(result.candidates)} matching ZB number(s), "
                         f"{sum(c.latest for c in result.candidates)} newest.")
        elif result.kind == "zb":
            lines.append(f"<b>ZB {html_escape(result.number)}</b> → family <b>{html_escape(', '.join(result.families) or '—')}</b>.")
        for message in result.messages:
            color = COLOR_WARNING if message.startswith("⚠️") else COLOR_INFO
            lines.append(f"<span style='color:{color};'>{html_escape(message)}</span>")
        self.status_label.setText("<br>".join(lines))

        if self._shown:
            row_idx = self._shown.index(result.recommended) if result.recommended is not None else 0
            self.table.setCurrentCell(row_idx, 0)
            self.table.scrollToItem(self.table.item(row_idx, 0))
            # currentCellChanged does not fire when the row index stays the same.
            self._show_candidate(row_idx)
        else:
            self.result_view.setHtml(html_page(HELP_HTML))
            self.copy_btn.setEnabled(False)

    def _apply_filter(self):
        words = [w for w in self.filter_edit.text().lower().split() if w]
        for idx, cand in enumerate(self._shown):
            text = " ".join([
                cand.record.name, cand.row.entry.zb_nr, cand.row.entry.hw_nr, cand.row.description,
            ]).lower()
            self.table.setRowHidden(idx, not all(w in text for w in words))

    # --- details ---------------------------------------------------------------

    def _show_candidate(self, row: int):
        if row < 0 or row >= len(self._shown):
            return
        cand = self._shown[row]
        values = expert_values(cand)
        recommended = self._result is not None and cand is self._result.recommended
        html = []
        if recommended:
            html.append(f"<h3 style='color:{COLOR_OK};'>✅ Recommended: ZB {html_escape(values.zb_nr)}</h3>")
        else:
            html.append(f"<h3>ZB {html_escape(values.zb_nr)}</h3>")
        if cand.row.description:
            html.append(f"<p><b>{html_escape(cand.row.description)}</b></p>")
        for warning in values.warnings:
            html.append(f"<p style='color:{COLOR_WARNING};'>⚠️ {html_escape(warning)}</p>")

        html.append("<h4>Expert mode — enter in WinKFP</h4><table cellspacing='0' cellpadding='3'>")
        for label, value in (
            ("PABD", values.pabd), ("P-SGBD", values.psgbd),
            ("ECU address", f"{values.address} (hex)" if values.address else ""),
            ("Data file", values.data_file or "— (program only)"),
            ("Program file", values.program_file),
        ):
            html.append(f"<tr><td><b>{label}:</b>&nbsp;</td><td><code>{html_escape(value or '?')}</code></td></tr>")
        html.append("</table>")
        html.append(
            f"<p style='color:{COLOR_MUTED};'>Program file = new software, data file = calibration. "
            "Usually program first, then data — WinKFP Comfort mode does both automatically.</p>"
            f"<p style='color:{COLOR_MUTED};'>Expert mode lists program / data files only from DATA\\DEVELOP — "
            "<b>💾 Save as preset</b> → <b>Load into WinKFP</b> copies them there and fills in the configuration.</p>"
        )
        html.append(
            "<h4>Comfort mode</h4>"
            f"<p>Enter ZUSB (F1) → <code>{html_escape(values.zb_nr)}</code>, family "
            f"<code>{html_escape(values.family)}</code>, then choose the integration position.</p>"
        )
        self.result_view.setHtml(html_page("".join(html)))
        self._values_text = values.as_text()
        self._values = values
        self._candidate = cand
        self.copy_btn.setText("📋 Copy Expert-mode values")
        self.copy_btn.setEnabled(True)
        self.preset_btn.setEnabled(True)

    def _save_preset(self):
        values = getattr(self, "_values", None)
        cand = getattr(self, "_candidate", None)
        if values is None or cand is None:
            return
        description = cand.row.description
        name = f"{values.family} {values.zb_nr}" + (f" — {description[:40]}" if description else "")
        self.savePresetRequested.emit(ExpertPreset(
            name=name, family=values.family, zb_nr=values.zb_nr, pabd=values.pabd, psgbd=values.psgbd,
            address=values.address, program_file=values.program_file, data_file=values.data_file,
            notes=description,
        ))

    def _copy_values(self):
        text = getattr(self, "_values_text", "")
        if text:
            QApplication.clipboard().setText(text)
            self.copy_btn.setText("📋 Copied!")
