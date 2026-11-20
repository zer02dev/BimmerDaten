"""
winkfp_presets_tab.py
"Presets" sub-tab: named WinKFP Expert-mode configurations, loaded into WINKFPT.INI.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from html import escape as html_escape

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
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

from winkfp_health import apply_fixes, get_backup_root, is_winkfp_running
from winkfp_parser import WinkfpPaths, list_files_ci
from winkfp_presets import (
    EXPERT_KEYS,
    ExpertPreset,
    hw_interfaces,
    load_presets,
    plan_load,
    read_current_expert_config,
    save_presets,
)
from winkfp_widgets import COLOR_ERROR, COLOR_MUTED, COLOR_OK, COLOR_WARNING, LoadingOverlay, Worker, html_page, style_table

logger = logging.getLogger("bimmerdaten.winkfp_presets_tab")

COLUMNS = ["Name", "Family", "ZB", "PABD", "Program file", "Data file"]
UNITS = ["", "_", "A", "B", "C", "D"]


class PresetsTab(QWidget):
    filesChanged = pyqtSignal()

    def __init__(self, paths_provider: Callable[[], WinkfpPaths], parent=None):
        super().__init__(parent)
        self._paths_provider = paths_provider
        self._presets: list[ExpertPreset] = []
        self._current: ExpertPreset | None = None
        self._worker: Worker | None = None
        self._loaded = False
        self._build_ui()
        self._overlay = LoadingOverlay(self)

    # --- UI ------------------------------------------------------------------

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        intro = QLabel(
            "WinKFP remembers <b>one</b> Expert-mode configuration in WINKFPT.INI and offers it when you enter "
            "Expert mode. Keep any number of presets here and load the one you need — the flash files are copied "
            "to DATA\\DEVELOP, because Expert mode only lists files from that folder."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        self.table = QTableWidget(0, len(COLUMNS))
        style_table(self.table)
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.currentCellChanged.connect(lambda row, *_: self._select(row))
        left_layout.addWidget(self.table, 1)
        buttons = QHBoxLayout()
        self.new_btn = QPushButton("➕ New")
        self.new_btn.clicked.connect(self._new_preset)
        self.from_winkfp_btn = QPushButton("📥 From current WinKFP config")
        self.from_winkfp_btn.clicked.connect(self._from_current)
        self.delete_btn = QPushButton("🗑 Delete")
        self.delete_btn.clicked.connect(self._delete_preset)
        for button in (self.new_btn, self.from_winkfp_btn, self.delete_btn):
            buttons.addWidget(button)
        buttons.addStretch()
        left_layout.addLayout(buttons)

        self.info_tabs = QTabWidget()
        self.check_view = QTextBrowser()
        self.info_tabs.addTab(self.check_view, "✔ Check before loading")
        self.current_view = QTextBrowser()
        self.info_tabs.addTab(self.current_view, "📄 Current WinKFP config")
        left_layout.addWidget(self.info_tabs, 1)
        splitter.addWidget(left)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        editor = QGroupBox("Preset")
        form = QFormLayout(editor)
        self.name_edit = QLineEdit()
        self.family_edit = QLineEdit()
        self.zb_edit = QLineEdit()
        self.pabd_combo = QComboBox()
        self.pabd_combo.setEditable(True)
        self.psgbd_edit = QLineEdit()
        self.address_edit = QLineEdit()
        self.address_edit.setMaxLength(2)
        self.address_edit.setPlaceholderText("hex, e.g. 12")
        self.program_edit = QLineEdit()
        self.data_edit = QLineEdit()
        self.naab_edit = QLineEdit()
        self.interface_combo = QComboBox()
        self.unit_combo = QComboBox()
        self.unit_combo.addItems(UNITS)
        self.protocol_edit = QLineEdit()
        self.protocol_edit.setPlaceholderText("empty = WinKFP default (e.g. KWP2000*, BMW-FAST)")
        self.notes_edit = QPlainTextEdit()
        self.notes_edit.setMaximumHeight(60)
        for label, widget in (
            ("Name", self.name_edit), ("Family", self.family_edit), ("ZB number", self.zb_edit),
            ("PABD", self.pabd_combo), ("P-SGBD", self.psgbd_edit), ("ECU address", self.address_edit),
            ("Program file (0PA)", self.program_edit), ("Data file (0DA)", self.data_edit),
            ("NAAB file (0BA)", self.naab_edit), ("HW interface", self.interface_combo),
            ("Interface unit", self.unit_combo), ("Diagnosis protocol", self.protocol_edit),
            ("Notes", self.notes_edit),
        ):
            form.addRow(f"{label}:", widget)
        right_layout.addWidget(editor)

        actions = QHBoxLayout()
        self.save_btn = QPushButton("💾 Save preset")
        self.save_btn.clicked.connect(self._save_current)
        self.load_btn = QPushButton("⬇ Load into WinKFP")
        self.load_btn.clicked.connect(self._load_into_winkfp)
        actions.addWidget(self.save_btn)
        actions.addStretch()
        actions.addWidget(self.load_btn)
        right_layout.addLayout(actions)
        right_layout.addStretch(1)
        splitter.addWidget(right)
        splitter.setSizes([620, 620])
        layout.addWidget(splitter, 1)
        self._set_editor_enabled(False)

    # --- loading -------------------------------------------------------------

    def showEvent(self, event):
        super().showEvent(event)
        if not self._loaded:
            self._loaded = True
            self.reload()

    def reload(self, select_name: str = ""):
        paths = self._paths_provider()
        self._presets = load_presets()
        self._fill_interfaces(paths)
        self._fill_pabds(paths)
        self._fill_table(select_name)
        self._show_current_config()

    def _fill_interfaces(self, paths: WinkfpPaths):
        current = self.interface_combo.currentData()
        self.interface_combo.clear()
        self.interface_combo.addItem("(WinKFP default)", "")
        try:
            for label, value in hw_interfaces(paths):
                self.interface_combo.addItem(f"{label} — {value}", value)
        except Exception:
            logger.exception("Cannot read HW interfaces")
        if current:
            idx = self.interface_combo.findData(current)
            if idx >= 0:
                self.interface_combo.setCurrentIndex(idx)

    def _fill_pabds(self, paths: WinkfpPaths):
        text = self.pabd_combo.currentText()
        self.pabd_combo.clear()
        self.pabd_combo.addItem("")
        names = sorted(name for name in list_files_ci(paths.sgdat_dir) if name.endswith(".ipo") and not name.startswith("a_"))
        self.pabd_combo.addItems(names)
        self.pabd_combo.setCurrentText(text)

    def _fill_table(self, select_name: str = ""):
        self.table.setRowCount(len(self._presets))
        select_row = -1
        for row, preset in enumerate(self._presets):
            for col, value in enumerate((preset.name, preset.family, preset.zb_nr, preset.pabd,
                                         preset.program_file, preset.data_file)):
                self.table.setItem(row, col, QTableWidgetItem(value))
            if preset.name == select_name:
                select_row = row
        self.table.resizeColumnsToContents()
        if select_row >= 0:
            self.table.setCurrentCell(select_row, 0)
            self._select(select_row)
        elif not self._presets:
            self._current = None
            self._set_editor_enabled(False)
            self.check_view.setHtml(html_page(
                f"<p style='color:{COLOR_MUTED};'>No presets yet. Click <b>➕ New</b>, take over the current WinKFP "
                "configuration, or use <b>💾 Save as preset</b> in the 🔎 What to flash tab.</p>"
            ))

    def _show_current_config(self):
        try:
            config = read_current_expert_config(self._paths_provider())
        except Exception:
            config = {}
        if not any(config.get(k) for k in EXPERT_KEYS):
            self.current_view.setHtml(html_page(f"<p style='color:{COLOR_MUTED};'>Empty — no Expert configuration saved.</p>"))
            return
        rows = "".join(
            f"<tr><td><b>{html_escape(k)}</b>&nbsp;</td><td>{html_escape(config.get(k, ''))}</td></tr>" for k in EXPERT_KEYS
        )
        self.current_view.setHtml(html_page(f"<table cellspacing='0' cellpadding='1'>{rows}</table>"))

    # --- editor ----------------------------------------------------------------

    def _set_editor_enabled(self, enabled: bool):
        for widget in (self.name_edit, self.family_edit, self.zb_edit, self.pabd_combo, self.psgbd_edit,
                       self.address_edit, self.program_edit, self.data_edit, self.naab_edit,
                       self.interface_combo, self.unit_combo, self.protocol_edit, self.notes_edit,
                       self.save_btn, self.load_btn, self.delete_btn):
            widget.setEnabled(enabled)

    def _select(self, row: int):
        if row < 0 or row >= len(self._presets):
            return
        preset = self._presets[row]
        self._current = preset
        self._set_editor_enabled(True)
        self.name_edit.setText(preset.name)
        self.family_edit.setText(preset.family)
        self.zb_edit.setText(preset.zb_nr)
        self.pabd_combo.setCurrentText(preset.pabd)
        self.psgbd_edit.setText(preset.psgbd)
        self.address_edit.setText(preset.address)
        self.program_edit.setText(preset.program_file)
        self.data_edit.setText(preset.data_file)
        self.naab_edit.setText(preset.naab_file)
        idx = self.interface_combo.findData(preset.hw_interface)
        if idx < 0 and preset.hw_interface:
            self.interface_combo.addItem(preset.hw_interface, preset.hw_interface)
            idx = self.interface_combo.count() - 1
        self.interface_combo.setCurrentIndex(max(idx, 0))
        self.unit_combo.setCurrentText(preset.hw_unit)
        self.protocol_edit.setText(preset.diag_protocol)
        self.notes_edit.setPlainText(preset.notes)
        self._show_check(preset)

    def _editor_preset(self) -> ExpertPreset:
        base = self._current or ExpertPreset(name="")
        return ExpertPreset(
            name=self.name_edit.text().strip(),
            family=self.family_edit.text().strip().upper(),
            zb_nr=self.zb_edit.text().strip(),
            pabd=self.pabd_combo.currentText().strip(),
            psgbd=self.psgbd_edit.text().strip(),
            address=self.address_edit.text().strip().upper(),
            program_file=self.program_edit.text().strip(),
            data_file=self.data_edit.text().strip(),
            naab_file=self.naab_edit.text().strip(),
            hw_interface=self.interface_combo.currentData() or "",
            hw_unit=self.unit_combo.currentText(),
            diag_protocol=self.protocol_edit.text().strip(),
            notes=self.notes_edit.toPlainText().strip(),
            created=base.created,
        )

    def _show_check(self, preset: ExpertPreset):
        try:
            plan = plan_load(preset, self._paths_provider())
        except Exception as exc:
            self.check_view.setHtml(html_page(f"<p style='color:{COLOR_ERROR};'>Check failed: {html_escape(str(exc))}</p>"))
            return
        html = ["<h4>Check before loading</h4>"]
        if plan.errors:
            html.extend(f"<p style='color:{COLOR_ERROR};'>❌ {html_escape(e)}</p>" for e in plan.errors)
        else:
            html.append(f"<p style='color:{COLOR_OK};'>✅ Ready to load into WinKFP.</p>")
        html.extend(f"<p style='color:{COLOR_WARNING};'>ℹ️ {html_escape(m)}</p>" for m in plan.messages)
        html.append("<p><b>Changes when loading:</b></p><pre>" + html_escape("\n\n".join(f.preview() for f in plan.fixes)) + "</pre>")
        self.check_view.setHtml(html_page("".join(html)))

    # --- actions -----------------------------------------------------------------

    def add_preset(self, preset: ExpertPreset) -> None:
        """Add a preset coming from another tab (e.g. the What-to-flash assistant)."""
        self._presets = load_presets()
        name = preset.name
        existing = {p.name for p in self._presets}
        counter = 2
        while preset.name in existing:
            preset.name = f"{name} ({counter})"
            counter += 1
        self._presets.append(preset)
        save_presets(self._presets)
        self._loaded = True
        self.reload(select_name=preset.name)

    def _new_preset(self):
        name, ok = QInputDialog.getText(self, "New preset", "Preset name:")
        if ok and name.strip():
            self.add_preset(ExpertPreset(name=name.strip()))

    def _from_current(self):
        config = read_current_expert_config(self._paths_provider())
        if not any(config.get(k) for k in EXPERT_KEYS):
            QMessageBox.information(self, "Presets", "WINKFPT.INI has no Expert configuration saved.")
            return
        name, ok = QInputDialog.getText(self, "New preset", "Name for the current WinKFP configuration:")
        if ok and name.strip():
            self.add_preset(ExpertPreset.from_ini_values(name.strip(), config))

    def _save_current(self):
        if self._current is None:
            return
        preset = self._editor_preset()
        if not preset.name:
            QMessageBox.warning(self, "Presets", "The preset needs a name.")
            return
        others = [p for p in self._presets if p is not self._current]
        if any(p.name == preset.name for p in others):
            QMessageBox.warning(self, "Presets", f"A preset named '{preset.name}' already exists.")
            return
        index = self._presets.index(self._current)
        self._presets[index] = preset
        save_presets(self._presets)
        self.reload(select_name=preset.name)

    def _delete_preset(self):
        if self._current is None:
            return
        answer = QMessageBox.question(self, "Delete preset", f"Delete preset '{self._current.name}'?")
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._presets = [p for p in self._presets if p is not self._current]
        save_presets(self._presets)
        self._current = None
        self.reload()

    def _load_into_winkfp(self):
        if self._current is None:
            return
        preset = self._editor_preset()
        paths = self._paths_provider()
        plan = plan_load(preset, paths)
        if plan.errors:
            QMessageBox.warning(self, "Load into WinKFP", "The preset cannot be loaded:\n\n" + "\n".join(plan.errors))
            self._show_check(preset)
            return
        if is_winkfp_running():
            QMessageBox.warning(
                self, "WinKFP is running",
                "Close WinKFP first — it writes WINKFPT.INI when it exits and would overwrite the preset.",
            )
            return
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle("Load into WinKFP")
        box.setText(f"Load preset '{preset.name}' into WinKFP?")
        box.setInformativeText(
            "WINKFPT.INI is changed and the flash files are copied to DATA\\DEVELOP. "
            f"Everything is backed up in {get_backup_root()} and can be undone in 🩺 Health → Restore backup…"
        )
        box.setDetailedText("\n\n".join(f.preview() for f in plan.fixes))
        box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel)
        box.setDefaultButton(QMessageBox.StandardButton.Cancel)
        if box.exec() != QMessageBox.StandardButton.Yes:
            return

        self.load_btn.setEnabled(False)
        self._overlay.start(f"Loading preset '{preset.name}' into WinKFP…")
        worker = Worker(lambda: apply_fixes(plan.fixes, paths), self)
        worker.finishedWithResult.connect(lambda record: self._on_loaded(preset))
        worker.failed.connect(lambda msg: QMessageBox.critical(self, "Load failed", f"No changes were applied.\n\n{msg}"))
        worker.finished.connect(self._overlay.stop)
        worker.finished.connect(lambda: self.load_btn.setEnabled(True))
        self._worker = worker
        worker.start()

    def _on_loaded(self, preset: ExpertPreset):
        self._show_current_config()
        self._show_check(preset)
        QMessageBox.information(
            self, "Load into WinKFP",
            f"Preset '{preset.name}' is loaded.\n\nStart WinKFP, click 'Expert mode' and confirm the suggested "
            "configuration. Then use the program / data buttons and start programming.",
        )
        self.filesChanged.emit()
