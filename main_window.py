"""
main_window.py
Główne okno aplikacji BimmerDaten w PyQt6.
Styl: Windows 98/2000 — pasuje do epoki EDIABAS 😄
"""

import sys
import platform
from pathlib import Path
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QSplitter,
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QListWidget, QListWidgetItem, QTreeWidget,
    QTreeWidgetItem, QFileDialog, QStatusBar, QMenuBar,
    QMenu, QGroupBox, QTextEdit, QComboBox, QFrame,
    QSizePolicy, QHeaderView, QTabWidget, QTableWidget,
    QTableWidgetItem
)
from PyQt6.QtCore import Qt, QSize, pyqtSignal
from PyQt6.QtGui import QFont, QAction, QColor, QPalette, QIcon

# Import naszego dekodera
try:
    from decoderPrg import parse_prg, PrgFile, Job, Table
    DECODER_AVAILABLE = True
except ImportError:
    DECODER_AVAILABLE = False

# Import bazy tłumaczeń
try:
    from database import Database
    DB_AVAILABLE = True
except ImportError:
    DB_AVAILABLE = False


# ---------------------------------------------------------------------------
# Kategorie jobów — na podstawie prefiksu nazwy

JOB_CATEGORIES = {
    "STATUS":    "📊 Status / Live Data",
    "STEUERN":   "⚙️ Steuern / Aktuatory",
    "FS":        "❌ Fehlerspeicher / Błędy",
    "LESEN":     "📖 Lesen / Odczyt",
    "SCHREIBEN": "✏️ Schreiben / Zapis",
    "START":     "▶️ Start / Systemcheck",
    "ENDE":      "⏹️ Ende / Zakończenie",
    "STOP":      "⏹️ Stop",
    "IDENT":     "🔍 Identyfikacja",
    "ADAP":      "🔄 Adaptacje",
    "VARIANTE":  "🔧 Wariant",
    "RAM":       "💾 RAM",
    "DATA":      "📁 Data",
    "C_":        "📡 C_ / Komunikacja",
    "EWS":       "🔐 EWS / Immobilizer",
    "SEED":      "🔑 Seed/Key",
    "SLP":       "💡 SLP",
    "INFO":      "ℹ️ Info",
}

def get_category(job_name: str) -> str:
    for prefix, label in JOB_CATEGORIES.items():
        if job_name.upper().startswith(prefix):
            return label
    return "🔩 Inne"


TABLE_CATEGORIES = {
    "Błędy": {
        "FEHLERCODES", "FORTTEXTE", "FARTTEXTE", "FARTTEXTEERWEITERT",
        "FUMWELTTEXTE", "FUMWELTMATRIX", "FARTTYP", "FARTTXT_ERW",
        "FDETAILSTRUKTUR",
    },
    "Statusy": {
        "VVTSTATUSBG2_2", "EWSSTART", "EWSEMPFANGSSTATUS", "SLSSTATUS",
        "TEVSTATUS", "STAGEDMTL", "STAGEDMTLFREEZE", "REGEL",
    },
    "Bity": {"BITS", "FASTABITS", "FGRBITS", "READINESSBITS"},
    "Komunikacja": {
        "KONZEPT_TABELLE", "BAUDRATE", "DIAGMODE", "JOBRESULT",
        "JOBRESULTEXTENDED",
    },
}

TABLE_CATEGORY_COLORS = {
    "Błędy": ("#8b0000", "#ffffff"),
    "Statusy": ("#1a5c1a", "#ffffff"),
    "Bity": ("#003580", "#ffffff"),
    "Komunikacja": ("#4b0082", "#ffffff"),
    "Inne": ("#2f4f4f", "#ffffff"),
}

TABLE_COLUMN_PRESETS = {
    "FEHLERCODES": [
        ("CODE", "Kod"),
        ("FEHLERTEXT", "Opis błędu"),
    ],
    "BITS": [
        ("NAME", "Nazwa"),
        ("BYTE", "Bajt"),
        ("MASK", "Maska"),
        ("VALUE", "Wartość"),
    ],
    "FASTABITS": [
        ("NAME", "Nazwa"),
        ("BYTE", "Bajt"),
        ("MASK", "Maska"),
        ("VALUE", "Wartość"),
    ],
    "FGRBITS": [
        ("NAME", "Nazwa"),
        ("BYTE", "Bajt"),
        ("MASK", "Maska"),
        ("VALUE", "Wartość"),
    ],
    "READINESSBITS": [
        ("NAME", "Nazwa"),
        ("BYTE", "Bajt"),
        ("MASK", "Maska"),
        ("VALUE", "Wartość"),
    ],
    "EWSSTART": [
        ("STATI", "Status"),
        ("TEXT", "Opis"),
    ],
    "EWSEMPFANGSSTATUS": [
        ("STATI", "Status"),
        ("TEXT", "Opis"),
    ],
}


def get_table_category(table_name: str) -> str:
    upper_name = table_name.upper()
    for category, names in TABLE_CATEGORIES.items():
        if upper_name in names:
            return category
    return "Inne"


# ---------------------------------------------------------------------------
# Styl Windows 98/2000

