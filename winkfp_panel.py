"""
winkfp_panel.py
WinKFP tab: helper for the BMW WinKFP flash tool.
"""
from __future__ import annotations

import logging
from html import escape as html_escape
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from winkfp_health_tab import HealthTab
from winkfp_sgdat_tab import SgdatTab
from winkfp_updates_tab import UpdatesTab
from winkfp_parser import (
    InstallSummary,
    WinkfpPaths,
    build_install_summary,
    load_paths,
    save_paths,
)

logger = logging.getLogger("bimmerdaten.winkfp_panel")

SGDAT_TAB_TITLE = "🗂 SGDAT"

# Sub-tabs planned for the next stages: (title, stage, description).
PLANNED_TABS = [
    ("🩺 Health", "E1", "Installation check with fixes and backup."),
    ("📦 Families", "E5", "ECU families with completeness status, integration positions, ZB table, restore from backups."),
    ("🔎 What to flash", "E6", "Assistant: HW number / ZB → family → ZB history → HW compatibility → files for Expert mode."),
    (SGDAT_TAB_TITLE, "E3", "All *.ipo files classified as flash (PABD) or coding (CABD), with job list and author."),
    ("🧾 Logs", "E4", "WinKFP error logs with explained error codes, IDENT / AIF / REF results."),
    ("💾 Presets", "E7", "Named Expert-mode presets loaded into WINKFPT.INI."),
]


