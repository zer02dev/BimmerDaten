"""SA options decoder tab widget."""

from __future__ import annotations

import logging
from pathlib import Path

from PyQt6.QtCore import QCoreApplication, Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QFileDialog,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from database import Database
from sa_parser import list_available_chassis, parse_at_file, parse_fa_trc
from trc_coding import parse_sysdaten
from vin_decoder import read_fa_file
from vin_decoder_tab import VinDecoderTab


logger = logging.getLogger("bimmerdaten.sa_options_widget")


class SATranslationWorker(QThread):
    # Must not be called "finished": that would shadow QThread.finished, which is
    # what tells us the thread has really stopped and can be deleted.
    translated = pyqtSignal(str, str, str, str)  # chassis, sa_code, desc_en, error

    def __init__(self, chassis: str, sa_code: str, desc_de: str, parent=None):
        super().__init__(parent)
        self.chassis = chassis
        self.sa_code = sa_code
        self.desc_de = desc_de

    def run(self):
        try:
            from deep_translator import GoogleTranslator

            translated = GoogleTranslator(source="german", target="english").translate(self.desc_de)
            if translated:
                self.translated.emit(self.chassis, self.sa_code, translated, "")
            else:
                self.translated.emit(self.chassis, self.sa_code, "", "empty result")
        except Exception as exc:
            logger.exception("SA translation worker failed for code %s", self.sa_code)
            if type(exc).__name__ == "TooManyRequests":
                error = "Google limit, try later"
            else:
                error = "no connection"
            self.translated.emit(self.chassis, self.sa_code, "", error)