WIN98_STYLE = """
QMainWindow {
    background-color: #d4d0c8;
}

QWidget {
    background-color: #d4d0c8;
    font-family: "Tahoma", "MS Sans Serif", sans-serif;
    font-size: 11px;
    color: #000000;
}

QMenuBar {
    background-color: #d4d0c8;
    border-bottom: 1px solid #808080;
}

QMenuBar::item:selected {
    background-color: #000080;
    color: #ffffff;
}

QMenu {
    background-color: #d4d0c8;
    border: 1px solid #808080;
}

QMenu::item:selected {
    background-color: #000080;
    color: #ffffff;
}

QGroupBox {
    border: 2px groove #808080;
    margin-top: 8px;
    padding-top: 4px;
    font-weight: bold;
}

QGroupBox::title {
    subcontrol-origin: margin;
    left: 6px;
    padding: 0 2px;
}

QListWidget {
    background-color: #ffffff;
    border: 2px inset #808080;
    selection-background-color: #000080;
    selection-color: #ffffff;
    font-family: "Courier New", monospace;
    font-size: 11px;
}

QListWidget::item:hover {
    background-color: #c0c0ff;
}

QTreeWidget {
    background-color: #ffffff;
    border: 2px inset #808080;
    selection-background-color: #000080;
    selection-color: #ffffff;
    font-family: "Courier New", monospace;
    font-size: 11px;
}

QTreeWidget::item:hover {
    background-color: #c0c0ff;
}

QTreeWidget::item:selected {
    background-color: #000080;
    color: #ffffff;
}

QTableWidget {
    background-color: #ffffff;
    border: 2px inset #808080;
    selection-background-color: #000080;
    selection-color: #ffffff;
    font-family: "Courier New", monospace;
    font-size: 11px;
}

QTableWidget::item:hover {
    background-color: #c0c0ff;
}

QTableWidget::item:selected {
    background-color: #000080;
    color: #ffffff;
}

QLineEdit {
    background-color: #ffffff;
    border: 2px inset #808080;
    padding: 2px;
    font-family: "Courier New", monospace;
}

QTextEdit {
    background-color: #ffffff;
    border: 2px inset #808080;
    font-family: "Courier New", monospace;
    font-size: 11px;
}

QPushButton {
    background-color: #d4d0c8;
    border-top: 2px solid #ffffff;
    border-left: 2px solid #ffffff;
    border-bottom: 2px solid #808080;
    border-right: 2px solid #808080;
    padding: 3px 10px;
    min-width: 70px;
}

QPushButton:pressed {
    border-top: 2px solid #808080;
    border-left: 2px solid #808080;
    border-bottom: 2px solid #ffffff;
    border-right: 2px solid #ffffff;
}

QPushButton:hover {
    background-color: #e0ddd5;
}

QComboBox {
    background-color: #ffffff;
    border: 2px inset #808080;
    padding: 2px;
}

QComboBox::drop-down {
    border-left: 1px solid #808080;
    width: 16px;
}

QSplitter::handle {
    background-color: #d4d0c8;
    border: 1px solid #808080;
    width: 4px;
}

QStatusBar {
    background-color: #d4d0c8;
    border-top: 1px solid #808080;
    font-size: 11px;
}

QTabWidget::pane {
    border: 2px groove #808080;
}

QTabBar::tab {
    background-color: #d4d0c8;
    border: 1px solid #808080;
    border-bottom: none;
    padding: 3px 8px;
}

QTabBar::tab:selected {
    background-color: #d4d0c8;
    border-bottom: 2px solid #d4d0c8;
    font-weight: bold;
}

QLabel#title_label {
    background-color: #000080;
    color: #ffffff;
    font-weight: bold;
    font-size: 12px;
    padding: 4px 8px;
}

QFrame#separator {
    border: 1px inset #808080;
}
"""


# ---------------------------------------------------------------------------
# Panel lewry — lista jobów