class WinkfpPanel(QWidget):
    """Top-level WinKFP tab."""

    openPrgRequested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._paths = load_paths()
        self._summary: InstallSummary | None = None
        self._pending_changes = False
        self._build_ui()
        self.refresh()

    def showEvent(self, event):
        super().showEvent(event)
        self.updates_tab.auto_check()

    def _on_changes_detected(self, changed: bool, summary: str):
        self._pending_changes = changed
        self.health_tab.set_update_notice(changed, summary)

    def _on_files_changed_by_fix(self):
        self.refresh()
        # Changes made by BimmerDaten itself should not be reported as an update later.
        if not self._pending_changes:
            self.updates_tab.save_baseline("after BimmerDaten fix")

    # --- UI -----------------------------------------------------------------

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Sub-tabs fill the whole window, like the Diagnosis tab.
        self.sub_tabs = QTabWidget()
        layout.addWidget(self.sub_tabs)

        self.health_tab = HealthTab(self._current_paths)
        self.health_tab.filesChanged.connect(self._on_files_changed_by_fix)
        self.sub_tabs.addTab(self.health_tab, PLANNED_TABS[0][0])

        self.updates_tab = UpdatesTab(self._current_paths)
        self.updates_tab.changesDetected.connect(self._on_changes_detected)
        self.health_tab.showUpdatesRequested.connect(
            lambda: self.sub_tabs.setCurrentWidget(self.updates_tab)
        )
        self.sub_tabs.addTab(self.updates_tab, "🔄 Updates")

        self.sgdat_tab = SgdatTab(self._current_paths)
        self.sgdat_tab.openPrgRequested.connect(self.openPrgRequested.emit)

        for title, stage, description in PLANNED_TABS[1:]:
            if title == SGDAT_TAB_TITLE:
                self.sub_tabs.addTab(self.sgdat_tab, title)
                continue
            page = QWidget()
            page_layout = QVBoxLayout(page)
            text = QLabel(
                f"<b>{html_escape(title)}</b><br><br>{html_escape(description)}"
                f"<br><br><i>Planned in stage {stage}.</i>"
            )
            text.setAlignment(Qt.AlignmentFlag.AlignCenter)
            text.setWordWrap(True)
            text.setStyleSheet("color: #666;")
            page_layout.addWidget(text)
            self.sub_tabs.addTab(page, title)

        # Installation tab: paths + overview.
        install_page = QWidget()
        install_layout = QVBoxLayout(install_page)
        install_layout.setContentsMargins(8, 8, 8, 8)
        install_layout.setSpacing(8)
        self.sub_tabs.addTab(install_page, "⚙️ Installation")

        paths_box = QGroupBox("Paths")
        paths_form = QFormLayout(paths_box)
        self.nfs_edit = self._path_row(paths_form, "WinKFP (NFS) folder", str(self._paths.nfs_root))
        self.ecu_edit = self._path_row(paths_form, "EDIABAS Ecu folder", str(self._paths.ecu_dir))

        buttons = QHBoxLayout()
        buttons.addStretch()
        self.save_btn = QPushButton("💾 Save paths")
        self.save_btn.clicked.connect(self._save_paths)
        self.refresh_btn = QPushButton("🔄 Refresh")
        self.refresh_btn.clicked.connect(self.refresh)
        buttons.addWidget(self.save_btn)
        buttons.addWidget(self.refresh_btn)
        paths_form.addRow(buttons)
        install_layout.addWidget(paths_box)

        summary_box = QGroupBox("Installation overview")
        summary_form = QFormLayout(summary_box)
        summary_form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        self._summary_labels: dict[str, QLabel] = {}
        for key, title in (
            ("status", "Status"),
            ("version", "Version (NFS / WinKFP / KMM)"),
            ("settings", "Language / CABD format"),
            ("kfconf", "KFCONF entries"),
            ("info", "INFO file"),
            ("families", "ECU families in DATA"),
            ("sgdat", "SGDAT *.ipo files"),
            ("ecu", "EDIABAS *.prg files"),
            ("backups", "Backup folders"),
        ):
            label = QLabel("-")
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            label.setWordWrap(True)
            self._summary_labels[key] = label
            summary_form.addRow(f"{title}:", label)
        install_layout.addWidget(summary_box)
        install_layout.addStretch(1)

    def _path_row(self, form: QFormLayout, label: str, value: str) -> QLineEdit:
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(4)
        edit = QLineEdit(value)
        browse = QPushButton("…")
        browse.setFixedWidth(32)
        browse.clicked.connect(lambda: self._browse(edit))
        row_layout.addWidget(edit, 1)
        row_layout.addWidget(browse)
        form.addRow(f"{label}:", row)
        return edit

    def _browse(self, edit: QLineEdit):
        folder = QFileDialog.getExistingDirectory(self, "Select folder", edit.text())
        if folder:
            edit.setText(str(Path(folder)))

    # --- Actions ------------------------------------------------------------

    def _current_paths(self) -> WinkfpPaths:
        return WinkfpPaths(
            nfs_root=Path(self.nfs_edit.text().strip()),
            ecu_dir=Path(self.ecu_edit.text().strip()),
        )

    def _save_paths(self):
        paths = self._current_paths()
        try:
            save_paths(paths)
        except Exception as exc:
            logger.exception("Failed to save WinKFP paths")
            QMessageBox.warning(self, "WinKFP", f"Failed to save paths:\n{exc}")
            return
        self._paths = paths
        self.refresh()
        self.health_tab.run_check()

    def refresh(self):
        self._paths = self._current_paths()
        labels = self._summary_labels
        if not self._paths.is_valid():
            for label in labels.values():
                label.setText("-")
            labels["status"].setText(
                f"<span style='color:#b00020;'>WinKFP not found in {self._paths.nfs_root}</span>"
            )
            self._summary = None
            return

        try:
            summary = build_install_summary(self._paths)
        except Exception as exc:
            logger.exception("Failed to read WinKFP installation")
            labels["status"].setText(f"<span style='color:#b00020;'>Read error: {exc}</span>")
            return
        self._summary = summary
        info = summary.info

        labels["status"].setText("<span style='color:#2a8f2a;'>WinKFP installation found</span>")
        labels["version"].setText(
            " / ".join(v or "?" for v in (info.nfs_version, info.winkfp_version, info.kmm_version))
            if info.version_line else "unknown"
        )
        labels["settings"].setText(f"{info.language or '?'} / {info.cabd_format or '?'}")
        labels["kfconf"].setText(str(summary.kfconf_entries))
        expected_info = f"INFO.{(info.language or 'ger').upper()}"
        if summary.info_file:
            labels["info"].setText(f"{summary.info_file} ({summary.info_entries} entries)")
        else:
            labels["info"].setText(
                f"<span style='color:#b00020;'>{expected_info} missing — Comfort mode cannot list "
                f"integration positions (COAPI error 1020)</span>"
            )
        labels["families"].setText(str(summary.families))
        labels["sgdat"].setText(str(summary.ipo_files))
        labels["ecu"].setText(f"{summary.prg_files} ({self._paths.ecu_dir})")
        if summary.backups:
            labels["backups"].setText(", ".join(b.path.name for b in summary.backups))
        else:
            labels["backups"].setText("none")