class SAOptionsWidget(QWidget):
    CATEGORIES = [
        "All",
        "Engine",
        "Transmission",
        "Safety",
        "Comfort",
        "Multimedia",
        "Lighting",
        "Body",
        "Other",
    ]

    CATEGORY_FILTER_MAP = {
        "Engine": "Silnik",
        "Transmission": "Skrzynia",
        "Safety": "Bezpieczeństwo",
        "Comfort": "Komfort",
        "Multimedia": "Multimedia",
        "Lighting": "Oświetlenie",
        "Body": "Nadwozie",
        "Other": "Inne",
    }

    def __init__(self, db: Database | None, config: dict | None = None, parent=None):
        super().__init__(parent)
        self.db = db
        self.config = config or {}
        self.daten_folder = str(self.config.get("daten") or r"C:\NCSEXPER\DATEN")
        self.work_folder = str(self.config.get("work") or r"C:\NCSEXPER\WORK")

        self._vehicle_sa_codes: list[str] = []
        self._workers: list[SATranslationWorker] = []
        self._translation_pending: set[tuple[str, str]] = set()
        self._current_options: list[dict] = []
        self._auto_load_attempted = False

        app = QCoreApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self._wait_for_workers)

        self._setup_ui()
        self._load_models()
        self._populate_table()

    def showEvent(self, event):
        super().showEvent(event)
        if self._auto_load_attempted:
            return
        self._auto_load_attempted = True
        self._auto_load_fa_trc()

    def _setup_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.sub_tabs = QTabWidget()
        outer.addWidget(self.sub_tabs)

        sa_page = QWidget()
        root = QVBoxLayout(sa_page)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        top = QHBoxLayout()
        top.setSpacing(6)

        top.addWidget(QLabel("Model:"))
        self.model_combo = QComboBox()
        self.model_combo.currentIndexChanged.connect(self._populate_table)
        top.addWidget(self.model_combo)

        self.vin_label = QLabel("VIN: —")
        top.addWidget(self.vin_label, 1)

        self.fa_trc_status_label = QLabel("No fa.trc file")
        self.fa_trc_status_label.setStyleSheet("color: #4a4a4a;")
        top.addWidget(self.fa_trc_status_label)

        self.load_btn = QPushButton("Load any file (FA)")
        self.load_btn.setMinimumWidth(150)
        self.load_btn.setToolTip("Manually select fa.trc file")
        self.load_btn.clicked.connect(self._load_fa_trc)
        top.addWidget(self.load_btn)

        self.only_vehicle_btn = QPushButton("Show only your car codes")
        self.only_vehicle_btn.setCheckable(True)
        self.only_vehicle_btn.setEnabled(False)
        self.only_vehicle_btn.toggled.connect(self._populate_table)
        top.addWidget(self.only_vehicle_btn)

        top.addWidget(QLabel("Category:"))
        self.category_combo = QComboBox()
        self.category_combo.addItems(self.CATEGORIES)
        self.category_combo.currentIndexChanged.connect(self._populate_table)
        top.addWidget(self.category_combo)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("🔍 Search SA or description...")
        self.search_edit.textChanged.connect(self._populate_table)
        top.addWidget(self.search_edit, 1)

        root.addLayout(top)

        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels([
            "SA",
            "ASW name",
            "Description DE",
            "Description EN",
            "Coding",
        ])
        self.table.setColumnWidth(0, 60)
        self.table.setColumnWidth(1, 120)
        self.table.setColumnWidth(2, 250)
        self.table.setColumnWidth(3, 250)
        self.table.setColumnWidth(4, 80)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setWordWrap(True)
        self.table.cellDoubleClicked.connect(self._on_table_double_clicked)
        root.addWidget(self.table, 1)

        self.status_label = QLabel("Total: 0 options")
        root.addWidget(self.status_label)

        self.sub_tabs.addTab(sa_page, "📋 SA codes")
        self.vin_tab = VinDecoderTab(self.daten_folder, self._sa_names_for)
        self.vin_tab.showSaCodesRequested.connect(self._show_vehicle_sa_codes)
        self.sub_tabs.addTab(self.vin_tab, "🔎 VIN decoder")

    def _sa_names_for(self, chassis: str) -> dict[str, str]:
        """SA code -> description (English if already translated, else German)."""
        names: dict[str, str] = {}
        for opt in parse_at_file(chassis, self.daten_folder):
            code = str(opt.get("sa_code") or "").strip().upper()
            if not code:
                continue
            text = ""
            if self.db:
                text = self.db.get_sa_translation(chassis, code, "en") or ""
            names[code] = text or str(opt.get("desc_de") or "")
        return names

    def _show_vehicle_sa_codes(self):
        self.sub_tabs.setCurrentIndex(0)
        if self.only_vehicle_btn.isEnabled():
            self.only_vehicle_btn.setChecked(True)

    def _load_models(self):
        self.model_combo.blockSignals(True)
        self.model_combo.clear()

        models = list_available_chassis(self.daten_folder)
        for model in models:
            self.model_combo.addItem(model)

        self.model_combo.blockSignals(False)

    def _auto_load_fa_trc(self):
        """Try to automatically load fa.trc from default work folder."""
        default_path = Path(self.work_folder) / "fa.trc"
        if default_path.exists():
            try:
                self._load_fa_trc_from_path(str(default_path))
                return
            except Exception as e:
                # Silently fail if auto-load fails, user can manually select
                pass
        
        # File not found: set status label and ask user if they want to manually select
        self.fa_trc_status_label.setText("No fa.trc file")
        self.fa_trc_status_label.setStyleSheet("color: #4a4a4a;")
        reply = QMessageBox.question(
            self,
            "Load fa.trc",
            f"No fa.trc found in default location:\n{default_path}\n\n"
            "Would you like to manually select the fa.trc file?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._load_fa_trc()

    def _load_fa_trc_from_path(self, path: str):
        """Load fa.trc from specified path."""
        self._vehicle_sa_codes = parse_fa_trc(path)

        has_vehicle_codes = bool(self._vehicle_sa_codes)
        self.only_vehicle_btn.setEnabled(has_vehicle_codes)
        if not has_vehicle_codes:
            self.only_vehicle_btn.setChecked(False)

        work_dir = str(Path(path).parent)
        sysdaten = parse_sysdaten(work_dir)
        vin = str(sysdaten.get("FAHRGESTELL_NR", "") or "").strip() or "—"
        self.vin_label.setText(f"VIN: {vin}")
        self.vin_tab.set_vehicle(vin, read_fa_file(path))

        self.fa_trc_status_label.setText("✅ File fa.trc loaded")
        self.fa_trc_status_label.setStyleSheet("color: #2a8f2a;")

        self._populate_table()

    def _load_fa_trc(self):
        """Open file dialog to manually select fa.trc."""
        start_dir = self.work_folder if Path(self.work_folder).exists() else str(Path.home())
        path = QFileDialog.getOpenFileName(
            self,
            "Load fa.trc",
            start_dir,
            "Trace files (*.trc *.TRC);;All files (*)",
        )[0]
        if not path:
            return

        try:
            self._load_fa_trc_from_path(path)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load fa.trc: {e}")

    def _populate_table(self):
        chassis = (self.model_combo.currentText() or "").strip().upper()
        if not chassis:
            self.table.setRowCount(0)
            self.status_label.setText("Total: 0 options")
            return

        all_options = parse_at_file(chassis, self.daten_folder)

        category = self.category_combo.currentText()
        if category and category != "All":
            parser_category = self.CATEGORY_FILTER_MAP.get(category, category)
            all_options = [o for o in all_options if o.get("category") == parser_category]

        vehicle_codes = set(code.upper() for code in (self._vehicle_sa_codes or []))
        if self.only_vehicle_btn.isChecked() and vehicle_codes:
            all_options = [
                o for o in all_options
                if str(o.get("sa_code") or "").strip().upper() in vehicle_codes
            ]

        query = (self.search_edit.text() or "").strip().lower()
        if query:
            filtered = []
            for opt in all_options:
                if (
                    query in str(opt.get("sa_code", "")).lower()
                    or query in str(opt.get("asw_name", "")).lower()
                    or query in str(opt.get("desc_de", "")).lower()
                    or query in str(opt.get("desc_en", "")).lower()
                ):
                    filtered.append(opt)
            all_options = filtered

        self._current_options = list(all_options)
        self.table.setRowCount(len(all_options))

        for row, opt in enumerate(all_options):
            sa_code = str(opt.get("sa_code") or "").strip().upper()
            asw_name = str(opt.get("asw_name") or "").strip()
            desc_de = str(opt.get("desc_de") or "")

            desc_en = None
            if self.db:
                desc_en = self.db.get_sa_translation(chassis, sa_code, "en")

            self.table.setItem(row, 0, QTableWidgetItem(sa_code))
            self.table.setItem(row, 1, QTableWidgetItem(asw_name or "—"))
            self.table.setItem(row, 2, QTableWidgetItem(desc_de))
            self.table.setItem(row, 3, QTableWidgetItem(desc_en or "(double-click to translate)"))

            coding_item = QTableWidgetItem("✅" if bool(opt.get("codierrelevant")) else "❌")
            coding_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 4, coding_item)

            has_vehicle_option = sa_code in vehicle_codes
            coding_relevant = bool(opt.get("codierrelevant"))
            if has_vehicle_option:
                color = QColor("#B3D9FF") if coding_relevant else QColor("#CCE4F7")
                for col in range(5):
                    item = self.table.item(row, col)
                    if item:
                        item.setBackground(color)
                        if coding_relevant:
                            font = item.font()
                            font.setBold(True)
                            item.setFont(font)

        total = len(all_options)
        vehicle_count = sum(1 for o in all_options if str(o.get("sa_code") or "").strip().upper() in vehicle_codes)
        coding_count = sum(1 for o in all_options if bool(o.get("codierrelevant")))

        if vehicle_codes:
            self.status_label.setText(
                f"Total: {total} SA options | Your car: {vehicle_count} | Coding relevant: {coding_count}"
            )
        else:
            self.status_label.setText(
                f"Total: {total} SA options | Coding relevant: {coding_count} | Load fa.trc to see the vehicle equipment"
            )

        self.table.resizeRowsToContents()

    def _on_table_double_clicked(self, row: int, column: int):
        # Trigger translation only on explicit user action.
        if column not in (1, 2, 3):
            return
        if row < 0 or row >= len(self._current_options):
            return

        opt = self._current_options[row]
        chassis = (self.model_combo.currentText() or "").strip().upper()
        sa_code = str(opt.get("sa_code") or "").strip().upper()
        desc_de = str(opt.get("desc_de") or "").strip()

        if not chassis or not sa_code or not desc_de:
            return

        if self.db:
            cached = self.db.get_sa_translation(chassis, sa_code, "en")
            if cached:
                self._set_en_text(row, cached)
                return

        self._set_en_text(row, "⏳ translating...")
        self._queue_translation(chassis, sa_code, desc_de)

    def _queue_translation(self, chassis: str, sa_code: str, desc_de: str):
        key = (chassis, sa_code)
        if key in self._translation_pending:
            return
        self._translation_pending.add(key)

        worker = SATranslationWorker(chassis, sa_code, desc_de, self)
        worker.translated.connect(self._on_translation_done)
        # QThread.finished fires only after run() has returned, so deleting here is safe.
        worker.finished.connect(lambda w=worker: self._remove_worker(w))
        self._workers.append(worker)
        worker.start()

    def _remove_worker(self, worker: SATranslationWorker):
        try:
            if worker in self._workers:
                self._workers.remove(worker)
            worker.deleteLater()
        except Exception:
            logger.exception("Failed to clean up SA translation worker")

    def _wait_for_workers(self):
        """Give running translations a moment to end before the app exits."""
        for worker in list(self._workers):
            if worker.isRunning() and not worker.wait(5000):
                logger.warning("SA translation for %s still running at exit", worker.sa_code)

    def _set_en_text(self, row: int, text: str, tooltip: str = ""):
        """Change the EN cell text but keep the row's colour and bold font."""
        item = self.table.item(row, 3)
        if item is None:
            item = QTableWidgetItem()
            self.table.setItem(row, 3, item)
        item.setText(text)
        item.setToolTip(tooltip)

    def _on_translation_done(self, chassis: str, sa_code: str, desc_en: str, error: str = ""):
        key = (chassis, sa_code)
        self._translation_pending.discard(key)

        if self.db and desc_en:
            self.db.save_sa_translation(chassis, sa_code, desc_en=desc_en)

        current_chassis = (self.model_combo.currentText() or "").strip().upper()
        if current_chassis != (chassis or "").strip().upper():
            return

        for row in range(self.table.rowCount()):
            sa_item = self.table.item(row, 0)
            if sa_item and (sa_item.text() or "").strip().upper() == sa_code.upper():
                if desc_en:
                    self._set_en_text(row, desc_en)
                else:
                    reason = error or "translation failed"
                    self._set_en_text(
                        row,
                        f"⚠ {reason} (double-click to retry)",
                        f"Translation failed: {reason}.",
                    )
                break
