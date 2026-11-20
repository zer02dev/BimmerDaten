"""
winkfp_sgdat_tab.py
"SGDAT" sub-tab: all *.ipo files classified as flash (PABD), coding (CABD) or SWT,
with job list, author and KFCONF references.
"""
from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from html import escape as html_escape

from PyQt6.QtCore import Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from winkfp_parser import (
    IPO_KIND_CABD,
    IPO_KIND_PABD,
    IPO_KIND_SWT,
    IpoInfo,
    KfconfEntry,
    WinkfpPaths,
    classify_ipo,
    ipo_family_stem,
    ipo_version,
    list_family_folders,
    list_files_ci,
    load_kfconf,
)
from winkfp_widgets import Worker

logger = logging.getLogger("bimmerdaten.winkfp_sgdat_tab")

KIND_LABELS = {
    IPO_KIND_PABD: ("🔧 Flash (PABD)", "#1f5f9e"),
    IPO_KIND_CABD: ("✏️ Coding (CABD)", "#8a5a00"),
    IPO_KIND_SWT: ("🔑 Activation codes (SWT/FSC)", "#6a3d9a"),
}
UNKNOWN_LABEL = ("❓ Unknown", "#777777")

KIND_DESCRIPTIONS = {
    IPO_KIND_PABD: (
        "<b>Flash sequence description (PABD)</b> — used by WinKFP to program this ECU. "
        "In Expert mode select it with the <i>PABD</i> button."
    ),
    IPO_KIND_CABD: (
        "<b>Coding sequence description (CABD)</b> — used by NCS Expert for coding "
        "(A_*.ipo files; A_EWSSYN synchronises the EWS immobiliser with the engine ECU). "
        "<span style='color:#b00020;'><b>Do not select it as PABD in WinKFP</b></span>: it has no flash jobs "
        "and WinKFP stops with COAPI error 1063 (CABD parameter error, e.g. SET_ECU_ADDRESS)."
    ),
    IPO_KIND_SWT: (
        "<b>Activation codes (SWT / FSC)</b> — stores BMW enabling codes (FSC, Freischaltcode) and "
        "certificates in an ECU, e.g. to unlock a navigation map update or Night Vision. "
        "Not used for flashing or coding."
    ),
}

COLUMNS = ["File", "Type", "Family", "Ver.", "Used in KFCONF", "Data installed", "Modified", "Author"]


@dataclass
class SgdatRow:
    info: IpoInfo
    stem: str
    version: int
    modified: datetime | None
    kfconf: list[KfconfEntry] = field(default_factory=list)
    data_installed: bool = False
    newer: str = ""  # name of a newer PABD of the same family, if any


def load_sgdat_rows(paths: WinkfpPaths) -> list[SgdatRow]:
    kfconf_by_pabd: dict[str, list[KfconfEntry]] = {}
    for entry in load_kfconf(paths.gdaten_dir):
        kfconf_by_pabd.setdefault(entry.pabd.lower(), []).append(entry)
    installed = {f.name for f in list_family_folders(paths.data_dir)}

    rows: list[SgdatRow] = []
    for name, path in sorted(list_files_ci(paths.sgdat_dir).items()):
        if not name.endswith(".ipo"):
            continue
        info = classify_ipo(path)
        try:
            modified = datetime.fromtimestamp(path.stat().st_mtime)
        except OSError:
            modified = None
        refs = kfconf_by_pabd.get(name, [])
        rows.append(SgdatRow(
            info=info,
            stem=re.sub(r"^A_", "", ipo_family_stem(path.name)) if info.kind == IPO_KIND_CABD else ipo_family_stem(path.name),
            version=ipo_version(path.name),
            modified=modified,
            kfconf=refs,
            data_installed=any(e.family.upper() in installed for e in refs),
        ))

    newest: dict[str, SgdatRow] = {}
    for row in rows:
        if row.info.kind != IPO_KIND_PABD:
            continue
        current = newest.get(row.stem)
        if current is None or row.version > current.version:
            newest[row.stem] = row
    for row in rows:
        if row.info.kind == IPO_KIND_PABD:
            best = newest.get(row.stem)
            if best is not None and best is not row and best.version > row.version:
                row.newer = best.info.name
    return rows


