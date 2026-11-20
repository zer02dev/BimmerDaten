"""
winkfp_families_tab.py
"Families" sub-tab: ECU family inventory with status, vehicles / engines, details,
ZB table, HW groups and restore of families that exist only in update backups.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from html import escape as html_escape

from PyQt6.QtCore import Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from winkfp_families import (
    STATUS_BACKUP_ONLY,
    STATUS_COMPLETE,
    STATUS_INCOMPLETE,
    STATUS_NO_DATA,
    FamilyRecord,
    HeaderCache,
    enrich_with_headers,
    load_family_records,
    load_hwh_groups,
    load_zb_rows,
)
from winkfp_health import CopyFolderFix, apply_fixes, get_backup_root, is_winkfp_running
from winkfp_parser import WinkfpPaths, list_files_ci
from winkfp_widgets import Worker, html_page, style_table

logger = logging.getLogger("bimmerdaten.winkfp_families_tab")

STATUS_STYLE = {
    STATUS_COMPLETE: ("✅ Complete", "#176b1d"),
    STATUS_INCOMPLETE: ("⚠️ Incomplete", "#8a4b00"),
    STATUS_BACKUP_ONLY: ("🗄 Only in backup", "#0f4c8a"),
    STATUS_NO_DATA: ("○ No data", "#4a4a4a"),
}

FILTERS = [
    ("Families with data (installed + backup)", {STATUS_COMPLETE, STATUS_INCOMPLETE, STATUS_BACKUP_ONLY}),
    ("Installed in DATA", {STATUS_COMPLETE, STATUS_INCOMPLETE}),
    ("Problems only", {STATUS_INCOMPLETE}),
    ("Only in backup (restorable)", {STATUS_BACKUP_ONLY}),
    ("All KFCONF families (incl. without data)", {STATUS_COMPLETE, STATUS_INCOMPLETE, STATUS_BACKUP_ONLY, STATUS_NO_DATA}),
]

FAMILY_COLUMNS = ["Family", "Status", "Address", "Vehicles", "Engines", "ECU system", "ZB", "Description"]
ZB_COLUMNS = ["ZB number", "HW number", "Program file", "Data file", "Newer ZB", "Software / vehicle"]


class _Item(QTableWidgetItem):
    def __init__(self, text: str, key=None):
        super().__init__(text)
        self._key = key if key is not None else text.lower()

    def __lt__(self, other):
        if isinstance(other, _Item):
            try:
                return self._key < other._key
            except TypeError:
                return str(self._key) < str(other._key)
        return super().__lt__(other)


def _make_table(columns: list[str], multi: bool = False) -> QTableWidget:
    table = QTableWidget(0, len(columns))
    style_table(table)
    table.setHorizontalHeaderLabels(columns)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(
        QAbstractItemView.SelectionMode.ExtendedSelection if multi else QAbstractItemView.SelectionMode.SingleSelection
    )
    table.setAlternatingRowColors(True)
    table.verticalHeader().setVisible(False)
    header = table.horizontalHeader()
    header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
    header.setStretchLastSection(True)
    return table


class FamiliesTab(QWidget):
    openPrgRequested = pyqtSignal(str)
    filesChanged = pyqtSignal()

    def __init__(self, paths_provider: Callable[[], WinkfpPaths], parent=None):
        super().__init__(parent)
        self._paths_provider = paths_provider
        self._records: list[FamilyRecord] = []
        self._cache: HeaderCache | None = None
        self._worker: Worker | None = None
        self._loaded = False
        self._build_ui()

    # --- UI ------------------------------------------------------------------

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        bar = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search family, vehicle (E46), engine (N47), system (MS43)…")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.textChanged.connect(self._apply_filter)
        bar.addWidget(self.search_edit, 2)
        self.filter_combo = QComboBox()
        for label, _ in FILTERS:
            self.filter_combo.addItem(label)
        self.filter_combo.currentIndexChanged.connect(self._apply_filter)
        bar.addWidget(self.filter_combo)
        self.restore_btn = QPushButton("🗄 Restore from backup")
        self.restore_btn.setToolTip("Copy the selected families from the update backup folder back to DATA")
        self.restore_btn.setEnabled(False)
        self.restore_btn.clicked.connect(self._restore_selected)
        bar.addWidget(self.restore_btn)
        self.reload_btn = QPushButton("🔄")
        self.reload_btn.setToolTip("Reload")
        self.reload_btn.clicked.connect(self.reload)
        bar.addWidget(self.reload_btn)
        layout.addLayout(bar)

        self.count_label = QLabel("")
        layout.addWidget(self.count_label)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.table = _make_table(FAMILY_COLUMNS, multi=True)
        self.table.setSortingEnabled(True)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        splitter.addWidget(self.table)

        self.detail_tabs = QTabWidget()
        self.overview = QTextBrowser()
        self.overview.setOpenLinks(False)
        self.overview.anchorClicked.connect(self._on_anchor)
        self.detail_tabs.addTab(self.overview, "ℹ️ Overview")
        self.zb_table = _make_table(ZB_COLUMNS)
        self.detail_tabs.addTab(self.zb_table, "🔢 ZB numbers")
        self.hwh_view = QTextBrowser()
        self.detail_tabs.addTab(self.hwh_view, "🧩 HW groups")
        splitter.addWidget(self.detail_tabs)
        splitter.setSizes([650, 600])
        layout.addWidget(splitter, 1)

    # --- loading -------------------------------------------------------------

    def showEvent(self, event):
        super().showEvent(event)
        if not self._loaded:
            self._loaded = True
            self.reload()

    def _busy(self) -> bool:
        return self._worker is not None and self._worker.isRunning()

    def reload(self):
        if self._busy():
            return
        paths = self._paths_provider()
        self.count_label.setText("Loading families… (the first time all flash file headers are read, this takes a few seconds)")
        self.reload_btn.setEnabled(False)

        def job():
            cache = HeaderCache()
            records = load_family_records(paths, include_without_data=True)
            enrich_with_headers([r for r in records if r.folder is not None], cache)
            return records, cache

        worker = Worker(job, self)
        worker.finishedWithResult.connect(self._on_loaded)
        worker.failed.connect(lambda msg: self.count_label.setText(f"Failed: {msg}"))
        worker.finished.connect(lambda: self.reload_btn.setEnabled(True))
        self._worker = worker
        worker.start()

    def _on_loaded(self, result):
        self._records, self._cache = result
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(self._records))
        for row, record in enumerate(self._records):
            label, color = STATUS_STYLE[record.status]
            name_item = _Item(record.name)
            name_item.setData(Qt.ItemDataRole.UserRole, row)
            status_item = _Item(label, list(STATUS_STYLE).index(record.status))
            status_item.setForeground(QColor(color))
            if record.problems:
                status_item.setToolTip("\n".join(record.problems))
            values = [
                name_item,
                status_item,
                _Item(f"0x{record.address}" if record.address else ""),
                _Item(", ".join(sorted(record.chassis))),
                _Item(", ".join(sorted(record.engines))),
                _Item(", ".join(sorted(record.systems))),
                _Item(str(record.zb_count) if record.zb_count else "", record.zb_count),
                _Item(record.description),
            ]
            for col, item in enumerate(values):
                self.table.setItem(row, col, item)
        self.table.setSortingEnabled(True)
        self.table.sortItems(0, Qt.SortOrder.AscendingOrder)
        self.table.resizeColumnsToContents()
        for col in (FAMILY_COLUMNS.index("Vehicles"), FAMILY_COLUMNS.index("Engines"), FAMILY_COLUMNS.index("ECU system")):
            if self.table.columnWidth(col) > 220:
                self.table.setColumnWidth(col, 220)
        self._apply_filter()

    # --- filtering / selection -----------------------------------------------

    def _record_at(self, table_row: int) -> FamilyRecord | None:
        item = self.table.item(table_row, 0)
        if item is None:
            return None
        idx = item.data(Qt.ItemDataRole.UserRole)
        return self._records[idx] if idx is not None and 0 <= idx < len(self._records) else None

    def _apply_filter(self):
        allowed = FILTERS[self.filter_combo.currentIndex()][1]
        text = self.search_edit.text().strip().lower()
        visible = 0
        for table_row in range(self.table.rowCount()):
            record = self._record_at(table_row)
            if record is None:
                continue
            show = record.status in allowed
            if show and text:
                haystack = " ".join([
                    record.name, record.description, " ".join(record.chassis), " ".join(record.engines),
                    " ".join(record.systems), record.kfconf.pabd if record.kfconf else "",
                ]).lower()
                show = text in haystack
            self.table.setRowHidden(table_row, not show)
            visible += show
        counts = {status: sum(1 for r in self._records if r.status == status) for status in STATUS_STYLE}
        self.count_label.setText(
            f"{visible} shown · {counts[STATUS_COMPLETE]} complete · {counts[STATUS_INCOMPLETE]} incomplete · "
            f"{counts[STATUS_BACKUP_ONLY]} only in backup · {counts[STATUS_NO_DATA]} without data"
        )

    def _selected_records(self) -> list[FamilyRecord]:
        rows = sorted({index.row() for index in self.table.selectionModel().selectedRows()})
        return [r for r in (self._record_at(row) for row in rows) if r is not None]

    def _on_selection_changed(self):
        selected = self._selected_records()
        restorable = [r for r in selected if r.status == STATUS_BACKUP_ONLY]
        self.restore_btn.setEnabled(bool(restorable))
        self.restore_btn.setText(f"🗄 Restore from backup ({len(restorable)})" if restorable else "🗄 Restore from backup")
        current = self._record_at(self.table.currentRow())
        if current is not None:
            self._show_record(current)

    # --- details ---------------------------------------------------------------

    def _show_record(self, record: FamilyRecord):
        label, color = STATUS_STYLE[record.status]
        html = [f"<h3>{html_escape(record.name)}</h3>", f"<p style='color:{color};'><b>{label}</b></p>"]
        if record.status == STATUS_BACKUP_ONLY:
            html.append(
                f"<p style='color:#0f4c8a;'>This family was in DATA before an update and is now only in "
                f"<b>{html_escape(record.backup_name)}</b>. Select it and click <b>🗄 Restore from backup</b> "
                "to copy it back.</p>"
            )
        elif record.status == STATUS_NO_DATA:
            html.append(
                "<p style='color:#3f3f3f;'>WinKFP knows this ECU family (KFCONF), but no flash data is installed. "
                "It has to come from an SP-Daten package.</p>"
            )
        if record.problems:
            html.append("<p><b>Problems:</b></p><ul>" + "".join(f"<li>{html_escape(p)}</li>" for p in record.problems) + "</ul>")

        rows: list[tuple[str, str]] = []
        if record.description:
            rows.append(("Description (INFO)", html_escape(record.description)))
        if record.address:
            rows.append(("ECU address", f"0x{html_escape(record.address)}"))
        if record.chassis:
            rows.append(("Vehicles", html_escape(", ".join(sorted(record.chassis)))))
        if record.engines:
            rows.append(("Engines", html_escape(", ".join(sorted(record.engines)))))
        if record.systems:
            rows.append(("ECU system", html_escape(", ".join(sorted(record.systems)))))
        if record.kfconf:
            entry = record.kfconf
            mark = lambda ok: "✅" if ok else "❌ missing"  # noqa: E731
            rows.append(("PABD", f"{html_escape(entry.pabd)} {mark(record.pabd_ok)}"))
            psgbd = html_escape(entry.psgbd)
            psgbd_html = f"<a href='prg:{psgbd}'>{psgbd}</a>" if record.psgbd_ok else psgbd
            rows.append(("P-SGBD", f"{psgbd_html} {mark(record.psgbd_ok)}"))
            rows.append(("Data file prefix", html_escape(entry.data_prefix)))
            rows.append(("KFCONF", f"{html_escape(entry.source_file)}, line {entry.line_no}"))
        if record.folder is not None:
            folder = record.folder
            rows.append(("Folder", html_escape(str(folder.path))))
            rows.append((
                "Files",
                f"{folder.program_files} program (0PA) · {folder.data_files} data (0DA) · {folder.naab_files} NAAB (0BA)",
            ))
            rows.append(("ZB numbers", str(record.zb_count)))
        html.append("<table cellspacing='0' cellpadding='2'>")
        for key, value in rows:
            html.append(f"<tr><td valign='top'><b>{key}:</b>&nbsp;</td><td>{value}</td></tr>")
        html.append("</table>")
        if record.kfconf and record.psgbd_ok:
            html.append("<p style='color:#3f3f3f;'>Click the P-SGBD to open it in the Diagnosis tab.</p>")
        self.overview.setHtml(html_page("".join(html)))
        self._fill_zb(record)
        self._fill_hwh(record)

    def _fill_zb(self, record: FamilyRecord):
        self.zb_table.setRowCount(0)
        if self._cache is None:
            return
        try:
            rows = load_zb_rows(record, self._cache)
        except Exception:
            logger.exception("Failed to load ZB rows for %s", record.name)
            rows = []
        self.zb_table.setRowCount(len(rows))
        red = QColor("#a8001c")
        for idx, row in enumerate(rows):
            entry = row.entry
            items = [
                QTableWidgetItem(entry.zb_nr),
                QTableWidgetItem(f"{entry.hw_nr}{entry.index}"),
                QTableWidgetItem(row.program_file),
                QTableWidgetItem(row.data_file or "—"),
                QTableWidgetItem(row.latest_zb),
                QTableWidgetItem(row.description),
            ]
            if not row.program_exists:
                items[2].setForeground(red)
                items[2].setToolTip("File missing")
            if not row.data_exists:
                items[3].setForeground(red)
                items[3].setToolTip("File missing")
            if row.latest_zb:
                items[4].setToolTip("A newer ZB exists for this one (ZB history)")
            for col, item in enumerate(items):
                self.zb_table.setItem(idx, col, item)
        self.zb_table.resizeColumnsToContents()

    def _fill_hwh(self, record: FamilyRecord):
        groups = load_hwh_groups(record)
        if not groups:
            self.hwh_view.setHtml(html_page("<p style='color:#3f3f3f;'>No HW history (HWH) available.</p>"))
            return
        html = [
            "<p>Hardware numbers in the same group are compatible with each other "
            "(the letter in brackets is the release status from the HWH file).</p>"
        ]
        for number, group in enumerate(groups, start=1):
            html.append(f"<p><b>Group {number}</b> ({len(group)})<br>{html_escape(', '.join(group))}</p>")
        self.hwh_view.setHtml(html_page("".join(html)))

    def _on_anchor(self, url: QUrl):
        target = url.toString()
        if not target.startswith("prg:"):
            return
        ecu_dir = self._paths_provider().ecu_dir
        match = list_files_ci(ecu_dir).get(target[4:].lower())
        if match is not None:
            self.openPrgRequested.emit(str(match))

    # --- restore -----------------------------------------------------------------

    def _restore_selected(self):
        records = [r for r in self._selected_records() if r.status == STATUS_BACKUP_ONLY and r.folder is not None]
        if not records:
            return
        paths = self._paths_provider()
        if is_winkfp_running():
            QMessageBox.warning(self, "WinKFP is running", "Close WinKFP before restoring families.")
            return
        fixes = [
            CopyFolderFix(
                description=f"Restore family {r.name} from {r.backup_name}",
                source=r.folder.path,
                destination=paths.data_dir / r.folder.path.name,
            )
            for r in records
        ]
        problems = [msg for msg in (fix.validate() for fix in fixes) if msg]
        if problems:
            QMessageBox.warning(self, "Restore families", "\n".join(problems))
            return

        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle("Restore families")
        box.setText(f"Copy {len(records)} famil{'y' if len(records) == 1 else 'ies'} back to DATA?\n\n"
                    + ", ".join(r.name for r in records))
        box.setInformativeText(
            "Only missing folders are added — nothing in DATA is overwritten. "
            f"The change is recorded in {get_backup_root()} and can be undone in 🩺 Health → Restore backup…"
        )
        box.setDetailedText("\n\n".join(fix.preview() for fix in fixes))
        box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel)
        box.setDefaultButton(QMessageBox.StandardButton.Cancel)
        if box.exec() != QMessageBox.StandardButton.Yes:
            return

        self.restore_btn.setEnabled(False)
        self.count_label.setText(f"Restoring {len(records)} famil{'y' if len(records) == 1 else 'ies'}…")
        worker = Worker(lambda: apply_fixes(fixes, paths), self)
        worker.finishedWithResult.connect(lambda record: self._on_restored(record, records))
        worker.failed.connect(self._on_restore_failed)
        worker.finished.connect(self.reload)
        self._worker = worker
        worker.start()

    def _on_restored(self, backup_record, records: list[FamilyRecord]):
        QMessageBox.information(
            self, "Restore families",
            f"Restored: {', '.join(r.name for r in records)}\n\n"
            "Start WinKFP again so it sees the restored families.",
        )
        self.filesChanged.emit()

    def _on_restore_failed(self, message: str):
        QMessageBox.critical(self, "Restore failed", message)
