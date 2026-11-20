"""
winkfp_health_tab.py
"Health" sub-tab of the WinKFP tab: installation check, fixes with backup, restore.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from html import escape as html_escape

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
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

from winkfp_health import (
    SEVERITY_ERROR,
    SEVERITY_INFO,
    SEVERITY_OK,
    SEVERITY_WARNING,
    BackupRecord,
    HealthReport,
    Issue,
    apply_fixes,
    get_backup_root,
    is_winkfp_running,
    list_backups,
    restore_backup,
    run_health_check,
)
from winkfp_parser import WinkfpPaths

logger = logging.getLogger("bimmerdaten.winkfp_health_tab")

SEVERITY_STYLE = {
    SEVERITY_ERROR: ("❌", "Error", "#b00020"),
    SEVERITY_WARNING: ("⚠️", "Warning", "#b36b00"),
    SEVERITY_INFO: ("ℹ️", "Info", "#1f5f9e"),
    SEVERITY_OK: ("✅", "OK", "#2a8f2a"),
}

ISSUE_ROLE = Qt.ItemDataRole.UserRole + 1


class RestoreDialog(QDialog):
    def __init__(self, backups: list[BackupRecord], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Restore WinKFP backup")
        self.resize(760, 380)
        self._backups = backups

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"Backups made by BimmerDaten ({get_backup_root()}):"))

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Created", "Changes", "Files", "Status"])
        self.tree.setRootIsDecorated(False)
        for record in backups:
            item = QTreeWidgetItem([
                record.created.replace("T", " "),
                record.description,
                "\n".join(f"{f.get('action')}: {f.get('rel')}" for f in record.files),
                "restored" if record.restored else "",
            ])
            item.setToolTip(1, record.description)
            self.tree.addTopLevelItem(item)
        header = self.tree.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        if backups:
            self.tree.setCurrentItem(self.tree.topLevelItem(0))
        layout.addWidget(self.tree, 1)

        buttons = QDialogButtonBox()
        self.restore_btn = QPushButton("↩ Restore selected")
        self.restore_btn.setEnabled(bool(backups))
        buttons.addButton(self.restore_btn, QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.addButton(QDialogButtonBox.StandardButton.Close)
        self.restore_btn.clicked.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def selected(self) -> BackupRecord | None:
        item = self.tree.currentItem()
        if item is None:
            return None
        return self._backups[self.tree.indexOfTopLevelItem(item)]


class HealthTab(QWidget):
    """Installation check with fixes."""

    filesChanged = pyqtSignal()
    showUpdatesRequested = pyqtSignal()

    def __init__(self, paths_provider: Callable[[], WinkfpPaths], parent=None):
        super().__init__(parent)
        self._paths_provider = paths_provider
        self._report: HealthReport | None = None
        self._checked_once = False
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        bar = QHBoxLayout()
        self.summary_label = QLabel("Not checked yet.")
        bar.addWidget(self.summary_label, 1)
        self.check_btn = QPushButton("▶ Run check")
        self.check_btn.clicked.connect(self.run_check)
        self.fix_btn = QPushButton("🛠 Fix selected")
        self.fix_btn.setEnabled(False)
        self.fix_btn.clicked.connect(self._fix_selected)
        self.restore_btn = QPushButton("↩ Restore backup…")
        self.restore_btn.clicked.connect(self._restore)
        for button in (self.check_btn, self.fix_btn, self.restore_btn):
            bar.addWidget(button)
        layout.addLayout(bar)

        self.update_banner = QWidget()
        self.update_banner.setStyleSheet(
            "QWidget { background-color: #fff4d6; border: 1px solid #e0b84c; border-radius: 3px; }"
            "QLabel { border: none; }"
        )
        banner_layout = QHBoxLayout(self.update_banner)
        banner_layout.setContentsMargins(8, 4, 8, 4)
        self.update_banner_label = QLabel("")
        self.update_banner_label.setWordWrap(True)
        banner_layout.addWidget(self.update_banner_label, 1)
        show_changes_btn = QPushButton("🔄 Show changes")
        show_changes_btn.clicked.connect(self.showUpdatesRequested.emit)
        banner_layout.addWidget(show_changes_btn)
        self.update_banner.hide()
        layout.addWidget(self.update_banner)

        splitter = QSplitter(Qt.Orientation.Vertical)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Issue", "Category", "Fix"])
        self.tree.setRootIsDecorated(False)
        self.tree.setAlternatingRowColors(True)
        header = self.tree.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.tree.currentItemChanged.connect(self._show_details)
        self.tree.itemChanged.connect(lambda *_: self._update_fix_button())
        splitter.addWidget(self.tree)

        self.details = QTextBrowser()
        self.details.setOpenExternalLinks(False)
        splitter.addWidget(self.details)
        splitter.setSizes([320, 180])
        layout.addWidget(splitter, 1)

    def set_update_notice(self, changed: bool, summary: str):
        """Show / hide the 'installation changed since last snapshot' banner."""
        if changed:
            self.update_banner_label.setText(
                f"⚠️ <b>The installation changed since the last snapshot</b> (update?): {html_escape(summary)}"
            )
            self.update_banner.show()
        else:
            self.update_banner.hide()

    # --- check ---------------------------------------------------------------

    def showEvent(self, event):
        super().showEvent(event)
        if not self._checked_once:
            self._checked_once = True
            self.run_check()

    def run_check(self):
        paths = self._paths_provider()
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            report = run_health_check(paths)
        except Exception as exc:
            logger.exception("WinKFP health check failed")
            self.summary_label.setText(f"<span style='color:#b00020;'>Check failed: {html_escape(str(exc))}</span>")
            return
        finally:
            QApplication.restoreOverrideCursor()
        self._report = report
        self._populate(report)

    def _populate(self, report: HealthReport):
        self.tree.blockSignals(True)
        self.tree.clear()
        for issue in report.issues:
            icon, _, color = SEVERITY_STYLE.get(issue.severity, ("", "", "#000"))
            item = QTreeWidgetItem([f"{icon}  {issue.title}", issue.category, "available" if issue.fix else ""])
            item.setData(0, ISSUE_ROLE, issue)
            item.setForeground(0, QColor(color))
            if issue.fix is not None:
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(2, Qt.CheckState.Checked)
            self.tree.addTopLevelItem(item)
        self.tree.blockSignals(False)

        errors = report.count(SEVERITY_ERROR)
        warnings = report.count(SEVERITY_WARNING)
        fixable = len(report.fixable)
        if errors == 0 and warnings == 0:
            text = "<span style='color:#2a8f2a;'><b>No problems found.</b></span>"
        else:
            error_color = "#b00020" if errors else "#2a8f2a"
            warning_color = "#b36b00" if warnings else "#2a8f2a"
            text = (
                f"<b><span style='color:{error_color};'>{errors} error(s)</span>, "
                f"<span style='color:{warning_color};'>{warnings} warning(s)</span></b>"
            )
            if fixable:
                text += f" — {fixable} can be fixed automatically"
        text += f" <span style='color:#888;'>(checked {report.checked_at:%H:%M:%S})</span>"
        self.summary_label.setText(text)
        if self.tree.topLevelItemCount():
            self.tree.setCurrentItem(self.tree.topLevelItem(0))
        else:
            self.details.clear()
        self._update_fix_button()

    def _show_details(self, current: QTreeWidgetItem | None, _previous=None):
        if current is None:
            self.details.clear()
            return
        issue: Issue = current.data(0, ISSUE_ROLE)
        _, label, color = SEVERITY_STYLE.get(issue.severity, ("", "", "#000"))
        html = [
            f"<h3 style='color:{color};'>{html_escape(issue.title)}</h3>",
            f"<p><b>{label}</b> · {html_escape(issue.category)}"
            + (f" · family {html_escape(issue.family)}" if issue.family else "")
            + "</p>",
            "<p>" + html_escape(issue.details).replace("\n", "<br>") + "</p>",
        ]
        if issue.fix is not None:
            html.append("<p><b>Automatic fix:</b></p><pre>" + html_escape(issue.fix.preview()) + "</pre>")
        self.details.setHtml("".join(html))

    # --- fixes -----------------------------------------------------------------

    def _checked_issues(self) -> list[Issue]:
        issues: list[Issue] = []
        for idx in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(idx)
            issue: Issue = item.data(0, ISSUE_ROLE)
            if issue.fix is not None and item.checkState(2) == Qt.CheckState.Checked:
                issues.append(issue)
        return issues

    def _update_fix_button(self):
        count = len(self._checked_issues())
        self.fix_btn.setEnabled(count > 0)
        self.fix_btn.setText(f"🛠 Fix selected ({count})" if count else "🛠 Fix selected")

    def _fix_selected(self):
        issues = self._checked_issues()
        if not issues:
            return
        paths = self._paths_provider()

        if is_winkfp_running():
            QMessageBox.warning(
                self, "WinKFP is running",
                "Close WinKFP before applying fixes — it reads these files only at start-up.",
            )
            return

        preview = "\n\n".join(issue.fix.preview() for issue in issues)
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle("Apply fixes")
        box.setText(f"Apply {len(issues)} fix(es) to the WinKFP installation?")
        box.setInformativeText(
            f"Every changed file is backed up first to:\n{get_backup_root()}\n\n"
            "You can undo the changes with “Restore backup…”."
        )
        box.setDetailedText(preview)
        box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel)
        box.setDefaultButton(QMessageBox.StandardButton.Cancel)
        if box.exec() != QMessageBox.StandardButton.Yes:
            return

        try:
            record = apply_fixes([issue.fix for issue in issues], paths)
        except Exception as exc:
            logger.exception("Applying WinKFP fixes failed")
            QMessageBox.critical(self, "Fix failed", f"No changes were applied.\n\n{exc}")
            self.run_check()
            return

        QMessageBox.information(
            self, "Fixes applied",
            f"{len(issues)} fix(es) applied.\nBackup: {record.path}\n\n"
            "Start WinKFP again so it reloads the changed files.",
        )
        self.run_check()
        self.filesChanged.emit()

    def _restore(self):
        backups = list_backups()
        if not backups:
            QMessageBox.information(self, "Restore backup", "There are no backups made by BimmerDaten yet.")
            return
        dialog = RestoreDialog(backups, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        record = dialog.selected()
        if record is None:
            return
        if is_winkfp_running():
            QMessageBox.warning(self, "WinKFP is running", "Close WinKFP before restoring a backup.")
            return
        answer = QMessageBox.question(
            self, "Restore backup",
            f"Restore the backup from {record.created.replace('T', ' ')}?\n\n{record.description}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            messages = restore_backup(record)
        except Exception as exc:
            logger.exception("Restoring WinKFP backup failed")
            QMessageBox.critical(self, "Restore failed", str(exc))
            return
        QMessageBox.information(self, "Restore backup", "\n".join(messages) or "Nothing to restore.")
        self.run_check()
        self.filesChanged.emit()
