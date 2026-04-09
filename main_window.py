import sys
import platform
import json
from pathlib import Path
from html import escape as html_escape
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QSplitter,
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QListWidget, QListWidgetItem, QTreeWidget,
    QTreeWidgetItem, QFileDialog, QStatusBar, QMenuBar,
    QMenu, QGroupBox, QTextEdit, QComboBox, QFrame,
    QSizePolicy, QHeaderView, QTabWidget, QTableWidget,
    QTableWidgetItem, QDialog, QTextBrowser, QMessageBox
)
from PyQt6.QtCore import Qt, QSize, pyqtSignal, QThread, QTimer
from PyQt6.QtGui import QFont, QAction, QColor, QPalette, QIcon, QPixmap

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

try:
    from trc_coding import CodingPanel
    CODING_AVAILABLE = True
except Exception:
    CODING_AVAILABLE = False

try:
    from sa_options_widget import SAOptionsWidget
    SA_OPTIONS_AVAILABLE = True
except Exception:
    SA_OPTIONS_AVAILABLE = False

try:
    import winsound
except Exception:
    winsound = None


def play_sound(sound_type: str = "success") -> None:
    """Gra dźwięk systemowy dla danego typu akcji."""
    if winsound is None:
        return

    try:
        if sound_type == "success":
            for freq, duration in [(800, 100), (1000, 100)]:
                winsound.Beep(freq, duration)
        elif sound_type == "error":
            for freq, duration in [(400, 150), (300, 150), (400, 150)]:
                winsound.Beep(freq, duration)
        elif sound_type == "warning":
            for freq, duration in [(600, 100), (800, 100), (600, 100)]:
                winsound.Beep(freq, duration)
        elif sound_type == "info":
            winsound.Beep(1200, 80)
    except Exception:
        pass