class _SortItem(QTableWidgetItem):
    """Table item sorting by an explicit key."""

    def __init__(self, text: str, key=None):
        super().__init__(text)
        self._key = key if key is not None else text.lower()

    def __lt__(self, other):
        if isinstance(other, _SortItem):
            try:
                return self._key < other._key
            except TypeError:
                return str(self._key) < str(other._key)
        return super().__lt__(other)


class SgdatTab(QWidget):
    openPrgRequested = pyqtSignal(str)

    def __init__(self, paths_provider: Callable[[], WinkfpPaths], parent=None):
        super().__init__(parent)
        self._paths_provider = paths_provider
        self._rows: list[SgdatRow] = []
        self._worker: Worker | None = None
        self._loaded = False
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        bar = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search file, family, author or job…")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.textChanged.connect(self._apply_filter)
        bar.addWidget(self.search_edit, 2)

        self.type_combo = QComboBox()
        self.type_combo.addItem("All types", "")
        for kind, (label, _) in KIND_LABELS.items():
            self.type_combo.addItem(label, kind)
        self.type_combo.addItem(UNKNOWN_LABEL[0], "?")
        self.type_combo.currentIndexChanged.connect(self._apply_filter)
        bar.addWidget(self.type_combo)

        self.installed_check = QCheckBox("Only families with installed data")
        self.installed_check.toggled.connect(self._apply_filter)
        bar.addWidget(self.installed_check)

        self.count_label = QLabel("")
        bar.addWidget(self.count_label)
        layout.addLayout(bar)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setSortingEnabled(True)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        self.table.currentCellChanged.connect(lambda row, *_: self._show_details(row))
        splitter.addWidget(self.table)

        self.details = QTextBrowser()
        self.details.setOpenLinks(False)
        self.details.anchorClicked.connect(self._on_anchor)
        splitter.addWidget(self.details)
        splitter.setSizes([760, 380])
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
        self.count_label.setText("Loading SGDAT…")
        self.table.setRowCount(0)
        self.details.clear()
        worker = Worker(lambda: load_sgdat_rows(paths), self)
        worker.finishedWithResult.connect(self._on_loaded)
        worker.failed.connect(lambda msg: self.count_label.setText(f"Failed: {msg}"))
        self._worker = worker
        worker.start()

    def _on_loaded(self, rows: list[SgdatRow]):
        self._rows = rows
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(rows))
        for idx, row in enumerate(rows):
            label, color = KIND_LABELS.get(row.info.kind, UNKNOWN_LABEL)
            name_item = _SortItem(row.info.name)
            name_item.setData(Qt.ItemDataRole.UserRole, idx)
            type_item = _SortItem(label)
            type_item.setForeground(QColor(color))
            families = ", ".join(sorted({e.family for e in row.kfconf}))
            used_item = _SortItem(families or "—", families.lower() or "~")
            data_item = _SortItem("✅" if row.data_installed else "", 0 if row.data_installed else 1)
            if row.newer:
                name_item.setToolTip(f"Newer version available: {row.newer}")
                name_item.setForeground(QColor("#888888"))
            stamp = row.modified.strftime("%Y-%m-%d") if row.modified else ""
            items = [
                name_item,
                type_item,
                _SortItem(row.stem),
                _SortItem(str(row.version) if row.version >= 0 else "", row.version),
                used_item,
                data_item,
                _SortItem(stamp, row.modified.timestamp() if row.modified else 0),
                _SortItem(row.info.author),
            ]
            for col, item in enumerate(items):
                self.table.setItem(idx, col, item)
        self.table.setSortingEnabled(True)
        self.table.sortItems(0, Qt.SortOrder.AscendingOrder)
        self.table.resizeColumnsToContents()
        self._apply_filter()

    # --- filtering -------------------------------------------------------------

    def _row_for_table_row(self, table_row: int) -> SgdatRow | None:
        item = self.table.item(table_row, 0)
        if item is None:
            return None
        idx = item.data(Qt.ItemDataRole.UserRole)
        return self._rows[idx] if idx is not None and 0 <= idx < len(self._rows) else None

    def _apply_filter(self):
        text = self.search_edit.text().strip().lower()
        kind = self.type_combo.currentData()
        only_installed = self.installed_check.isChecked()
        visible = 0
        counts = {IPO_KIND_PABD: 0, IPO_KIND_CABD: 0}
        for table_row in range(self.table.rowCount()):
            row = self._row_for_table_row(table_row)
            if row is None:
                continue
            show = True
            if kind and row.info.kind != kind:
                show = False
            if only_installed and not row.data_installed:
                show = False
            if show and text:
                haystack = " ".join([
                    row.info.name, row.stem, row.info.author, row.info.source_name,
                    " ".join(row.info.jobs), " ".join(e.family for e in row.kfconf),
                ]).lower()
                show = text in haystack
            self.table.setRowHidden(table_row, not show)
            if show:
                visible += 1
                if row.info.kind in counts:
                    counts[row.info.kind] += 1
        self.count_label.setText(
            f"{visible} of {len(self._rows)} files · {counts[IPO_KIND_PABD]} flash · {counts[IPO_KIND_CABD]} coding"
        )

    # --- details ---------------------------------------------------------------

    def _show_details(self, table_row: int):
        row = self._row_for_table_row(table_row)
        if row is None:
            self.details.clear()
            return
        info = row.info
        label, color = KIND_LABELS.get(info.kind, UNKNOWN_LABEL)
        html = [
            f"<h3>{html_escape(info.name)}</h3>",
            f"<p style='color:{color};'><b>{html_escape(label)}</b></p>",
            f"<p>{KIND_DESCRIPTIONS.get(info.kind, 'Type could not be recognised.')}</p>",
        ]
        if row.newer:
            html.append(
                f"<p style='color:#b36b00;'>⚠️ A newer version of this PABD is available: "
                f"<b>{html_escape(row.newer)}</b></p>"
            )
        meta = [
            ("Family stem", row.stem),
            ("Version prefix", str(row.version) if row.version >= 0 else "—"),
            ("Author", info.author or "—"),
            ("Source", info.source_name or "—"),
            ("Size", f"{info.size:,} bytes".replace(",", " ")),
            ("Modified", row.modified.strftime("%Y-%m-%d %H:%M") if row.modified else "—"),
        ]
        html.append("<table cellspacing='0' cellpadding='2'>")
        for key, value in meta:
            html.append(f"<tr><td><b>{key}:</b>&nbsp;</td><td>{html_escape(value)}</td></tr>")
        html.append("</table>")

        if row.kfconf:
            html.append("<h4>Used in KFCONF (Comfort mode)</h4><ul>")
            for entry in row.kfconf:
                addr = f"0x{entry.address}" if entry.address else "?"
                html.append(
                    f"<li><b>{html_escape(entry.family)}</b> — ECU address {html_escape(addr)}, "
                    f"P-SGBD <a href='prg:{html_escape(entry.psgbd)}'>{html_escape(entry.psgbd)}</a>"
                    f"{' · data installed' if row.data_installed else ''}</li>"
                )
            html.append("</ul><p style='color:#666;'>Click a P-SGBD to open it in the Diagnosis tab.</p>")
        elif info.kind == IPO_KIND_PABD:
            html.append("<p style='color:#666;'>Not referenced in KFCONF — usable in Expert mode only.</p>")

        if info.jobs:
            html.append("<h4>Jobs</h4><p>" + ", ".join(html_escape(j) for j in info.jobs) + "</p>")
        self.details.setHtml("".join(html))

    def _on_anchor(self, url: QUrl):
        target = url.toString()
        if not target.startswith("prg:"):
            return
        name = target[4:]
        ecu_dir = self._paths_provider().ecu_dir
        match = list_files_ci(ecu_dir).get(name.lower())
        if match is None:
            self.details.append(f"<p style='color:#b00020;'>{html_escape(name)} not found in {html_escape(str(ecu_dir))}</p>")
            return
        self.openPrgRequested.emit(str(match))