class JobListPanel(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self._all_jobs: list[Job] = []
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Tytuł
        title = QLabel("JOBS")
        title.setObjectName("title_label")
        layout.addWidget(title)

        # Filtr kategorii
        cat_box = QGroupBox("Kategoria")
        cat_layout = QVBoxLayout(cat_box)
        self.category_combo = QComboBox()
        self.category_combo.addItem("-- Wszystkie --")
        for label in sorted(set(JOB_CATEGORIES.values())):
            self.category_combo.addItem(label)
        self.category_combo.addItem("🔩 Inne")
        self.category_combo.currentTextChanged.connect(self._apply_filter)
        cat_layout.addWidget(self.category_combo)
        layout.addWidget(cat_box)

        # Wyszukiwarka
        search_box = QGroupBox("Szukaj")
        search_layout = QVBoxLayout(search_box)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Nazwa joba...")
        self.search_edit.textChanged.connect(self._apply_filter)
        search_layout.addWidget(self.search_edit)
        layout.addWidget(search_box)

        # Lista jobów
        jobs_box = QGroupBox("Lista jobów")
        jobs_layout = QVBoxLayout(jobs_box)
        self.job_count_label = QLabel("Brak wczytanego pliku")
        self.job_count_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        jobs_layout.addWidget(self.job_count_label)
        self.job_list = QListWidget()
        self.job_list.setMinimumWidth(220)
        jobs_layout.addWidget(self.job_list)
        layout.addWidget(jobs_box)

    def load_jobs(self, jobs: list[Job]):
        self._all_jobs = jobs
        self._apply_filter()
        self.job_count_label.setText(f"Jobów: {len(jobs)}")

    def _apply_filter(self):
        search = self.search_edit.text().strip().upper()
        category = self.category_combo.currentText()

        self.job_list.clear()
        for job in self._all_jobs:
            cat = get_category(job.name)
            if category != "-- Wszystkie --" and cat != category:
                continue
            if search and search not in job.name.upper():
                continue
            item = QListWidgetItem(job.name)
            item.setData(Qt.ItemDataRole.UserRole, job)
            # Kolor według kategorii
            cat_prefix = job.name.split("_")[0]
            colors = {
                "STATUS":    ("#1a5c1a", "#ffffff"),
                "STEUERN":   ("#8b4500", "#ffffff"),
                "FS":        ("#8b0000", "#ffffff"),
                "LESEN":     ("#003580", "#ffffff"),
                "IDENT":     ("#4b0082", "#ffffff"),
                "ADAP":      ("#556b2f", "#ffffff"),
                "EWS":       ("#8b008b", "#ffffff"),
                "SEED":      ("#8b008b", "#ffffff"),
                "RAM":       ("#2f4f4f", "#ffffff"),
                "DATA":      ("#2f4f4f", "#ffffff"),
                "START":     ("#003580", "#ffffff"),
                "STOP":      ("#003580", "#ffffff"),
                "ENDE":      ("#003580", "#ffffff"),
            }
            style = colors.get(cat_prefix, ("#333333", "#ffffff"))
            item.setBackground(QColor(style[0]))
            item.setForeground(QColor(style[1]))
            self.job_list.addItem(item)

        count = self.job_list.count()
        if self._all_jobs:
            self.job_count_label.setText(
                f"Pokazano: {count} / {len(self._all_jobs)}"
            )


# ---------------------------------------------------------------------------
# Panel prawy — szczegóły joba

class JobDetailPanel(QWidget):
    languageChanged = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_job: Job | None = None
        self._current_tables: list[Table] = []
        self._current_prg_file: str = ""
        self._current_comments_de: str = "Brak komentarzy."
        self._db: Database | None = None
        self._lang: str = "de"
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Tytuł
        self.title_label = QLabel("SZCZEGÓŁY JOBA")
        self.title_label.setObjectName("title_label")
        layout.addWidget(self.title_label)

        # Zakładki
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # --- Zakładka: Informacje ogólne ---
        info_widget = QWidget()
        info_layout = QVBoxLayout(info_widget)

        self.job_name_label = QLabel("—")
        self.job_name_label.setFont(QFont("Courier New", 12, QFont.Weight.Bold))
        info_layout.addWidget(self.job_name_label)

        self.job_addr_label = QLabel("Adres: —")
        info_layout.addWidget(self.job_addr_label)

        self.job_category_label = QLabel("Kategoria: —")
        info_layout.addWidget(self.job_category_label)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setObjectName("separator")
        info_layout.addWidget(sep)

        self.comment_box = QGroupBox("Komentarze z pliku .prg")
        comment_layout = QVBoxLayout(self.comment_box)

        comment_header = QHBoxLayout()
        comment_header.addWidget(QLabel("Język:"))
        self.lang_combo = QComboBox()
        self.lang_combo.addItem("DE", "de")
        self.lang_combo.addItem("EN", "en")
        self.lang_combo.addItem("PL", "pl")
        self.lang_combo.currentIndexChanged.connect(self._emit_language_changed)
        comment_header.addWidget(self.lang_combo)
        comment_header.addStretch()
        comment_layout.addLayout(comment_header)

        self.job_comment_label = QLabel("Opis: —")
        self.job_comment_label.setWordWrap(True)
        self.job_comment_label.setStyleSheet("font-weight: bold;")
        comment_layout.addWidget(self.job_comment_label)

        self.results_table = QTableWidget()
        self.results_table.setColumnCount(3)
        self.results_table.setHorizontalHeaderLabels(["Wynik", "Typ", "Opis"])
        self.results_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.results_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.results_table.setMinimumHeight(140)
        self.results_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self.results_table.horizontalHeader().setStretchLastSection(True)
        comment_layout.addWidget(self.results_table)

        # Splitter pod komentarzami pozwala ręcznie zwiększać/zmniejszać
        # wysokość pola tekstowego bez zmiany jego położenia w UI.
        comments_resizer = QSplitter(Qt.Orientation.Vertical)
        comments_resizer.setHandleWidth(6)
        comments_resizer.setChildrenCollapsible(True)
        comments_resizer.addWidget(self.comment_box)
        comments_resizer.addWidget(QWidget())
        comments_resizer.setSizes([260, 80])
        info_layout.addWidget(comments_resizer, 1)

        self._set_translation_state("idle")
        self.tabs.addTab(info_widget, "ℹ️ Ogólne")

        # --- Zakładka: Parametry (BETRIEBSWTAB) ---
        params_widget = QWidget()
        params_layout = QVBoxLayout(params_widget)

        self.params_tree = QTreeWidget()
        self.params_tree.setHeaderLabels([
            "Nazwa", "Bajt", "Typ", "Jedn.", "FACT_A", "FACT_B", "Telegram DS2"
        ])
        self.params_tree.header().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        params_layout.addWidget(self.params_tree)
        self.tabs.addTab(params_widget, "📊 Parametry")

        # --- Zakładka: Disassembly ---
        dis_widget = QWidget()
        dis_layout = QVBoxLayout(dis_widget)
        self.dis_text = QTextEdit()
        self.dis_text.setReadOnly(True)
        self.dis_text.setFont(QFont("Courier New", 10))
        self.dis_text.setStyleSheet(
            "background-color: #000000; color: #00ff00;"
        )
        dis_layout.addWidget(self.dis_text)
        self.tabs.addTab(dis_widget, "🔧 Disassembly")

    def show_job(
        self,
        job: Job,
        tables: list[Table],
        db: Database | None = None,
        lang: str = "de",
        prg_file: str = "",
    ):
        self._current_job = job
        self._current_tables = tables
        self._current_prg_file = (prg_file or "").upper()
        self._db = db
        self._lang = (lang or "de").lower()
        self._set_language_combo(self._lang)

        self.title_label.setText(f"JOB: {job.name}")
        self.job_name_label.setText(job.name)
        self.job_addr_label.setText(f"Adres w pliku: 0x{job.address:08X}")
        self.job_category_label.setText(f"Kategoria: {get_category(job.name)}")

        # Komentarze
        comments = [c for c in job.comments if not c.startswith("JOBNAME:")]
        job_comment, result_rows = self._parse_job_comments(comments)
        self._current_comments_de = job_comment or "Brak komentarzy."
        self.job_comment_label.setText(f"Opis: {self._current_comments_de}")

        self.results_table.setRowCount(len(result_rows))
        for row_index, (result_name, result_type, result_comment) in enumerate(result_rows):
            self.results_table.setItem(row_index, 0, QTableWidgetItem(result_name))
            self.results_table.setItem(row_index, 1, QTableWidgetItem(result_type))
            self.results_table.setItem(row_index, 2, QTableWidgetItem(result_comment))
        self.results_table.resizeColumnsToContents()

        # Tłumaczenie wg wybranego języka
        self._refresh_translation()

        # Parametry z BETRIEBSWTAB
        self._load_params(job, tables)

        # Disassembly
        self.dis_text.setPlainText(
            "\n".join(job.disassembly) if job.disassembly
            else "; Brak disassembly"
        )

    def update_language(self, lang: str):
        self._lang = (lang or "de").lower()
        self._set_language_combo(self._lang)
        self._refresh_translation()

    def current_language(self) -> str:
        return self._lang

    def _emit_language_changed(self, _index: int):
        self._lang = self.lang_combo.currentData() or "de"
        self.languageChanged.emit(self._lang)

    def _set_language_combo(self, lang: str):
        index = self.lang_combo.findData(lang)
        if index >= 0 and index != self.lang_combo.currentIndex():
            self.lang_combo.blockSignals(True)
            self.lang_combo.setCurrentIndex(index)
            self.lang_combo.blockSignals(False)

    def _refresh_translation(self):
        if not self._current_job:
            self.job_comment_label.setText("Opis: —")
            self._set_translation_state("idle")
            return

        translation = None
        if self._db:
            translation = self._db.get_translation(
                self._current_prg_file,
                self._current_job.name,
                self._lang,
            )

        if translation:
            self.job_comment_label.setText(f"Opis: {translation}")
            self._set_translation_state("ok")
            return

        if self._lang == "de":
            self.job_comment_label.setText(f"Opis: {self._current_comments_de}")
            self._set_translation_state("ok")
            return

        self.job_comment_label.setText(
            f"Opis: ⚠️ Brak tłumaczenia ({self._lang.upper()}) — {self._current_comments_de}"
        )
        self._set_translation_state("missing")

    def _parse_job_comments(self, comments: list[str]) -> tuple[str, list[tuple[str, str, str]]]:
        job_comment = ""
        results: list[tuple[str, str, str]] = []
        current_result = ""
        current_type = ""
        current_comment = ""

        def flush_result():
            nonlocal current_result, current_type, current_comment
            if current_result:
                results.append((current_result, current_type, current_comment))
            current_result = ""
            current_type = ""
            current_comment = ""

        for entry in comments:
            line = entry.strip()
            upper = line.upper()
            if upper.startswith("JOBCOMMENT:"):
                job_comment = line.split(":", 1)[1].strip()
            elif upper.startswith("RESULT:"):
                flush_result()
                current_result = line.split(":", 1)[1].strip()
            elif upper.startswith("RESULTTYPE:"):
                current_type = line.split(":", 1)[1].strip()
            elif upper.startswith("RESULTCOMMENT:"):
                current_comment = line.split(":", 1)[1].strip()

        flush_result()
        return job_comment, results

    def _set_translation_state(self, state: str):
        if state == "missing":
            self.comment_box.setTitle("Komentarze z pliku .prg — BRAK TŁUMACZENIA")
            self.job_comment_label.setStyleSheet(
                "background-color: #ffe4e4;"
                "border: 1px solid #8b0000;"
                "color: #8b0000;"
                "font-weight: bold;"
                "padding: 4px;"
            )
            return

        self.comment_box.setTitle("Komentarze z pliku .prg")
        if state == "ok":
            self.job_comment_label.setStyleSheet(
                "color: #000000;"
                "font-weight: bold;"
            )
            return

        self.job_comment_label.setStyleSheet(
            "color: #808080;"
            "font-weight: bold;"
        )

    def _load_params(self, job: "Job", tables: list["Table"]):
        self.params_tree.clear()

        # Szukamy tabeli BETRIEBSWTAB
        betrieb = None
        for table in tables:
            if "BETRIEBSWTAB" in table.name.upper():
                betrieb = table
                break

        if not betrieb:
            item = QTreeWidgetItem(["Plik .prg nie zawiera tabeli BETRIEBSWTAB", "", "", "", "", ""])
            self.params_tree.addTopLevelItem(item)
            return

        # Znajdź indeksy kolumn
        cols = [c.upper() for c in betrieb.columns]
        def col(name):
            try:
                return cols.index(name.upper())
            except ValueError:
                return -1

        idx_name    = col("NAME")
        idx_tel     = col("TELEGRAM")
        idx_byte    = col("BYTE")
        idx_dtype   = col("DATA_TYPE")
        idx_meas    = col("MEAS")
        idx_facta   = col("FACT_A")
        idx_factb   = col("FACT_B")

        def get_val(row, idx):
            if idx == -1 or idx >= len(row.values):
                return "—"
            return row.values[idx].strip()

        # Wyciągnij nazwy parametrów z disassembly
        # Job robi: move S1,"NMOT_W" → tabseek "NAME",S1
        # czyli szuka w BETRIEBSWTAB po NAME = "NMOT_W"
        param_names = self._extract_param_names_from_disassembly(job.disassembly)

        if not param_names:
            item = QTreeWidgetItem(
                ["Brak danych live data — job zwraca status tekstowy lub wykonuje akcję", "", "", "", "", "", ""]
            )
            self.params_tree.addTopLevelItem(item)
            return

        # Dopasuj wiersze BETRIEBSWTAB przez kolumnę NAME
        found = False
        for row in betrieb.rows:
            row_name = get_val(row, idx_name).upper().strip()
            if row_name not in param_names:
                continue
            found = True
            name  = get_val(row, idx_name)
            byte_ = get_val(row, idx_byte)
            dtype = get_val(row, idx_dtype)
            meas  = get_val(row, idx_meas)
            facta = get_val(row, idx_facta)
            factb = get_val(row, idx_factb)
            raw_tel = get_val(row, idx_tel).upper().replace(" ", "")
            tel_fmt = self._format_telegram(raw_tel)
            item = QTreeWidgetItem([name, byte_, dtype, meas, facta, factb, tel_fmt])
            self.params_tree.addTopLevelItem(item)

        if not found:
            item = QTreeWidgetItem(
                ["Brak danych live data — job zwraca status tekstowy lub wykonuje akcję", "", "", "", "", "", ""]
            )
            self.params_tree.addTopLevelItem(item)

    def _extract_param_names_from_disassembly(self, disassembly: list[str]) -> set[str]:
        """
        Wyciąga nazwy parametrów z disassembly joba.
        Job robi: move S1,"NMOT_W" → tabseek "NAME",S1
        Szukamy stringów w cudzysłowach które są używane jako nazwy w tabset/tabseek.
        """
        import re
        names = set()
        # Wzorzec: move Sx,"NAZWA_PARAMETRU" przed tabseek "NAME"
        str_pattern = re.compile(r'move\s+\w+,"([^"]+)"')
        tabset_seen = False

        for line in disassembly:
            stripped = line.strip()
            if "tabset" in stripped.lower() and "betriebswtab" in stripped.lower():
                tabset_seen = True
            if tabset_seen and "tabseek" in stripped.lower():
                # Wyciągnij string z poprzednich move
                pass
            # Wyciągnij wszystkie stringi z move które wyglądają jak nazwy parametrów
            # (wielkie litery, podkreślenia, cyfry — nie są to normalne słowa)
            for match in str_pattern.finditer(stripped):
                val = match.group(1)
                # Filtruj: nazwy parametrów to CAPS_WITH_UNDERSCORES
                # pomijamy "OKAY", "NEG_RESPONSE" itd. które są wynikami
                if (val.isupper() or "_" in val) and len(val) > 2:
                    # Pomijamy znane nie-parametry
                    skip = {"OKAY", "NEG_RESPONSE", "UNDEF", "NAME", "TELEGRAM",
                            "BYTE", "MEAS", "FACT_A", "FACT_B", "DATA_TYPE",
                            "FEHLERTEXT", "CODE", "WERT", "ERGEBNIS"}
                    if val not in skip:
                        names.add(val.upper())

        return names

    def _format_telegram(self, raw_hex: str) -> str:
        """Formatuje surowy hex telegramu jako 0xXX, 0xXX, ... + checksum XOR."""
        try:
            parts = []
            checksum = 0
            for i in range(0, len(raw_hex), 2):
                val = int(raw_hex[i:i+2], 16)
                checksum ^= val
                parts.append(f"0x{val:02X}")
            parts.append(f"0x{checksum:02X}")
            return ", ".join(parts)
        except Exception:
            return raw_hex

    def clear(self):
        self._current_job = None
        self._current_tables = []
        self._current_prg_file = ""
        self._current_comments_de = "Brak komentarzy."
        self.title_label.setText("SZCZEGÓŁY JOBA")
        self.job_name_label.setText("—")
        self.job_addr_label.setText("Adres: —")
        self.job_category_label.setText("Kategoria: —")
        self.job_comment_label.setText("Opis: —")
        self.results_table.setRowCount(0)
        self._set_translation_state("idle")
        self.params_tree.clear()
        self.dis_text.clear()


# ---------------------------------------------------------------------------
# Panel tabel

class TablesPanel(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tables: list[Table] = []
        self._current_table: Table | None = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        left_box = QGroupBox("Tabele z pliku .prg")
        left_layout = QVBoxLayout(left_box)

        table_search_row = QHBoxLayout()
        table_search_row.addWidget(QLabel("Tabela:"))
        self.table_search_edit = QLineEdit()
        self.table_search_edit.setPlaceholderText("Szukaj po nazwie tabeli...")
        self.table_search_edit.textChanged.connect(self._apply_table_name_filter)
        table_search_row.addWidget(self.table_search_edit)
        left_layout.addLayout(table_search_row)

        self.tables_count_label = QLabel("Brak wczytanego pliku")
        self.tables_count_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        left_layout.addWidget(self.tables_count_label)

        self.tables_tree = QTreeWidget()
        self.tables_tree.setHeaderHidden(True)
        self.tables_tree.currentItemChanged.connect(self._on_table_selected)
        left_layout.addWidget(self.tables_tree)

        right_box = QGroupBox("Podgląd tabeli")
        right_layout = QVBoxLayout(right_box)

        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Filtr:"))
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("Szukaj w wierszach tabeli...")
        self.filter_edit.textChanged.connect(self._apply_filter)
        filter_row.addWidget(self.filter_edit)
        right_layout.addLayout(filter_row)

        self.row_count_label = QLabel("Wybierz tabelę z listy po lewej.")
        self.row_count_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        right_layout.addWidget(self.row_count_label)

        self.table_widget = QTableWidget()
        self.table_widget.setAlternatingRowColors(False)
        right_layout.addWidget(self.table_widget)

        layout.addWidget(left_box, 1)
        layout.addWidget(right_box, 3)

    def load_tables(self, tables: list[Table]):
        self._tables = tables
        self._current_table = None
        self.tables_tree.clear()
        self.table_widget.clear()
        self.table_widget.setRowCount(0)
        self.table_widget.setColumnCount(0)
        self.filter_edit.clear()
        self.table_search_edit.clear()

        self.tables_count_label.setText(f"Tablic: {len(tables)}")

        if not tables:
            self.row_count_label.setText("Brak tabel w pliku.")
            return

        top_items: dict[str, QTreeWidgetItem] = {}
        for category in ["Błędy", "Statusy", "Bity", "Komunikacja", "Inne"]:
            item = QTreeWidgetItem([category])
            bg, fg = TABLE_CATEGORY_COLORS.get(category, ("#d4d0c8", "#000000"))
            item.setBackground(0, QColor(bg))
            item.setForeground(0, QColor(fg))
            top_items[category] = item
            self.tables_tree.addTopLevelItem(item)
            item.setExpanded(True)

        for table in tables:
            category = get_table_category(table.name)
            count = len(table.rows) if getattr(table, "rows", None) is not None else 0
            table_item = QTreeWidgetItem([f"{table.name} ({count})"])
            table_item.setData(0, Qt.ItemDataRole.UserRole, table)
            table_item.setData(0, Qt.ItemDataRole.UserRole + 1, table.name)
            bg, fg = TABLE_CATEGORY_COLORS.get(category, ("#333333", "#ffffff"))
            table_item.setBackground(0, QColor(bg))
            table_item.setForeground(0, QColor(fg))
            top_items[category].addChild(table_item)

        self._apply_table_name_filter()

        first_child = None
        for index in range(self.tables_tree.topLevelItemCount()):
            top_item = self.tables_tree.topLevelItem(index)
            for child_index in range(top_item.childCount()):
                child = top_item.child(child_index)
                if not child.isHidden():
                    first_child = child
                    break
            if first_child:
                break

        if first_child:
            self.tables_tree.setCurrentItem(first_child)

    def _on_table_selected(self, current, previous):
        table = None
        if current:
            table = current.data(0, Qt.ItemDataRole.UserRole)
        self._current_table = table
        self._apply_filter()

    def _apply_filter(self):
        if not self._current_table:
            self.row_count_label.setText("Wybierz tabelę z listy po lewej.")
            self.table_widget.setRowCount(0)
            self.table_widget.setColumnCount(0)
            return

        columns = list(getattr(self._current_table, "columns", []) or [])
        rows = list(getattr(self._current_table, "rows", []) or [])
        display_columns = self._get_display_columns(self._current_table)

        self.table_widget.clear()
        self.table_widget.setColumnCount(len(display_columns))
        self.table_widget.setHorizontalHeaderLabels([label for _, label in display_columns])

        query = self.filter_edit.text().strip().upper()
        visible_rows = []
        for row in rows:
            values = [str(value) for value in getattr(row, "values", [])]
            haystack = " ".join(values).upper()
            if query and query not in haystack:
                continue
            visible_rows.append(values)

        self.table_widget.setRowCount(len(visible_rows))
        for row_index, values in enumerate(visible_rows):
            value_map = {
                columns[col_index].upper(): values[col_index] if col_index < len(values) else ""
                for col_index in range(len(columns))
            }
            for col_index, (source_name, _label) in enumerate(display_columns):
                self.table_widget.setItem(
                    row_index,
                    col_index,
                    QTableWidgetItem(value_map.get(source_name.upper(), "")),
                )

        self.table_widget.resizeColumnsToContents()
        self.row_count_label.setText(
            f"Wiersze: {len(visible_rows)} / {len(rows)}"
            if query else f"Wiersze: {len(rows)}"
        )

    def _apply_table_name_filter(self):
        query = self.table_search_edit.text().strip().upper()
        visible_tables = 0

        for index in range(self.tables_tree.topLevelItemCount()):
            top_item = self.tables_tree.topLevelItem(index)
            visible_children = 0
            for child_index in range(top_item.childCount()):
                child = top_item.child(child_index)
                table_name = (child.data(0, Qt.ItemDataRole.UserRole + 1) or "").upper()
                match = (not query) or (query in table_name)
                child.setHidden(not match)
                if match:
                    visible_children += 1
                    visible_tables += 1

            top_item.setHidden(visible_children == 0)

        self.tables_count_label.setText(f"Tablic: {visible_tables} / {len(self._tables)}")

        current = self.tables_tree.currentItem()
        if current and current.isHidden():
            self.tables_tree.setCurrentItem(None)
            self._current_table = None
            self._apply_filter()

    def _get_display_columns(self, table: Table) -> list[tuple[str, str]]:
        raw_columns = list(getattr(table, "columns", []) or [])
        upper_columns = [col.upper() for col in raw_columns]
        table_name = table.name.upper()
        preset = TABLE_COLUMN_PRESETS.get(table_name)

        if not preset:
            if table_name.startswith("EWS") and "STATI" in upper_columns and "TEXT" in upper_columns:
                preset = [("STATI", "Status"), ("TEXT", "Opis")]
            else:
                return [(col, col) for col in raw_columns]

        display = []
        used_upper = set()
        for source_name, label in preset:
            if source_name.upper() in upper_columns:
                display.append((source_name, label))
                used_upper.add(source_name.upper())

        for col in raw_columns:
            if col.upper() not in used_upper:
                display.append((col, col))

        return display

    def clear(self):
        self._tables = []
        self._current_table = None
        self.tables_tree.clear()
        self.table_widget.clear()
        self.table_widget.setRowCount(0)
        self.table_widget.setColumnCount(0)
        self.tables_count_label.setText("Brak wczytanego pliku")
        self.row_count_label.setText("Wybierz tabelę z listy po lewej.")
        self.filter_edit.clear()
        self.table_search_edit.clear()


# ---------------------------------------------------------------------------
# Panel modeli INPA

class ModelsPanel(QWidget):
    openPrgRequested = pyqtSignal(str)
    changeInpaPathRequested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._models_data: dict = {}
        self._inpa_path: str = ""
        self._ecu_path: str = ""
        self._current_entry: dict | None = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        left_box = QGroupBox("Modele INPA")
        left_layout = QVBoxLayout(left_box)

        controls_row = QHBoxLayout()
        self.change_path_btn = QPushButton("Zmień ścieżkę INPA")
        self.change_path_btn.clicked.connect(self.changeInpaPathRequested.emit)
        controls_row.addWidget(self.change_path_btn)
        controls_row.addStretch()
        left_layout.addLayout(controls_row)

        self.inpa_status_label = QLabel("Nie znaleziono instalacji INPA")
        self.inpa_status_label.setWordWrap(True)
        left_layout.addWidget(self.inpa_status_label)

        self.models_tree = QTreeWidget()
        self.models_tree.setHeaderHidden(True)
        self.models_tree.currentItemChanged.connect(self._on_tree_item_changed)
        left_layout.addWidget(self.models_tree)

        right_box = QGroupBox("Szczegóły ECU")
        right_layout = QVBoxLayout(right_box)

        self.description_label = QLabel("—")
        self.description_label.setWordWrap(True)
        right_layout.addWidget(self.description_label)

        self.script_label = QLabel("Skrypt INPA: —")
        self.script_label.setWordWrap(True)
        right_layout.addWidget(self.script_label)

        self.prg_list_label = QLabel("Dostępne pliki PRG:")
        right_layout.addWidget(self.prg_list_label)

        self.prg_list_widget = QListWidget()
        self.prg_list_widget.currentItemChanged.connect(self._on_prg_item_changed)
        right_layout.addWidget(self.prg_list_widget)

        self.prg_status_label = QLabel("—")
        self.prg_status_label.setWordWrap(True)
        right_layout.addWidget(self.prg_status_label)

        self.open_prg_btn = QPushButton("Otwórz plik PRG")
        self.open_prg_btn.setEnabled(False)
        self.open_prg_btn.clicked.connect(self._open_selected_prg)
        right_layout.addWidget(self.open_prg_btn)

        right_layout.addStretch()

        layout.addWidget(left_box, 1)
        layout.addWidget(right_box, 1)

    def set_placeholder(self, message: str):
        self._models_data = {}
        self._current_entry = None
        self.models_tree.clear()
        self.description_label.setText("—")
        self.script_label.setText("Skrypt INPA: —")
        self.prg_list_widget.clear()
        self.prg_status_label.setText(message)
        self.open_prg_btn.setEnabled(False)
        self.inpa_status_label.setText(message)

    def set_models_data(self, models_data: dict, inpa_path: str, ecu_path: str):
        self._models_data = models_data or {}
        self._inpa_path = inpa_path or ""
        self._ecu_path = ecu_path or ""
        self._current_entry = None

        self.models_tree.clear()
        self.inpa_status_label.setText(
            f"INPA: {self._inpa_path}" if self._inpa_path else "Nie znaleziono instalacji INPA"
        )

        if not self._models_data:
            self.set_placeholder("Nie znaleziono plików .ENG w CFGDAT")
            return

        model_names = sorted(self._models_data.keys())
        for model_name in model_names:
            model_item = QTreeWidgetItem([model_name])
            self.models_tree.addTopLevelItem(model_item)
            model_bucket = self._models_data.get(model_name, {})

            for category in ["Silnik", "Skrzynia", "Podwozie", "Karoseria", "Komunikacja"]:
                entries = model_bucket.get(category, [])
                if not entries:
                    continue

                category_item = QTreeWidgetItem([category])
                model_item.addChild(category_item)

                for entry in entries:
                    entry_item = QTreeWidgetItem([entry.get("description", "")])
                    entry_item.setData(0, Qt.ItemDataRole.UserRole, entry)
                    category_item.addChild(entry_item)

                category_item.setExpanded(True)

            model_item.setExpanded(True)

        first_entry = self._find_first_leaf_item()
        if first_entry:
            self.models_tree.setCurrentItem(first_entry)

    def _find_first_leaf_item(self) -> QTreeWidgetItem | None:
        for i in range(self.models_tree.topLevelItemCount()):
            model_item = self.models_tree.topLevelItem(i)
            for j in range(model_item.childCount()):
                category_item = model_item.child(j)
                for k in range(category_item.childCount()):
                    leaf = category_item.child(k)
                    if leaf is not None:
                        return leaf
        return None

    def _on_tree_item_changed(self, current, previous):
        entry = None
        if current:
            entry = current.data(0, Qt.ItemDataRole.UserRole)
        self._current_entry = entry
        self._update_details()

    def _update_details(self):
        if not self._current_entry:
            self.description_label.setText("Wybierz ECU z listy po lewej.")
            self.script_label.setText("Skrypt INPA: —")
            self.prg_list_widget.clear()
            self.prg_status_label.setText("—")
            self.open_prg_btn.setEnabled(False)
            return

        description = self._current_entry.get("description") or "—"
        script_name = self._current_entry.get("script") or ""
        prg_files = list(self._current_entry.get("prg_file") or [])

        self.description_label.setText(description)
        self.script_label.setText(f"Skrypt INPA: {script_name or '—'}")
        self.prg_list_widget.blockSignals(True)
        self.prg_list_widget.clear()

        if not prg_files:
            item = QListWidgetItem("Brak wykrytych plików PRG")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.prg_list_widget.addItem(item)
            self.prg_status_label.setText("❌ Brak dopasowań")
            self.open_prg_btn.setEnabled(False)
            self.prg_list_widget.blockSignals(False)
            return

        first_existing_row = -1
        for prg_file in prg_files:
            prg_display = prg_file if prg_file.lower().endswith(".prg") else f"{prg_file}.prg"
            exists = False
            full_path = None
            if self._ecu_path:
                full_path = Path(self._ecu_path) / prg_display
                exists = full_path.exists()

            prefix = "✅" if exists else "❌"
            item_text = f"{prefix} {prg_display}"
            if exists:
                item_text += f"  [{full_path}]"
            item = QListWidgetItem(item_text)
            item.setData(Qt.ItemDataRole.UserRole, prg_display)
            item.setData(Qt.ItemDataRole.UserRole + 1, str(full_path) if full_path else "")
            self.prg_list_widget.addItem(item)
            if exists and first_existing_row == -1:
                first_existing_row = self.prg_list_widget.count() - 1

        if first_existing_row >= 0:
            self.prg_list_widget.setCurrentRow(first_existing_row)
        else:
            self.prg_list_widget.setCurrentRow(0)
        self.prg_list_widget.blockSignals(False)
        self._update_prg_selection_state(self.prg_list_widget.currentItem())

    def _on_prg_item_changed(self, current, previous):
        self._update_prg_selection_state(current)

    def _update_prg_selection_state(self, current_item):
        if not current_item:
            self.prg_status_label.setText("—")
            self.open_prg_btn.setEnabled(False)
            return

        prg_display = current_item.data(Qt.ItemDataRole.UserRole) or ""
        full_path = current_item.data(Qt.ItemDataRole.UserRole + 1) or ""

        if full_path and Path(full_path).exists():
            self.prg_status_label.setText(f"✅ Znaleziono: {full_path}")
            self.open_prg_btn.setEnabled(True)
        else:
            ecu_folder = self._ecu_path or "EDIABAS\\Ecu"
            self.prg_status_label.setText(f"❌ Nie znaleziono w {ecu_folder}")
            self.open_prg_btn.setEnabled(False)

        if not prg_display:
            self.open_prg_btn.setEnabled(False)

    def _open_selected_prg(self):
        current_item = self.prg_list_widget.currentItem()
        if not current_item or not self._ecu_path:
            return

        prg_display = current_item.data(Qt.ItemDataRole.UserRole) or ""
        if not prg_display:
            return

        full_path = Path(self._ecu_path) / prg_display
        if full_path.exists():
            self.openPrgRequested.emit(str(full_path))


# ---------------------------------------------------------------------------
# Panel informacji o pliku

class FileInfoPanel(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)

        self.file_label  = QLabel("Plik: —")
        self.ver_label   = QLabel("BIP: —")
        self.rev_label   = QLabel("Rev: —")
        self.author_label = QLabel("Autor: —")
        self.date_label  = QLabel("Data: —")

        for lbl in [self.file_label, self.ver_label, self.rev_label,
                    self.author_label, self.date_label]:
            layout.addWidget(lbl)
            sep = QFrame()
            sep.setFrameShape(QFrame.Shape.VLine)
            layout.addWidget(sep)

        layout.addStretch()
        self.setMaximumHeight(32)
        self.setStyleSheet(
            "background-color: #c0c0c0; border-bottom: 1px solid #808080;"
        )

    def load_info(self, prg: "PrgFile", filepath: str):
        name = Path(filepath).name
        self.file_label.setText(f"Plik: {name}")
        self.ver_label.setText(f"BIP: {prg.info.bip_version}")
        self.rev_label.setText(f"Rev: {prg.info.revision}")
        self.author_label.setText(f"Autor: {prg.info.author[:30]}")
        self.date_label.setText(f"Data: {prg.info.last_changed[:24]}")


# ---------------------------------------------------------------------------
# Główne okno

class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self._prg: PrgFile | None = None
        self._filepath: str = ""
        self._lang: str = "de"
        self._db: Database | None = None
        self._inpa_path: str = self._detect_inpa_path() or ""
        self._ecu_path: str = self._detect_ecu_path() or ""
        self._models_data: dict = {}
        self._models_loaded_for_path: str = ""
        self._models_parser_cls = None

        if DB_AVAILABLE:
            db_path = Path(__file__).resolve().parent / "data" / "database.db"
            try:
                self._db = Database(str(db_path))
            except Exception:
                self._db = None

        self._set_app_icon()

        self._setup_ui()
        self._setup_menu()
        self.setStyleSheet(WIN98_STYLE)

    def _detect_inpa_path(self) -> str | None:
        for candidate in [
            r"C:\EC-APPS\INPA",
            r"C:\EDIABAS\INPA",
            r"C:\Program Files\BMW\INPA",
        ]:
            if Path(candidate).exists():
                return candidate
        return None

    def _detect_ecu_path(self) -> str | None:
        for candidate in [
            r"C:\EDIABAS\Ecu",
            r"C:\EC-APPS\EDIABAS\Ecu",
        ]:
            if Path(candidate).exists():
                return candidate
        return None

    def _set_app_icon(self):
        icon_path = Path(__file__).resolve().parent / "bimmerdatenlogo.ico"
        if icon_path.exists():
            icon = QIcon(str(icon_path))
            self.setWindowIcon(icon)

    def _setup_ui(self):
        self.setWindowTitle("BimmerDaten — EDIABAS PRG Viewer")
        self.setMinimumSize(900, 600)
        self.resize(1100, 700)

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Pasek informacji o pliku
        self.file_info = FileInfoPanel()
        main_layout.addWidget(self.file_info)

        self.main_tabs = QTabWidget()
        main_layout.addWidget(self.main_tabs)

        # Tab 1: widok jobów
        jobs_tab = QWidget()
        jobs_layout = QVBoxLayout(jobs_tab)
        jobs_layout.setContentsMargins(0, 0, 0, 0)
        jobs_layout.setSpacing(0)

        toolbar_widget = QWidget()
        toolbar_widget.setMaximumHeight(48)
        toolbar_widget.setStyleSheet(
            "background-color: #d4d0c8; border-bottom: 1px solid #808080;"
        )
        toolbar_layout = QHBoxLayout(toolbar_widget)
        toolbar_layout.setContentsMargins(4, 2, 4, 2)

        self.open_btn = QPushButton("📂 Otwórz .PRG")
        self.open_btn.clicked.connect(self._open_file)
        toolbar_layout.addWidget(self.open_btn)

        self.vehicle_info_label = QLabel("Brak wczytanego pliku")
        self.vehicle_info_label.setWordWrap(True)
        toolbar_layout.addWidget(self.vehicle_info_label, 1)

        toolbar_layout.addStretch()

        self.jobs_info = QLabel("Brak wczytanego pliku")
        toolbar_layout.addWidget(self.jobs_info)

        jobs_layout.addWidget(toolbar_widget)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(4)

        self.job_list_panel = JobListPanel()
        self.job_detail_panel = JobDetailPanel()
        self.job_detail_panel.languageChanged.connect(self._on_language_changed)

        splitter.addWidget(self.job_list_panel)
        splitter.addWidget(self.job_detail_panel)
        splitter.setSizes([280, 820])

        jobs_layout.addWidget(splitter)
        self.main_tabs.addTab(jobs_tab, "💼 Joby")

        # Tab 2: tabele
        self.tables_panel = TablesPanel()
        self.main_tabs.addTab(self.tables_panel, "📋 Tabele")

        # Tab 3: modele INPA
        self.models_panel = ModelsPanel()
        self.models_panel.openPrgRequested.connect(self._open_file_direct)
        self.models_panel.changeInpaPathRequested.connect(self._choose_inpa_path)
        self.main_tabs.addTab(self.models_panel, "🚗 Modele")

        self.models_tab_index = 2
        self.main_tabs.currentChanged.connect(self._on_main_tab_changed)

        if not self._inpa_path:
            self.models_panel.set_placeholder("Nie znaleziono instalacji INPA")
        else:
            self.models_panel.set_placeholder("Wybierz zakładkę Modele, aby wczytać parser INPA")

        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Gotowy. Otwórz plik .PRG aby rozpocząć.")

        # Połącz kliknięcie na liście z panelem szczegółów
        self.job_list_panel.job_list.currentItemChanged.connect(
            self._on_job_selected
        )

    def _setup_menu(self):
        menubar = self.menuBar()

        # Menu Plik
        file_menu = menubar.addMenu("Plik")
        open_action = QAction("Otwórz .PRG...", self)
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self._open_file)
        file_menu.addAction(open_action)
        file_menu.addSeparator()
        exit_action = QAction("Zakończ", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # Menu Pomoc
        help_menu = menubar.addMenu("Pomoc")
        about_action = QAction("O programie", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    def _open_file(self):
        if not DECODER_AVAILABLE:
            self.status_bar.showMessage(
                "BŁĄD: Nie można zaimportować decoderPrg.py!"
            )
            return

        default_dir = r"C:\EDIABAS\Ecu"
        if not Path(default_dir).exists():
            default_dir = ""

        filepath, _ = QFileDialog.getOpenFileName(
            self,
            "Otwórz plik EDIABAS PRG",
            default_dir,
            "EDIABAS PRG Files (*.prg *.PRG);;All Files (*)"
        )
        if not filepath:
            return

        self._open_file_direct(filepath)

    def _open_file_direct(self, filepath: str):
        if not DECODER_AVAILABLE:
            self.status_bar.showMessage(
                "BŁĄD: Nie można zaimportować decoderPrg.py!"
            )
            return

        self.status_bar.showMessage(f"Wczytuję: {filepath}...")
        QApplication.processEvents()

        try:
            self._prg = parse_prg(filepath)
            self._filepath = filepath
            self._load_prg()
            self.main_tabs.setCurrentIndex(0)
            self.status_bar.showMessage(
                f"Wczytano: {Path(filepath).name} — "
                f"{len(self._prg.jobs)} jobów, "
                f"{len(self._prg.tables)} tabel"
            )
        except Exception as e:
            self.status_bar.showMessage(f"BŁĄD: {e}")

    def _choose_inpa_path(self):
        start_dir = self._inpa_path or r"C:\EC-APPS\INPA"
        folder = QFileDialog.getExistingDirectory(
            self,
            "Wybierz folder INPA",
            start_dir,
        )
        if not folder:
            return

        self._inpa_path = folder
        self._models_loaded_for_path = ""
        self._load_models_data(force_reload=True)

    def _on_main_tab_changed(self, index: int):
        if index == self.models_tab_index:
            self._load_models_data()

    def _ensure_inpa_parser(self):
        if self._models_parser_cls is not None:
            return self._models_parser_cls

        try:
            from inpa_parser import INPAParser
        except Exception as exc:
            self.status_bar.showMessage(f"BŁĄD INPA parsera: {exc}")
            return None

        self._models_parser_cls = INPAParser
        return self._models_parser_cls

    def _load_models_data(self, force_reload: bool = False):
        if not self._inpa_path:
            self.models_panel.set_placeholder("Nie znaleziono instalacji INPA")
            return

        if not force_reload and self._models_loaded_for_path == self._inpa_path:
            self.models_panel.set_models_data(self._models_data, self._inpa_path, self._ecu_path)
            return

        parser_cls = self._ensure_inpa_parser()
        if parser_cls is None:
            self.models_panel.set_placeholder("Nie udało się załadować parsera INPA")
            return

        try:
            parser = parser_cls(self._inpa_path)
            self._models_data = parser.parse_all()
            self._models_loaded_for_path = self._inpa_path
            self.models_panel.set_models_data(self._models_data, self._inpa_path, self._ecu_path)
            if self._models_data:
                self.status_bar.showMessage(f"Wczytano modele INPA z {self._inpa_path}")
            else:
                self.status_bar.showMessage("Nie znaleziono plików .ENG w CFGDAT")
        except Exception as exc:
            self.models_panel.set_placeholder(f"Błąd wczytywania INPA: {exc}")
            self.status_bar.showMessage(f"Błąd wczytywania INPA: {exc}")

    def _load_prg(self):
        if not self._prg:
            return

        self.file_info.load_info(self._prg, self._filepath)
        self.job_list_panel.load_jobs(self._prg.jobs)
        self.tables_panel.load_tables(self._prg.tables)
        self.job_detail_panel.clear()
        self._update_vehicle_info_bar()
        self.jobs_info.setText(
            f"Jobów: {len(self._prg.jobs)} | Tabel: {len(self._prg.tables)}"
        )

    def _update_vehicle_info_bar(self):
        if not self._prg or not self._filepath:
            self.vehicle_info_label.setText("Brak wczytanego pliku")
            return

        file_name = Path(self._filepath).name
        info = self._prg.info
        parts = [f"Plik: {file_name}"]
        if info.bip_version:
            parts.append(f"BIP: {info.bip_version}")
        if info.revision:
            parts.append(f"Rev: {info.revision}")
        if info.author:
            parts.append(f"Autor: {info.author}")
        if info.last_changed:
            parts.append(f"Data: {info.last_changed}")
        self.vehicle_info_label.setText(" | ".join(parts))

    def _on_job_selected(self, current, previous):
        if not current or not self._prg:
            return
        job: Job = current.data(Qt.ItemDataRole.UserRole)
        if job:
            self.job_detail_panel.show_job(
                job,
                self._prg.tables,
                self._db,
                self._lang,
                Path(self._filepath).stem,
            )
            self.status_bar.showMessage(
                f"Job: {job.name} @ 0x{job.address:08X} — "
                f"{get_category(job.name)}"
            )

    def _on_language_changed(self, _index: int):
        self._lang = self.job_detail_panel.current_language()
        self.job_detail_panel.update_language(self._lang)
        self.status_bar.showMessage(f"Język tłumaczeń: {self._lang.upper()}")

    def _show_about(self):
        self.status_bar.showMessage(
            "BimmerDaten v0.1 — EDIABAS PRG Viewer | "
            "Oparty na BimmerDis (GPL-3.0)"
        )

    def closeEvent(self, event):
        if self._db:
            self._db.close()
        super().closeEvent(event)


# ---------------------------------------------------------------------------
# Uruchomienie

def main():
    if platform.system() == "Windows":
        try:
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "BimmerDaten.PRGViewer"
            )
        except Exception:
            pass

    app = QApplication(sys.argv)
    app.setApplicationName("BimmerDaten")
    app.setApplicationDisplayName("BimmerDaten")
    app.setStyle("Windows")  # styl Windows dla lepszego efektu retro
    icon_path = Path(__file__).resolve().parent / "bimmerdatenlogo.ico"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()