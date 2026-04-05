"""SA options decoder tab widget."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, QThread, pyqtSignal
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
    QVBoxLayout,
    QWidget,
)

from database import Database
from sa_parser import list_available_chassis, parse_at_file, parse_fa_trc
from trc_coding import parse_sysdaten


class SATranslationWorker(QThread):
    finished = pyqtSignal(str, str, str)  # chassis, sa_code, desc_en

    def __init__(self, chassis: str, sa_code: str, desc_de: str, parent=None):
        super().__init__(parent)
        self.chassis = chassis
        self.sa_code = sa_code
        self.desc_de = desc_de

    def run(self):
        try:
            from deep_translator import GoogleTranslator

            translated = GoogleTranslator(source="german", target="english").translate(self.desc_de)
            self.finished.emit(self.chassis, self.sa_code, translated or "")
        except Exception:
            self.finished.emit(self.chassis, self.sa_code, "")


class SAOptionsWidget(QWidget):
    CATEGORIES = [
        "Wszystkie",
        "Silnik",
        "Skrzynia",
        "Bezpieczeństwo",
        "Komfort",
        "Multimedia",
        "Oświetlenie",
        "Nadwozie",
        "Inne",
    ]

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

        self._setup_ui()
        self._load_models()
        self._populate_table()

    def _setup_ui(self):
        root = QVBoxLayout(self)
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

        self.load_btn = QPushButton("📂 Załaduj fa.trc")
        self.load_btn.clicked.connect(self._load_fa_trc)
        top.addWidget(self.load_btn)

        top.addWidget(QLabel("Kategoria:"))
        self.category_combo = QComboBox()
        self.category_combo.addItems(self.CATEGORIES)
        self.category_combo.currentIndexChanged.connect(self._populate_table)
        top.addWidget(self.category_combo)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("🔍 Szukaj SA lub opisu...")
        self.search_edit.textChanged.connect(self._populate_table)
        top.addWidget(self.search_edit, 1)

        root.addLayout(top)

        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels([
            "SA",
            "Nazwa ASW",
            "Opis DE",
            "Opis EN",
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

        self.status_label = QLabel("Łącznie: 0 opcji")
        root.addWidget(self.status_label)

    def _load_models(self):
        self.model_combo.blockSignals(True)
        self.model_combo.clear()

        models = list_available_chassis(self.daten_folder)
        for model in models:
            self.model_combo.addItem(model)

        self.model_combo.blockSignals(False)

    def _load_fa_trc(self):
        start_dir = self.work_folder if Path(self.work_folder).exists() else str(Path.home())
        path = QFileDialog.getOpenFileName(
            self,
            "Załaduj fa.trc",
            start_dir,
            "Trace files (*.trc *.TRC);;All files (*)",
        )[0]
        if not path:
            return

        self._vehicle_sa_codes = parse_fa_trc(path)

        work_dir = str(Path(path).parent)
        sysdaten = parse_sysdaten(work_dir)
        vin = str(sysdaten.get("FAHRGESTELL_NR", "") or "").strip() or "—"
        self.vin_label.setText(f"VIN: {vin}")

        self._populate_table()

    def _populate_table(self):
        chassis = (self.model_combo.currentText() or "").strip().upper()
        if not chassis:
            self.table.setRowCount(0)
            self.status_label.setText("Łącznie: 0 opcji")
            return

        all_options = parse_at_file(chassis, self.daten_folder)

        category = self.category_combo.currentText()
        if category and category != "Wszystkie":
            all_options = [o for o in all_options if o.get("category") == category]

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

        vehicle_codes = set(code.upper() for code in (self._vehicle_sa_codes or []))

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
            self.table.setItem(row, 3, QTableWidgetItem(desc_en or "(dwuklik, aby tłumaczyć)"))

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
                f"Łącznie: {total} opcji SA | Twoje auto: {vehicle_count} | Codierrelevant: {coding_count}"
            )
        else:
            self.status_label.setText(
                f"Łącznie: {total} opcji SA | Codierrelevant: {coding_count} | Załaduj fa.trc aby zobaczyć wyposażenie auta"
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
                self.table.setItem(row, 3, QTableWidgetItem(cached))
                return

        self.table.setItem(row, 3, QTableWidgetItem("⏳ tłumaczenie..."))
        self._queue_translation(chassis, sa_code, desc_de)

    def _queue_translation(self, chassis: str, sa_code: str, desc_de: str):
        key = (chassis, sa_code)
        if key in self._translation_pending:
            return
        self._translation_pending.add(key)

        worker = SATranslationWorker(chassis, sa_code, desc_de, self)
        worker.finished.connect(self._on_translation_done)
        worker.finished.connect(lambda _c, _s, _d, w=worker: self._remove_worker(w))
        self._workers.append(worker)
        worker.start()

    def _remove_worker(self, worker: SATranslationWorker):
        try:
            if worker in self._workers:
                self._workers.remove(worker)
            worker.deleteLater()
        except Exception:
            pass

    def _on_translation_done(self, chassis: str, sa_code: str, desc_en: str):
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
                self.table.setItem(row, 3, QTableWidgetItem(desc_en or ""))
                break
