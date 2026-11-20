"""
winkfp_updates_tab.py
"Updates" sub-tab: detects changes of the WinKFP installation (e.g. after an
SP-Daten update) by comparing with a saved snapshot or an update backup folder.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from html import escape as html_escape

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTextBrowser,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from winkfp_parser import WinkfpPaths
from winkfp_widgets import LoadingOverlay, Worker, html_page, style_tree
from winkfp_snapshot import (
    SECTION_DATA,
    SECTION_TITLES,
    BackupTarget,
    ComparisonResult,
    Snapshot,
    compare_backup,
    compare_snapshots,
    latest_snapshot,
    list_backup_targets,
    list_snapshots,
    save_snapshot,
    take_snapshot,
)

logger = logging.getLogger("bimmerdaten.winkfp_updates_tab")

MAX_FILES_PER_GROUP = 500


class UpdatesTab(QWidget):
    """Snapshot comparison and backup-folder comparison."""

    # Emitted after the automatic check: (changes detected, short message).
    changesDetected = pyqtSignal(bool, str)

    def __init__(self, paths_provider: Callable[[], WinkfpPaths], parent=None):
        super().__init__(parent)
        self._paths_provider = paths_provider
        self._worker: Worker | None = None
        self._auto_checked = False
        self._build_ui()
        self._overlay = LoadingOverlay(self)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        bar = QHBoxLayout()
        bar.addWidget(QLabel("Compare current installation with:"))
        self.target_combo = QComboBox()
        self.target_combo.setMinimumWidth(360)
        bar.addWidget(self.target_combo, 1)
        self.compare_btn = QPushButton("🔍 Compare")
        self.compare_btn.clicked.connect(self._compare_selected)
        self.baseline_btn = QPushButton("📸 Save current state as baseline")
        self.baseline_btn.setToolTip(
            "Remember the current installation. Later changes (e.g. after an update) are compared to it."
        )
        self.baseline_btn.clicked.connect(lambda: self.save_baseline())
        bar.addWidget(self.compare_btn)
        bar.addWidget(self.baseline_btn)
        layout.addLayout(bar)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        splitter = QSplitter(Qt.Orientation.Vertical)
        self.tree = QTreeWidget()
        style_tree(self.tree)
        self.tree.setHeaderLabels(["Change", "Count"])
        self.tree.setAlternatingRowColors(True)
        header = self.tree.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        splitter.addWidget(self.tree)

        self.notes = QTextBrowser()
        splitter.addWidget(self.notes)
        splitter.setSizes([420, 140])
        layout.addWidget(splitter, 1)

    # --- targets ---------------------------------------------------------------

    def reload_targets(self):
        paths = self._paths_provider()
        self.target_combo.clear()
        for snapshot in list_snapshots():
            if str(snapshot.nfs_root) and snapshot.nfs_root != str(paths.nfs_root):
                continue
            self.target_combo.addItem(f"📸 Snapshot {snapshot.title}", snapshot)
        for target in list_backup_targets(paths):
            self.target_combo.addItem(f"🗄 Backup {target.title}", target)
        has_targets = self.target_combo.count() > 0
        self.compare_btn.setEnabled(has_targets)
        if not has_targets:
            self.target_combo.addItem("(no snapshots or backup folders yet)")

    def showEvent(self, event):
        super().showEvent(event)
        self.reload_targets()

    # --- automatic check -------------------------------------------------------

    def auto_check(self):
        """Compare with the latest snapshot; create the first baseline silently."""
        if self._auto_checked or self._busy():
            return
        self._auto_checked = True
        paths = self._paths_provider()
        if not paths.is_valid():
            return

        def job():
            current = take_snapshot(paths)
            baseline = latest_snapshot(paths)
            if baseline is None:
                current.label = "first baseline"
                save_snapshot(current)
                return ("baseline", current)
            return ("compare", compare_snapshots(baseline, current))

        self._run(job, self._on_auto_result, "Checking installation for changes…")

    def _on_auto_result(self, result):
        kind, payload = result
        self.reload_targets()
        if kind == "baseline":
            self.status_label.setText(
                f"First baseline snapshot saved ({payload.title}). "
                "Future changes of the installation will be detected automatically."
            )
            self.changesDetected.emit(False, "")
            return
        self._show_result(payload)
        if payload.has_changes:
            self.changesDetected.emit(True, self._short_summary(payload))
        else:
            self.changesDetected.emit(False, "")

    # --- manual actions --------------------------------------------------------

    def _compare_selected(self):
        target = self.target_combo.currentData()
        if target is None:
            return
        paths = self._paths_provider()
        if isinstance(target, Snapshot):
            self._run(lambda: compare_snapshots(target, take_snapshot(paths)), self._show_result,
                      f"Comparing with snapshot {target.title}…")
        elif isinstance(target, BackupTarget):
            self._run(lambda: compare_backup(target), self._show_result,
                      f"Comparing {target.title}… (may take a while for EDIABAS Ecu)")

    def save_baseline(self, label: str = "baseline"):
        paths = self._paths_provider()
        if not paths.is_valid():
            QMessageBox.warning(self, "Snapshot", "WinKFP installation not found.")
            return

        def job():
            snapshot = take_snapshot(paths, label=label)
            save_snapshot(snapshot)
            return snapshot

        def done(snapshot):
            self.reload_targets()
            self.status_label.setText(f"Baseline snapshot saved: {snapshot.title}")
            self.tree.clear()
            self.notes.clear()
            self.changesDetected.emit(False, "")

        self._run(job, done, "Saving snapshot…")

    # --- worker helpers --------------------------------------------------------

    def _busy(self) -> bool:
        return self._worker is not None and self._worker.isRunning()

    def _run(self, func, on_done, message: str):
        if self._busy():
            return
        self.status_label.setText(message)
        self.compare_btn.setEnabled(False)
        self.baseline_btn.setEnabled(False)
        worker = Worker(func, self)
        worker.finishedWithResult.connect(on_done)
        worker.failed.connect(self._on_failed)
        worker.finished.connect(self._on_worker_finished)
        self._worker = worker
        self._overlay.start(message)
        worker.start()

    def _on_worker_finished(self):
        self._overlay.stop()
        self.compare_btn.setEnabled(self.target_combo.currentData() is not None)
        self.baseline_btn.setEnabled(True)

    def _on_failed(self, message: str):
        self.status_label.setText(f"<span style='color:#a8001c;'>Failed: {html_escape(message)}</span>")

    # --- result display --------------------------------------------------------

    @staticmethod
    def _short_summary(result: ComparisonResult) -> str:
        def families(count: int) -> str:
            return f"{count} famil{'y' if count == 1 else 'ies'}"

        parts: list[str] = []
        if result.families.removed:
            parts.append(f"{families(len(result.families.removed))} removed")
        if result.families.added:
            parts.append(f"{families(len(result.families.added))} added")
        if result.families.changed:
            parts.append(f"{families(len(result.families.changed))} changed")
        for section, diff in result.sections.items():
            if section != SECTION_DATA and diff.total:
                parts.append(f"{SECTION_TITLES[section].split(' ')[0]}: {diff.total} file(s)")
        if result.new_backups:
            parts.append(f"new backup folder(s): {', '.join(result.new_backups)}")
        return "; ".join(parts) or "files changed"

    def _add_group(self, title: str, items: list[str], color: str = "") -> None:
        if not items:
            return
        group = QTreeWidgetItem([title, str(len(items))])
        if color:
            group.setForeground(0, QColor(color))
        font = group.font(0)
        font.setBold(True)
        group.setFont(0, font)
        for value in items[:MAX_FILES_PER_GROUP]:
            group.addChild(QTreeWidgetItem([value, ""]))
        if len(items) > MAX_FILES_PER_GROUP:
            group.addChild(QTreeWidgetItem([f"… and {len(items) - MAX_FILES_PER_GROUP} more", ""]))
        self.tree.addTopLevelItem(group)

    def _show_result(self, result: ComparisonResult):
        self.tree.clear()
        families = result.families
        self._add_group("Families removed from DATA", families.removed, "#a8001c")
        self._add_group("Families added to DATA", families.added, "#176b1d")
        self._add_group(
            "Families with changed files",
            [f"{fam} ({count} file(s))" for fam, count in families.changed.items()], "#8a4b00",
        )
        self._add_group("New update backup folders", result.new_backups, "#0f4c8a")
        for section, diff in result.sections.items():
            title = SECTION_TITLES.get(section, section)
            self._add_group(f"{title}: files added", diff.added)
            self._add_group(f"{title}: files removed", diff.removed)
            self._add_group(f"{title}: files changed", diff.changed)

        if result.has_changes:
            self.status_label.setText(
                f"<b>Changes</b> between <i>{html_escape(result.old_title)}</i> and "
                f"<i>{html_escape(result.new_title)}</i>: {html_escape(self._short_summary(result))}"
            )
        else:
            self.status_label.setText(
                f"<span style='color:#176b1d;'><b>No changes</b></span> between "
                f"<i>{html_escape(result.old_title)}</i> and <i>{html_escape(result.new_title)}</i>."
            )

        notes: list[str] = []
        if families.removed:
            notes.append(
                "⚠️ <b>Families were removed from DATA.</b> An update probably replaced the DATA folder "
                "instead of merging it. Those families can no longer be flashed; they can be restored "
                "from backup folders in the 📦 Families tab (stage E5)."
            )
        if result.gdaten_changed:
            notes.append(
                "⚠️ <b>gdaten changed</b> (" + html_escape(", ".join(result.gdaten_changed[:6])) + "). "
                "Run the 🩺 Health check — KFCONF / INFO may no longer match SGDAT and DATA."
            )
        if families.added or any(d.total for s, d in result.sections.items() if s != SECTION_DATA):
            notes.append("ℹ️ New or changed files: run the 🩺 Health check to verify the installation.")
        if result.has_changes:
            notes.append(
                "When everything is fine, click <b>📸 Save current state as baseline</b> so the next "
                "update is compared against this state."
            )
        self.notes.setHtml(html_page("<br><br>".join(notes)))