class TranslationWorker(QThread):
    translationFinished = pyqtSignal(str, str, str, str, str)

    def __init__(self, prg_file: str, job_name: str, text_de: str, lang: str, parent=None):
        super().__init__(parent)
        self.prg_file = prg_file
        self.job_name = job_name
        self.text_de = text_de
        self.lang = lang

    def run(self):
        try:
            from deep_translator import GoogleTranslator

            lang_map = {"en": "english", "pl": "polish"}
            translated = GoogleTranslator(source="german", target=lang_map[self.lang]).translate(self.text_de)
            self.translationFinished.emit(
                self.prg_file,
                self.job_name,
                self.lang,
                translated or "",
                self.text_de,
            )
        except Exception:
            self.translationFinished.emit(
                self.prg_file,
                self.job_name,
                self.lang,
                "",
                self.text_de,
            )


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
        self._translation_workers: list[TranslationWorker] = []
        self._translation_pending: set[tuple[str, str, str]] = set()
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

        self.job_comment_label = QLabel("—")
        self.job_comment_label.setWordWrap(True)
        self.job_comment_label.setFont(QFont("Tahoma", 13, QFont.Weight.Bold))
        self.job_comment_label.setTextFormat(Qt.TextFormat.RichText)
        comment_layout.addWidget(self.job_comment_label)

        self.args_label = QLabel("Argumenty (wejście):")
        self.args_label.setStyleSheet(
            "font-size: 9px; color: #555555; font-weight: bold;"
        )
        comment_layout.addWidget(self.args_label)

        self.args_table = QTableWidget()
        self.args_table.setColumnCount(3)
        self.args_table.setHorizontalHeaderLabels(["Argument", "Typ", "Opis"])
        self.args_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.args_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.args_table.setMinimumHeight(80)
        self.args_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self.args_table.horizontalHeader().setStretchLastSection(True)
        self.args_table.hide()
        self.args_label.hide()
        comment_layout.addWidget(self.args_table)

        self.results_label = QLabel("Wyniki (wyjście):")
        self.results_label.setStyleSheet(
            "font-size: 9px; color: #555555; font-weight: bold;"
        )
        comment_layout.addWidget(self.results_label)

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

        self.params_tree = None
        self.params_sub_tabs = QTabWidget()
        self.params_sub_tabs.setTabPosition(QTabWidget.TabPosition.North)
        params_layout.addWidget(self.params_sub_tabs)
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
        job_comment, result_rows, arg_rows = self._parse_job_comments(comments)
        self._current_comments_de = job_comment or "Brak komentarzy."
        self.job_comment_label.setText(self._current_comments_de)

        self.args_table.setRowCount(len(arg_rows))
        for row_index, (arg_name, arg_type, arg_comment) in enumerate(arg_rows):
            self.args_table.setItem(row_index, 0, QTableWidgetItem(arg_name))
            self.args_table.setItem(row_index, 1, QTableWidgetItem(arg_type))
            self.args_table.setItem(row_index, 2, QTableWidgetItem(arg_comment))
        if arg_rows:
            self.args_label.show()
            self.args_table.show()
            self.args_table.resizeColumnsToContents()
        else:
            self.args_table.hide()
            self.args_label.hide()

        self.results_table.setRowCount(len(result_rows))
        for row_index, (result_name, result_type, result_comment) in enumerate(result_rows):
            self.results_table.setItem(row_index, 0, QTableWidgetItem(result_name))
            self.results_table.setItem(row_index, 1, QTableWidgetItem(result_type))
            self.results_table.setItem(row_index, 2, QTableWidgetItem(result_comment))
        self.results_table.resizeColumnsToContents()

        # Tłumaczenie wg wybranego języka
        self._refresh_translation()

        # Parametry z BETRIEBSWTAB
        self._load_params(job, tables, self._db)

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
            self.job_comment_label.setText("—")
            self.job_comment_label.setToolTip("")
            self._set_translation_state("idle")
            return

        translation, is_live_translated = self._get_translation(
            self._current_prg_file,
            self._current_job.name,
            self._current_comments_de,
            self._lang,
        )

        if self._lang == "de":
            self.job_comment_label.setText(self._current_comments_de)
            self.job_comment_label.setToolTip("")
            self._set_translation_state("ok")
            return

        if translation != self._current_comments_de:
            self._set_translation_text(
                translation,
                is_live_translated=False,
                tooltip="",
            )
            return

        self._set_translation_text(
            self._current_comments_de,
            is_live_translated=False,
            tooltip="",
        )

    def _translation_key(self, prg_file: str, job_name: str, lang: str) -> tuple[str, str, str]:
        return ((prg_file or "").upper(), job_name or "", (lang or "de").lower())

    def _set_translation_text(
        self,
        text_de: str,
        is_live_translated: bool,
        fallback_missing: bool = False,
        tooltip: str = "",
    ):
        safe_text = str(text_de or "")
        rendered_text = html_escape(safe_text).replace("\n", "<br/>")
        if fallback_missing:
            html_text = (
                f"<span>{rendered_text}</span> "
                f"<span style='color:#808080; font-size: 9px;'>⚠️ brak tłumaczenia</span>"
            )
            self.job_comment_label.setText(html_text)
            self.job_comment_label.setToolTip(
                tooltip or "Brak tłumaczenia w bazie i brak połączenia z internetem"
            )
            self._set_translation_state("ok")
            return

        if is_live_translated:
            html_text = (
                f"<span>{rendered_text}</span> "
                f"<span style='color:#808080; font-size: 9px;'>🌐 (auto)</span>"
            )
            self.job_comment_label.setText(html_text)
            self.job_comment_label.setToolTip(
                tooltip or "Tłumaczenie automatyczne — zapisano do bazy danych"
            )
        else:
            self.job_comment_label.setText(safe_text)
            self.job_comment_label.setToolTip(tooltip)
        self._set_translation_state("ok")

    def _start_translation_worker(self, prg_file: str, job_name: str, text_de: str, lang: str):
        key = self._translation_key(prg_file, job_name, lang)
        if key in self._translation_pending:
            return

        worker = TranslationWorker(prg_file, job_name, text_de, lang, self)
        worker.translationFinished.connect(self._on_translation_finished)
        worker.finished.connect(worker.deleteLater)
        self._translation_pending.add(key)
        self._translation_workers.append(worker)
        worker.start()

    def _on_translation_finished(self, prg_file: str, job_name: str, lang: str, translated_text: str, original_de: str):
        key = self._translation_key(prg_file, job_name, lang)
        self._translation_pending.discard(key)
        self._translation_workers = [worker for worker in self._translation_workers if worker.isRunning()]

        if translated_text and self._db:
            try:
                if lang == "en":
                    self._db.save_translation(prg_file, job_name, comment_de=original_de, comment_en=translated_text)
                elif lang == "pl":
                    self._db.save_translation(prg_file, job_name, comment_de=original_de, comment_pl=translated_text)
            except Exception:
                pass

        if not translated_text:
            if (
                self._current_prg_file == (prg_file or "").upper()
                and self._current_job
                and self._current_job.name == job_name
                and self._lang == (lang or "de").lower()
                and self._current_comments_de == original_de
            ):
                self._set_translation_text(
                    original_de,
                    is_live_translated=False,
                    fallback_missing=True,
                )
            return

        if (
            self._current_prg_file == (prg_file or "").upper()
            and self._current_job
            and self._current_job.name == job_name
            and self._lang == (lang or "de").lower()
            and self._current_comments_de == original_de
        ):
            self._set_translation_text(
                translated_text,
                is_live_translated=True,
                tooltip="Tłumaczenie automatyczne — zapisano do bazy danych",
            )

    def _get_translation(self, prg_file: str, job_name: str, text_de: str, lang: str) -> tuple[str, bool]:
        lang = (lang or "de").lower()
        if lang == "de" or not text_de:
            return text_de, False

        cached = None
        if self._db:
            cached = self._db.get_translation(prg_file, job_name, lang)
        if cached:
            return cached, False

        self._start_translation_worker(prg_file, job_name, text_de, lang)
        return text_de, False

    def _parse_job_comments(self, comments: list[str]) -> tuple[str, list[tuple[str, str, str]], list[tuple[str, str, str]]]:
        job_comment = ""
        results: list[tuple[str, str, str]] = []
        args: list[tuple[str, str, str]] = []
        current_result = ""
        current_type = ""
        current_comment = ""
        current_arg = ""
        current_arg_type = ""
        current_arg_comments: list[str] = []

        def flush_result():
            nonlocal current_result, current_type, current_comment
            if current_result:
                results.append((current_result, current_type, current_comment))
            current_result = ""
            current_type = ""
            current_comment = ""

        def flush_arg():
            nonlocal current_arg, current_arg_type, current_arg_comments
            if current_arg:
                args.append((current_arg, current_arg_type, " | ".join(comment for comment in current_arg_comments if comment)))
            current_arg = ""
            current_arg_type = ""
            current_arg_comments = []

        for entry in comments:
            line = entry.strip()
            upper = line.upper()
            if upper.startswith("JOBCOMMENT:"):
                job_comment = line.split(":", 1)[1].strip()
            elif upper.startswith("ARG:"):
                flush_arg()
                flush_result()
                current_arg = line.split(":", 1)[1].strip()
            elif upper.startswith("ARGTYPE:"):
                current_arg_type = line.split(":", 1)[1].strip()
            elif upper.startswith("ARGCOMMENT:"):
                current_arg_comments.append(line.split(":", 1)[1].strip())
            elif upper.startswith("RESULT:"):
                flush_arg()
                flush_result()
                current_result = line.split(":", 1)[1].strip()
            elif upper.startswith("RESULTTYPE:"):
                current_type = line.split(":", 1)[1].strip()
            elif upper.startswith("RESULTCOMMENT:"):
                current_comment = line.split(":", 1)[1].strip()

        flush_arg()
        flush_result()
        return job_comment, results, args

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

    def _load_params(self, job: "Job", tables: list["Table"], db: "Database | None" = None):
        while self.params_sub_tabs.count():
            page = self.params_sub_tabs.widget(0)
            self.params_sub_tabs.removeTab(0)
            if page is not None:
                page.deleteLater()
        self.params_tree = None

        def build_generic_table_tab(table: "Table") -> QWidget:
            page = QWidget()
            layout = QVBoxLayout(page)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(4)

            filter_row = QHBoxLayout()
            filter_row.addWidget(QLabel("Filtr:"))
            filter_edit = QLineEdit()
            filter_edit.setPlaceholderText("Szukaj po wartościach tabeli...")
            filter_row.addWidget(filter_edit)
            layout.addLayout(filter_row)

            table_widget = QTableWidget()
            table_widget.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
            table_widget.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
            table_widget.setAlternatingRowColors(False)
            table_widget.horizontalHeader().setSectionResizeMode(
                QHeaderView.ResizeMode.ResizeToContents
            )
            table_widget.horizontalHeader().setStretchLastSection(True)
            layout.addWidget(table_widget)

            columns = list(getattr(table, "columns", []) or [])
            rows = list(getattr(table, "rows", []) or [])
            row_values = [[str(value) for value in getattr(row, "values", [])] for row in rows]

            table_widget.setColumnCount(len(columns))
            table_widget.setHorizontalHeaderLabels(columns)

            def apply_filter():
                query = filter_edit.text().strip().upper()
                visible_rows = []
                for values in row_values:
                    haystack = " ".join(values).upper()
                    if query and query not in haystack:
                        continue
                    visible_rows.append(values)

                table_widget.setRowCount(len(visible_rows))
                for row_index, values in enumerate(visible_rows):
                    for col_index in range(len(columns)):
                        cell_text = values[col_index] if col_index < len(values) else ""
                        table_widget.setItem(row_index, col_index, QTableWidgetItem(cell_text))

                table_widget.resizeColumnsToContents()

            filter_edit.textChanged.connect(lambda _text: apply_filter())
            apply_filter()
            return page

        def build_betriebs_tab(table: "Table") -> QWidget:
            page = QWidget()
            layout = QVBoxLayout(page)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(4)

            tree = QTreeWidget()
            tree.setHeaderLabels([
                "Nazwa", "Bajt", "Typ", "Jedn.", "FACT_A", "FACT_B", "Telegram DS2"
            ])
            tree.header().setSectionResizeMode(
                QHeaderView.ResizeMode.ResizeToContents
            )
            layout.addWidget(tree)

            cols = [c.upper() for c in table.columns]

            def col(name):
                try:
                    return cols.index(name.upper())
                except ValueError:
                    return -1

            idx_name = col("NAME")
            if idx_name == -1:
                layout.removeWidget(tree)
                tree.deleteLater()
                self.params_tree = None
                return build_generic_table_tab(table)

            self.params_tree = tree

            idx_tel = col("TELEGRAM")
            idx_byte = col("BYTE")
            idx_dtype = col("DATA_TYPE")
            idx_meas = col("MEAS")
            idx_facta = col("FACT_A")
            idx_factb = col("FACT_B")

            def get_val(row, idx):
                if idx == -1 or idx >= len(row.values):
                    return "—"
                return row.values[idx].strip()

            param_names = self._extract_param_names_from_disassembly(job.disassembly)

            if not param_names:
                item = QTreeWidgetItem(
                    ["Brak danych live data — job zwraca status tekstowy lub wykonuje akcję", "", "", "", "", "", ""]
                )
                tree.addTopLevelItem(item)
                return page

            found = False
            for row in table.rows:
                row_name = get_val(row, idx_name).upper().strip()
                if row_name not in param_names:
                    continue
                found = True
                name = get_val(row, idx_name)
                byte_ = get_val(row, idx_byte)
                dtype = get_val(row, idx_dtype)
                meas = get_val(row, idx_meas)
                facta = get_val(row, idx_facta)
                factb = get_val(row, idx_factb)
                raw_tel = get_val(row, idx_tel).upper().replace(" ", "")
                tel_fmt = self._format_telegram(raw_tel)
                item = QTreeWidgetItem([name, byte_, dtype, meas, facta, factb, tel_fmt])
                tree.addTopLevelItem(item)

            if not found:
                item = QTreeWidgetItem(
                    ["Brak danych live data — job zwraca status tekstowy lub wykonuje akcję", "", "", "", "", "", ""]
                )
                tree.addTopLevelItem(item)

            return page

        if not tables:
            placeholder = QWidget()
            self.params_sub_tabs.addTab(placeholder, "Plik .prg nie zawiera tabel")
            self.params_sub_tabs.setTabEnabled(0, False)
            return

        tables_sorted = sorted(
            tables,
            key=lambda table: 0 if self._table_used_in_job(table.name, job.disassembly) else 1,
        )

        for table in tables_sorted:
            used = self._table_used_in_job(table.name, job.disassembly)
            tab_title = f"{'🟢' if used else '🔴'} {table.name}"
            if "BETRIEBSWTAB" in table.name.upper() and used:
                page = build_betriebs_tab(table)
            else:
                page = build_generic_table_tab(table)
            self.params_sub_tabs.addTab(page, tab_title)
            if db is not None:
                desc = db.get_table_description(table.name)
            else:
                desc = None

            if desc:
                name_en, description_en = desc
                tooltip = f"<b>{name_en}</b><br>{description_en}"
            else:
                tooltip = "No description available for this table."
            tab_index = self.params_sub_tabs.count() - 1
            self.params_sub_tabs.setTabToolTip(tab_index, tooltip)
            self.params_sub_tabs.tabBar().setTabToolTip(tab_index, tooltip)

        if self.params_sub_tabs.count() > 0:
            self.params_sub_tabs.setCurrentIndex(0)

    def _table_used_in_job(self, table_name: str, disassembly: list[str]) -> bool:
        needle = (table_name or "").lower()
        if not needle:
            return False

        for line in disassembly:
            lower_line = line.lower()
            if ("tabset" in lower_line or "tabseek" in lower_line) and needle in lower_line:
                return True

        return False

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
        self.args_table.setRowCount(0)
        self.args_table.hide()
        self.args_label.hide()
        self.results_table.setRowCount(0)
        self._set_translation_state("idle")
        if self.params_tree is not None:
            self.params_tree.clear()
        while self.params_sub_tabs.count():
            page = self.params_sub_tabs.widget(0)
            self.params_sub_tabs.removeTab(0)
            if page is not None:
                page.deleteLater()
        self.params_tree = None
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
        self._parser = None
        self._current_entry: dict | None = None
        self._current_model_name: str = ""
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
        self._current_model_name = ""
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
        self._current_model_name = ""

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
            model_item.setData(0, Qt.ItemDataRole.UserRole, {"kind": "model", "model": model_name})
            self.models_tree.addTopLevelItem(model_item)
            model_item.setExpanded(False)

    def _on_tree_item_changed(self, current, previous):
        entry = None
        if current:
            data = current.data(0, Qt.ItemDataRole.UserRole)
            if isinstance(data, dict):
                kind = data.get("kind")
                if kind == "model":
                    self._current_model_name = data.get("model", "")
                    self._populate_model_children(current, self._current_model_name)
                elif kind == "entry":
                    entry = data
        self._current_entry = entry
        self._update_details()

    def _populate_model_children(self, model_item: QTreeWidgetItem, model_name: str):
        if model_item.childCount() > 0:
            return

        model_bucket = self._models_data.get(model_name, {})
        for category in ["Silnik", "Skrzynia", "Podwozie", "Karoseria", "Komunikacja"]:
            entries = model_bucket.get(category, [])
            if not entries:
                continue

            category_item = QTreeWidgetItem([category])
            category_item.setData(0, Qt.ItemDataRole.UserRole, {"kind": "category", "model": model_name, "category": category})
            model_item.addChild(category_item)

            for entry in entries:
                entry_data = {
                    "kind": "entry",
                    "model": model_name,
                    "category": category,
                    "description": entry.get("description", ""),
                    "script": entry.get("script", ""),
                    "prg_files": list(entry.get("prg_files", []) or []),
                }
                entry_item = QTreeWidgetItem([entry_data["description"]])
                entry_item.setData(0, Qt.ItemDataRole.UserRole, entry_data)
                category_item.addChild(entry_item)

            category_item.setExpanded(True)

        model_item.setExpanded(True)

    def _update_details(self):
        if not self._current_entry:
            if self._current_model_name:
                self.description_label.setText("Wybierz ECU z rozwiniętej listy po lewej.")
            else:
                self.description_label.setText("Najpierw wybierz model po lewej.")
            self.script_label.setText("Skrypt INPA: —")
            self.prg_list_widget.clear()
            self.prg_status_label.setText("—")
            self.open_prg_btn.setEnabled(False)
            return

        description = self._current_entry.get("description") or "—"
        script_name = self._current_entry.get("script") or ""
        prg_files = list(self._current_entry.get("prg_files") or [])

        if not prg_files and self._parser and script_name:
            prg_files = list(self._parser.get_prg_for_script(script_name) or [])
            self._current_entry["prg_files"] = prg_files

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

    def set_parser(self, parser):
        self._parser = parser

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
        self._sa_config = self._load_sa_config()

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
        QTimer.singleShot(0, self._run_startup_guard)

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

    def _load_sa_config(self) -> dict:
        config_path = Path(__file__).resolve().parent / "data" / "ncs_coding_paths.json"
        defaults = {
            "daten": r"C:\NCSEXPER\DATEN",
            "work": r"C:\NCSEXPER\WORK",
        }

        if not config_path.exists():
            return defaults

        try:
            payload = json.loads(config_path.read_text(encoding="utf-8"))
            daten_path = str(payload.get("daten_path") or defaults["daten"]).strip() or defaults["daten"]
            trc_path = str(payload.get("trc_path") or "").strip()
            work_path = str(Path(trc_path).parent) if trc_path else defaults["work"]
            return {
                "daten": daten_path,
                "work": work_path,
            }
        except Exception:
            return defaults

    def _set_app_icon(self):
        icon_path = Path(__file__).resolve().parent / "bimmerdatenlogo.ico"
        if icon_path.exists():
            icon = QIcon(str(icon_path))
            self.setWindowIcon(icon)

    def _resolve_startup_paths(self) -> dict:
        config_path = Path(__file__).resolve().parent / "data" / "ncs_coding_paths.json"
        defaults = {
            "daten_path": r"C:\NCSEXPER\DATEN",
            "trc_path": r"C:\NCSEXPER\WORK\FSW_PSW.TRC",
            "translations_path": r"C:\NCS Dummy\Translations.csv",
            "work_path": r"C:\NCSEXPER\WORK",
        }

        if not config_path.exists():
            return defaults

        try:
            payload = json.loads(config_path.read_text(encoding="utf-8"))
        except Exception:
            return defaults

        daten_path = str(payload.get("daten_path") or defaults["daten_path"]).strip() or defaults["daten_path"]
        trc_path = str(payload.get("trc_path") or defaults["trc_path"]).strip() or defaults["trc_path"]
        translations_path = (
            str(payload.get("translations_path") or defaults["translations_path"]).strip()
            or defaults["translations_path"]
        )
        work_path = str(Path(trc_path).parent) if trc_path else defaults["work_path"]

        return {
            "daten_path": daten_path,
            "trc_path": trc_path,
            "translations_path": translations_path,
            "work_path": work_path,
        }

    def _build_startup_report(self) -> tuple[str, bool]:
        paths = self._resolve_startup_paths()
        required_checks = [
            ("DATEN folder", paths["daten_path"]),
            ("TRC file", paths["trc_path"]),
            ("Translations.csv", paths["translations_path"]),
            ("WORK folder", paths["work_path"]),
        ]
        optional_checks = [
            ("INPA folder", self._inpa_path),
            ("EDIABAS ECU folder", self._ecu_path),
            ("Database file", str(Path(__file__).resolve().parent / "data" / "database.db")),
        ]

        lines: list[str] = []
        lines.append("BimmerDaten startup report")
        lines.append("")
        lines.append("Required for full coding flow:")

        missing_required: list[str] = []
        for label, raw_path in required_checks:
            target = (raw_path or "").strip()
            exists = bool(target) and Path(target).exists()
            status = "OK" if exists else "MISSING"
            lines.append(f"- [{status}] {label}: {target or 'not set'}")
            if not exists:
                missing_required.append(label)

        lines.append("")
        lines.append("Optional / feature-specific:")
        for label, raw_path in optional_checks:
            target = (raw_path or "").strip()
            exists = bool(target) and Path(target).exists()
            status = "OK" if exists else "MISSING"
            lines.append(f"- [{status}] {label}: {target or 'not set'}")

        lines.append("")
        lines.append("Python modules:")
        lines.append(f"- [{'OK' if DECODER_AVAILABLE else 'MISSING'}] decoderPrg")
        lines.append(f"- [{'OK' if DB_AVAILABLE else 'MISSING'}] database")
        lines.append(f"- [{'OK' if CODING_AVAILABLE else 'MISSING'}] trc_coding")
        lines.append(f"- [{'OK' if SA_OPTIONS_AVAILABLE else 'MISSING'}] sa_options_widget")

        report_text = "\n".join(lines)
        return report_text, bool(missing_required)

    def _show_startup_report(self, force_show: bool = False):
        report_text, has_missing_required = self._build_startup_report()

        if not force_show and not has_missing_required:
            return

        dialog = QMessageBox(self)
        dialog.setWindowTitle("Startup Guard")
        dialog.setIcon(QMessageBox.Icon.Warning if has_missing_required else QMessageBox.Icon.Information)
        if has_missing_required:
            dialog.setText("Wykryto brak wymaganych plików/ścieżek dla pełnego trybu kodowania.")
            dialog.setInformativeText("Uzupełnij ścieżki w konfiguracji, aby odblokować wszystkie funkcje.")
        else:
            dialog.setText("Wszystkie wymagane ścieżki są dostępne.")
            dialog.setInformativeText("Raport środowiska poniżej.")
        dialog.setDetailedText(report_text)
        dialog.setStandardButtons(QMessageBox.StandardButton.Ok)
        dialog.exec()

    def _run_startup_guard(self):
        _report_text, has_missing_required = self._build_startup_report()
        if has_missing_required:
            self.status_bar.showMessage("Startup Guard: brakuje części wymaganych plików/ścieżek (szczegóły w raporcie).")
            self._show_startup_report(force_show=True)
            return

        self.status_bar.showMessage("Startup Guard: wymagane pliki/ścieżki OK.")

    def _setup_ui(self):
        self.setWindowTitle("BimmerDaten - Expert for EDIABAS and NCS")
        self.setMinimumSize(900, 600)
        self.resize(1100, 700)

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        welcome_bar = QWidget()
        welcome_bar.setStyleSheet("background-color: #000080; border-bottom: 1px solid #808080;")
        welcome_layout = QHBoxLayout(welcome_bar)
        welcome_layout.setContentsMargins(8, 4, 8, 4)
        welcome_layout.setSpacing(8)

        logo_label = QLabel()
        logo_path = Path(__file__).resolve().parent / "bimmerdatenlogo.ico"
        logo_pixmap = QPixmap(str(logo_path)) if logo_path.exists() else QPixmap()
        if not logo_pixmap.isNull():
            logo_label.setPixmap(
                logo_pixmap.scaled(
                    24,
                    24,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
            logo_label.setFixedSize(24, 24)
        else:
            logo_label.setText("BD")
            logo_label.setStyleSheet(
                "color: #ffffff; font-weight: bold; border: 1px solid #ffffff; "
                "padding: 2px 6px; min-width: 24px;"
            )
            logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        welcome_layout.addWidget(logo_label)

        welcome_text = QLabel("Hello Bimmers | BimmerDaten - Expert for EDIABAS and NCS")
        welcome_text.setStyleSheet("color: #ffffff; font-weight: bold; font-size: 12px;")
        welcome_layout.addWidget(welcome_text, 1)

        main_layout.addWidget(welcome_bar)

        self.top_tabs = QTabWidget()
        self.top_tabs.tabBar().setStyleSheet(
            "QTabBar::tab { font-size: 13px; padding: 6px 16px; }"
        )
        main_layout.addWidget(self.top_tabs)

        diagnosis_tab = QWidget()
        diagnosis_layout = QVBoxLayout(diagnosis_tab)
        diagnosis_layout.setContentsMargins(0, 0, 0, 0)
        diagnosis_layout.setSpacing(0)

        self.main_tabs = QTabWidget()
        diagnosis_layout.addWidget(self.main_tabs)

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

        self.top_tabs.addTab(diagnosis_tab, "🔧 Diagnoza")

        if CODING_AVAILABLE:
            self.coding_panel = CodingPanel(self._db)
        else:
            self.coding_panel = QWidget()
            fallback_layout = QVBoxLayout(self.coding_panel)
            fallback_layout.addWidget(QLabel("Nie udało się załadować panelu kodowania."))

        self.top_tabs.addTab(self.coding_panel, "⚙️ Kodowanie")

        if SA_OPTIONS_AVAILABLE:
            self.sa_options_panel = SAOptionsWidget(self._db, self._sa_config, self)
        else:
            self.sa_options_panel = QWidget()
            sa_layout = QVBoxLayout(self.sa_options_panel)
            sa_layout.addWidget(QLabel("Nie udało się załadować zakładki Opcje SA."))

        self.top_tabs.addTab(self.sa_options_panel, "🔧 Opcje SA")

        if not self._inpa_path:
            self.models_panel.set_placeholder("Nie znaleziono instalacji INPA")
        else:
            self.models_panel.set_placeholder("Wybierz zakładkę Modele, aby wczytać parser INPA")

        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.clearMessage()

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
        report_action = QAction("Raport startup guard", self)
        report_action.triggered.connect(lambda: self._show_startup_report(force_show=True))
        help_menu.addAction(report_action)
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
            self.top_tabs.setCurrentIndex(0)
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
            self.models_panel.set_parser(parser)
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
        """Show About dialog with application information."""
        dialog = QDialog(self)
        dialog.setWindowTitle("O programie")
        dialog.setFixedSize(500, 550)
        dialog.setStyleSheet(WIN98_STYLE)
        
        layout = QVBoxLayout()
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)
        
        # App name (bold, large)
        app_name_label = QLabel("BimmerDaten")
        app_name_font = QFont("Tahoma", 16, QFont.Weight.Bold)
        app_name_label.setFont(app_name_font)
        layout.addWidget(app_name_label)
        
        # Version and author
        version_author = QLabel("<b>Wersja:</b> v0.2<br><b>Autor:</b> Filip Dzitko")
        layout.addWidget(version_author)
        
        # Description
        description_text = (
            "<b>Opis:</b><br>"
            "Narzędzie do pracy z BMW EDIABAS i NCS Expert. "
            "Pozwala przeglądać pliki .PRG, tabelki i joby, analizować oraz edytować kodowanie TRC, "
            "eksportować zmiany do .MAN i .TRC, przeglądać historię zapisów z bazy danych, "
            "generować raporty PDF oraz korzystać z tłumaczeń jobów i opcji w locie."
        )
        description_label = QLabel(description_text)
        description_label.setWordWrap(True)
        layout.addWidget(description_label)

        features_text = (
            "<b>Najważniejsze funkcje:</b><br>"
            "<ul style='margin-top: 6px; margin-bottom: 0;'>"
            "<li>kodowanie TRC z podglądem zmian i historią</li>"
            "<li>eksport .MAN / .TRC z kontrolą profilu NCS Expert</li>"
            "<li>dwujęzyczne tłumaczenia DE / EN / PL z zapisem do SQLite</li>"
            "<li>podgląd jobów, tabel i danych INPA / EDIABAS</li>"
            "<li>raporty PDF z metadanymi i listą zmian</li>"
            "</ul>"
        )
        features_label = QTextBrowser()
        features_label.setHtml(features_text)
        features_label.setMaximumHeight(160)
        features_label.setStyleSheet(
            "QTextBrowser { border: 1px inset #808080; "
            "background-color: #ffffff; padding: 6px; }"
        )
        layout.addWidget(features_label)
        
        # License
        license_text = (
            "<b>Licencja:</b> "
            '<a href="https://www.gnu.org/licenses/gpl-3.0.html" '
            'style="color: #0000ff; text-decoration: underline;">GPL-3.0</a>'
        )
        license_label = QTextBrowser()
        license_label.setHtml(license_text)
        license_label.setMaximumHeight(30)
        license_label.setOpenExternalLinks(True)
        license_label.setStyleSheet(
            "QTextBrowser { border: none; background-color: #d4d0c8; "
            "margin: 0; padding: 0; }"
        )
        layout.addWidget(license_label)
        
        # Credits section
        credits_text = (
            "<b>Zależności i źródła:</b><br>"
            "<ul style='margin-top: 6px; margin-bottom: 0;'>"
            "<li>deep-translator</li>"
            "<li>PyQt6</li>"
            "</ul>"
        )
        credits_label = QTextBrowser()
        credits_label.setHtml(credits_text)
        credits_label.setMaximumHeight(120)
        credits_label.setStyleSheet(
            "QTextBrowser { border: 1px inset #808080; "
            "background-color: #ffffff; padding: 6px; }"
        )
        layout.addWidget(credits_label)
        
        # Add stretch to push button to bottom
        layout.addStretch()
        
        # OK button
        ok_button = QPushButton("OK")
        ok_button.setMaximumWidth(80)
        ok_button.clicked.connect(dialog.accept)
        ok_layout = QHBoxLayout()
        ok_layout.addStretch()
        ok_layout.addWidget(ok_button)
        ok_layout.addStretch()
        layout.addLayout(ok_layout)
        
        dialog.setLayout(layout)
        dialog.exec()

    def closeEvent(self, event):
        man_path = Path(r"C:\NCSEXPER\WORK\FSW_PSW.MAN")
        if man_path.exists() and man_path.stat().st_size > 0:
            dialog = QMessageBox(self)
            dialog.setWindowTitle("Zamknąć program?")
            dialog.setText(
                "Plik FSW_PSW.MAN nie jest pusty.\n\n"
                "Dobra praktyka NCS Expert wymaga wyzerowania pliku po zakończeniu pracy.\n"
                "Czy chcesz wyczyścić FSW_PSW.MAN?"
            )
            clear_button = dialog.addButton("Tak — wyczyść", QMessageBox.ButtonRole.YesRole)
            no_button = dialog.addButton("Nie", QMessageBox.ButtonRole.NoRole)
            cancel_button = dialog.addButton("Anuluj zamykanie", QMessageBox.ButtonRole.RejectRole)
            dialog.exec()

            clicked_button = dialog.clickedButton()
            if clicked_button == cancel_button:
                event.ignore()
                return
            if clicked_button == clear_button:
                try:
                    with man_path.open("w", encoding="utf-8"):
                        pass
                except Exception as exc:
                    QMessageBox.critical(self, "Błąd", f"Nie udało się wyczyścić pliku:\n{exc}")
                    play_sound("error")
                    event.ignore()
                    return

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
    app.setStyle("Windows")  # styl Windows dla lepszego efektu retro
    icon_path = Path(__file__).resolve().parent / "bimmerdatenlogo.ico"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()