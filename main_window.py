import sys
import platform
import json
import os
import logging
from pathlib import Path
from html import escape as html_escape
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QSplitter,
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QListWidget, QListWidgetItem, QTreeWidget,
    QTreeWidgetItem, QFileDialog, QStatusBar, QMenuBar,
    QMenu, QGroupBox, QTextEdit, QComboBox, QFrame,
    QSizePolicy, QHeaderView, QTabWidget, QTabBar, QTableWidget,
    QTableWidgetItem, QDialog, QTextBrowser, QMessageBox, QToolButton,
    QProgressBar, QProgressDialog, QInputDialog
)
from PyQt6.QtCore import Qt, QSize, pyqtSignal, QThread, QTimer
from PyQt6.QtGui import QFont, QAction, QColor, QPalette, QIcon, QPixmap, QShowEvent

from app_logger import get_log_file_path, get_logs_dir_path, setup_logger


logger = logging.getLogger("bimmerdaten.main_window")

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
        logger.exception("Failed to play sound: %s", sound_type)


def _normalize_profile_name(raw_value: str) -> str:
    profile = (raw_value or "").strip().lower()
    if not profile or profile in {"prod", "production", "default", "release"}:
        return ""
    if profile in {"dev", "development"}:
        return "Dev"
    return ""


def get_runtime_profile() -> str:
    # CLI has priority, then environment variable.
    for arg in sys.argv[1:]:
        if arg.startswith("--profile="):
            return _normalize_profile_name(arg.split("=", 1)[1])
        if arg == "--dev":
            return "Dev"

    env_profile = os.environ.get("BIMMERDATEN_PROFILE", "")
    return _normalize_profile_name(env_profile)


def get_appdata_root(profile: str = "") -> Path:
    appdata = os.environ.get("LOCALAPPDATA")
    base = Path(appdata) if appdata else (Path.home() / "AppData" / "Local")
    suffix = f"-{profile}" if profile else ""
    return base / f"BimmerDaten{suffix}"


def get_runtime_db_path(profile: str = "") -> Path:
    return get_appdata_root(profile) / "database.db"


def get_runtime_paths_config_path(profile: str = "") -> Path:
    return get_appdata_root(profile) / "ncs_coding_paths.json"


def get_legacy_paths_config_path() -> Path:
    return Path(__file__).resolve().parent / "data" / "ncs_coding_paths.json"



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
            logger.exception("Translation worker failed for job '%s' (%s)", self.job_name, self.lang)
            self.translationFinished.emit(
                self.prg_file,
                self.job_name,
                self.lang,
                "",
                self.text_de,
            )


class UpdateCheckWorker(QThread):
    update_available = pyqtSignal(str)

    VERSION_URL = "https://raw.githubusercontent.com/zer02dev/BimmerDaten/main/seeds/version.txt"

    def __init__(self, local_version: str, parent=None):
        super().__init__(parent)
        self.local_version = local_version

    def _is_remote_newer(self, remote: str) -> bool:
        local = (self.local_version or "").strip()
        remote = (remote or "").strip()
        if not remote:
            return False

        # Prefer strict date compare for version.txt format: YYYY-MM-DD
        try:
            from datetime import datetime

            remote_date = datetime.strptime(remote, "%Y-%m-%d").date()
            local_date = datetime.strptime(local, "%Y-%m-%d").date()
            return remote_date > local_date
        except Exception:
            logger.exception("Failed to parse seed version dates: local=%s remote=%s", local, remote)

        # Fallback for semantic-ish versions and other formats.
        return remote > local

    def run(self):
        try:
            import urllib.request

            with urllib.request.urlopen(self.VERSION_URL, timeout=5) as resp:
                remote = resp.read().decode("utf-8").strip()
            if self._is_remote_newer(remote):
                self.update_available.emit(remote)
        except Exception:
            logger.exception("Seed update check failed")


# ---------------------------------------------------------------------------
# Kategorie jobów — na podstawie prefiksu nazwy

JOB_CATEGORIES = {
    "STATUS":    "📊 Status / Live Data",
    "STEUERN":   "⚙️ Control / Actuators",
    "FS":        "❌ Fault Memory / Errors",
    "LESEN":     "📖 Read / Readout",
    "SCHREIBEN": "✏️ Write / Coding",
    "START":     "▶️ Start / System Check",
    "ENDE":      "⏹️ End / Finish",
    "STOP":      "⏹️ Stop",
    "IDENT":     "🔍 Identification",
    "ADAP":      "🔄 Adaptations",
    "VARIANTE":  "🔧 Variant",
    "RAM":       "💾 RAM",
    "DATA":      "📁 Data",
    "C_":        "📡 C_ / Communication",
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
    "Errors": {
        "FEHLERCODES", "FORTTEXTE", "FARTTEXTE", "FARTTEXTEERWEITERT",
        "FUMWELTTEXTE", "FUMWELTMATRIX", "FARTTYP", "FARTTXT_ERW",
        "FDETAILSTRUKTUR",
    },
    "Status": {
        "VVTSTATUSBG2_2", "EWSSTART", "EWSEMPFANGSSTATUS", "SLSSTATUS",
        "TEVSTATUS", "STAGEDMTL", "STAGEDMTLFREEZE", "REGEL",
    },
    "Bits": {"BITS", "FASTABITS", "FGRBITS", "READINESSBITS"},
    "Communication": {
        "KONZEPT_TABELLE", "BAUDRATE", "DIAGMODE", "JOBRESULT",
        "JOBRESULTEXTENDED",
    },
}

TABLE_CATEGORY_COLORS = {
    "Errors": ("#8b0000", "#ffffff"),
    "Status": ("#1a5c1a", "#ffffff"),
    "Bits": ("#003580", "#ffffff"),
    "Communication": ("#4b0082", "#ffffff"),
    "Other": ("#2f4f4f", "#ffffff"),
}

TABLE_COLUMN_PRESETS = {
    "FEHLERCODES": [
        ("CODE", "Code"),
        ("FEHLERTEXT", "Error description"),
    ],
    "BITS": [
        ("NAME", "Name"),
        ("BYTE", "Byte"),
        ("MASK", "Mask"),
        ("VALUE", "Value"),
    ],
    "FASTABITS": [
        ("NAME", "Name"),
        ("BYTE", "Byte"),
        ("MASK", "Mask"),
        ("VALUE", "Value"),
    ],
    "FGRBITS": [
        ("NAME", "Name"),
        ("BYTE", "Byte"),
        ("MASK", "Mask"),
        ("VALUE", "Value"),
    ],
    "READINESSBITS": [
        ("NAME", "Name"),
        ("BYTE", "Byte"),
        ("MASK", "Mask"),
        ("VALUE", "Value"),
    ],
    "EWSSTART": [
        ("STATI", "Status"),
        ("TEXT", "Description"),
    ],
    "EWSEMPFANGSSTATUS": [
        ("STATI", "Status"),
        ("TEXT", "Description"),
    ],
}


def get_table_category(table_name: str) -> str:
    upper_name = table_name.upper()
    for category, names in TABLE_CATEGORIES.items():
        if upper_name in names:
            return category
    return "Other"


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

        # Filter by category
        cat_box = QGroupBox("Category")
        cat_layout = QVBoxLayout(cat_box)
        self.category_combo = QComboBox()
        self.category_combo.addItem("-- All --")
        for label in sorted(set(JOB_CATEGORIES.values())):
            self.category_combo.addItem(label)
        self.category_combo.addItem("🔩 Other")
        self.category_combo.currentTextChanged.connect(self._apply_filter)
        cat_layout.addWidget(self.category_combo)
        layout.addWidget(cat_box)

        # Search
        search_box = QGroupBox("Search")
        search_layout = QVBoxLayout(search_box)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Job name...")
        self.search_edit.textChanged.connect(self._apply_filter)
        search_layout.addWidget(self.search_edit)
        layout.addWidget(search_box)

        # Job list
        jobs_box = QGroupBox("Job list")
        jobs_layout = QVBoxLayout(jobs_box)
        self.job_count_label = QLabel("No file loaded")
        self.job_count_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        jobs_layout.addWidget(self.job_count_label)
        self.job_list = QListWidget()
        self.job_count_label.setText("No file loaded")
        jobs_layout.addWidget(self.job_list)
        layout.addWidget(jobs_box)

    def load_jobs(self, jobs: list[Job]):
        self._all_jobs = jobs
        self._apply_filter()
        self.job_count_label.setText(f"Jobs: {len(jobs)}")

    def _apply_filter(self):
        search = self.search_edit.text().strip().upper()
        category = self.category_combo.currentText()

        self.job_list.clear()
        for job in self._all_jobs:
            cat = get_category(job.name)
            if category != "-- All --" and cat != category:
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
                f"Shown: {count} / {len(self._all_jobs)}"
            )


# ---------------------------------------------------------------------------
# Panel prawy — szczegóły joba

class JobDetailPanel(QWidget):
    languageChanged = pyqtSignal(str)
    showAllTablesRequested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_job: Job | None = None
        self._current_tables: list[Table] = []
        self._current_prg_file: str = ""
        self._current_comments_de: str = "No comments."
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
        self.title_label = QLabel("JOB DETAILS")
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

        self.job_addr_label = QLabel("Address: —")
        info_layout.addWidget(self.job_addr_label)

        self.job_category_label = QLabel("Category: —")
        info_layout.addWidget(self.job_category_label)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setObjectName("separator")
        info_layout.addWidget(sep)

        self.comment_box = QGroupBox("Comments from .prg file")
        comment_layout = QVBoxLayout(self.comment_box)

        comment_header = QHBoxLayout()
        comment_header.addWidget(QLabel("Language:"))
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

        self.args_label = QLabel("Arguments (input):")
        self.args_label.setStyleSheet(
            "font-size: 9px; color: #555555; font-weight: bold;"
        )
        comment_layout.addWidget(self.args_label)

        self.args_table = QTableWidget()
        self.args_table.setColumnCount(3)
        self.args_table.setHorizontalHeaderLabels(["Argument", "Type", "Description"])
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

        self.results_label = QLabel("Results (output):")
        self.results_label.setStyleSheet(
            "font-size: 9px; color: #555555; font-weight: bold;"
        )
        comment_layout.addWidget(self.results_label)

        self.results_table = QTableWidget()
        self.results_table.setColumnCount(3)
        self.results_table.setHorizontalHeaderLabels(["Result", "Type", "Description"])
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
        self.tabs.addTab(info_widget, "ℹ️ General")

        # --- Zakładka: Parametry (BETRIEBSWTAB) ---
        params_widget = QWidget()
        params_layout = QVBoxLayout(params_widget)

        self.params_tree = None
        self.params_sub_tabs = QTabWidget()
        self.params_sub_tabs.setTabPosition(QTabWidget.TabPosition.North)
        params_layout.addWidget(self.params_sub_tabs)

        tables_info_row = QHBoxLayout()
        tables_info_row.setContentsMargins(0, 4, 0, 0)
        tables_info_row.setSpacing(8)

        self._tables_info_label = QLabel("Tables used by this job")
        self._tables_info_label.setStyleSheet(
            "font-size: 10px; color: #666666; font-style: italic;"
        )
        self._tables_info_label.setVisible(False)

        self._show_all_tables_btn = QPushButton("📋 Show all tables")
        self._show_all_tables_btn.clicked.connect(self.showAllTablesRequested.emit)
        self._show_all_tables_btn.setVisible(False)

        tables_info_row.addWidget(self._tables_info_label)
        tables_info_row.addStretch()
        tables_info_row.addWidget(self._show_all_tables_btn)
        params_layout.addLayout(tables_info_row)

        self.tabs.addTab(params_widget, "📊 Parameters")

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
        self.job_addr_label.setText(f"Address in file: 0x{job.address:08X}")
        self.job_category_label.setText(f"Category: {get_category(job.name)}")

        # Komentarze
        comments = [c for c in job.comments if not c.startswith("JOBNAME:")]
        job_comment, result_rows, arg_rows = self._parse_job_comments(comments)
        self._current_comments_de = job_comment or "No comments."
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
            else "; No disassembly"
        )

        self._tables_info_label.setVisible(True)
        self._show_all_tables_btn.setVisible(True)

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
                f"<span style='color:#808080; font-size: 9px;'>⚠️ no translation</span>"
            )
            self.job_comment_label.setText(html_text)
            self.job_comment_label.setToolTip(
                tooltip or "No translation in the database and no internet connection"
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
                tooltip or "Automatic translation - saved to the database"
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
                logger.exception("Failed to save translated job comment: %s/%s", prg_file, job_name)

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
                tooltip="Automatic translation - saved to the database",
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
            self.comment_box.setTitle("Comments from .prg file - NO TRANSLATION")
            self.job_comment_label.setStyleSheet(
                "background-color: #ffe4e4;"
                "border: 1px solid #8b0000;"
                "color: #8b0000;"
                "font-weight: bold;"
                "padding: 4px;"
            )
            return

        self.comment_box.setTitle("Comments from .prg file")
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

        def _show_table_desc_popup(table_name: str, desc: tuple[str, str] | None):
            dlg = QDialog(self)
            dlg.setWindowTitle(f"Table: {table_name}")
            dlg.setMinimumWidth(420)
            dlg.setWindowFlags(dlg.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

            layout = QVBoxLayout(dlg)
            layout.setContentsMargins(0, 0, 0, 12)
            layout.setSpacing(0)

            header = QLabel(f"  {table_name}")
            header.setStyleSheet(
                "background-color: #1a3a5c; color: white;"
                "font-family: 'Tahoma'; font-size: 12px; font-weight: bold;"
                "padding: 8px 10px;"
            )
            layout.addWidget(header)

            content_layout = QVBoxLayout()
            content_layout.setContentsMargins(14, 12, 14, 0)
            content_layout.setSpacing(6)

            if desc:
                name_label = QLabel(desc[0])
                name_label.setStyleSheet("font-weight: bold; font-size: 11px; color: #1a3a5c;")
                name_label.setWordWrap(True)
                content_layout.addWidget(name_label)

                desc_label = QLabel(desc[1])
                desc_label.setWordWrap(True)
                desc_label.setStyleSheet("font-size: 10px; color: #333;")
                content_layout.addWidget(desc_label)
            else:
                no_data = QLabel("No description available for this table.")
                no_data.setStyleSheet("font-size: 10px; color: #888; font-style: italic;")
                content_layout.addWidget(no_data)

            layout.addLayout(content_layout)

            ok_btn = QPushButton("OK")
            ok_btn.setFixedWidth(80)
            ok_btn.clicked.connect(dlg.accept)
            btn_row = QHBoxLayout()
            btn_row.addStretch()
            btn_row.addWidget(ok_btn)
            btn_row.setContentsMargins(0, 8, 14, 0)
            layout.addLayout(btn_row)

            dlg.exec()

        def _add_title_row(layout: QVBoxLayout, table_name: str):
            title_row = QHBoxLayout()
            title_row.setContentsMargins(0, 0, 0, 0)
            title_row.setSpacing(0)

            title_label = QLabel(table_name)
            title_label.setStyleSheet(
                "font-size: 9px; color: #555555; font-weight: bold;"
            )
            title_row.addWidget(title_label)
            layout.addLayout(title_row)

        def build_generic_table_tab(table: "Table") -> QWidget:
            page = QWidget()
            layout = QVBoxLayout(page)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(4)

            _add_title_row(layout, table.name)

            filter_row = QHBoxLayout()
            filter_row.addWidget(QLabel("Filtr:"))
            filter_edit = QLineEdit()
            filter_edit.setPlaceholderText("Search table values...")
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

            _add_title_row(layout, table.name)

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
                    ["No live data parameters - this job returns a textual status or performs an action", "", "", "", "", "", ""]
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
                    ["No live data parameters - this job returns a textual status or performs an action", "", "", "", "", "", ""]
                )
                tree.addTopLevelItem(item)

            return page

        if not tables:
            placeholder = QWidget()
            self.params_sub_tabs.addTab(placeholder, "The .prg file contains no tables")
            self.params_sub_tabs.setTabEnabled(0, False)
            return

        used_tables = [
            t for t in tables
            if self._table_used_in_job(t.name, job.disassembly)
        ]
        used_tables.sort(key=lambda t: t.name)

        if not used_tables:
            placeholder = QWidget()
            placeholder_layout = QVBoxLayout(placeholder)
            placeholder_layout.addWidget(QLabel("This job does not use any tables"))
            self.params_sub_tabs.addTab(placeholder, "This job does not use any tables")
            self.params_sub_tabs.setTabEnabled(0, False)
            return

        for table in used_tables:
            tab_title = table.name
            if "BETRIEBSWTAB" in table.name.upper():
                page = build_betriebs_tab(table)
            else:
                page = build_generic_table_tab(table)
            self.params_sub_tabs.addTab(page, tab_title)
            tab_index = self.params_sub_tabs.count() - 1
            tooltip_html = "Click ? for table description."
            self.params_sub_tabs.setTabToolTip(tab_index, tooltip_html)
            self.params_sub_tabs.tabBar().setTabToolTip(tab_index, tooltip_html)

        for tab_index, table in enumerate(used_tables):
            button = QToolButton()
            button.setText("?")
            button.setFixedSize(QSize(16, 16))
            button.setStyleSheet(
                "QToolButton {"
                "  font-size: 9px; font-weight: bold;"
                "  border: 1px solid #888; border-radius: 8px;"
                "  background: #ddd; color: #333;"
                "  padding: 0px;"
                "}"
                "QToolButton:hover { background: #bbb; }"
            )
            button.setToolTip("Click ? for table description.")

            def make_handler(tname: str, db_ref: "Database | None"):
                def handler():
                    desc = db_ref.get_table_description(tname) if db_ref else None
                    _show_table_desc_popup(tname, desc)

                return handler

            button.clicked.connect(make_handler(table.name, self._db))
            self.params_sub_tabs.tabBar().setTabButton(
                tab_index, QTabBar.ButtonPosition.RightSide, button
            )

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
            logger.exception("Failed to format telegram hex")
            return raw_hex

    def clear(self):
        self._current_job = None
        self._current_tables = []
        self._current_prg_file = ""
        self._current_comments_de = "No comments."
        self.title_label.setText("JOB DETAILS")
        self.job_name_label.setText("—")
        self.job_addr_label.setText("Address: —")
        self.job_category_label.setText("Category: —")
        self.job_comment_label.setText("Description: —")
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
        self._tables_info_label.setVisible(False)
        self._show_all_tables_btn.setVisible(False)


# ---------------------------------------------------------------------------
# Panel tabel

class TablesPanel(QWidget):

    def __init__(self, db=None, parent=None):
        super().__init__(parent)
        self._db = db
        self._tables: list[Table] = []
        self._current_table: Table | None = None
        self._setup_ui()

    def set_db(self, db) -> None:
        self._db = db

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        left_box = QGroupBox("Tables from .prg file")
        left_layout = QVBoxLayout(left_box)

        table_search_row = QHBoxLayout()
        table_search_row.addWidget(QLabel("Table:"))
        self.table_search_edit = QLineEdit()
        self.table_search_edit.setPlaceholderText("Search by table name...")
        self.table_search_edit.textChanged.connect(self._apply_table_name_filter)
        table_search_row.addWidget(self.table_search_edit)
        left_layout.addLayout(table_search_row)

        self.tables_count_label = QLabel("No file loaded")
        self.tables_count_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        left_layout.addWidget(self.tables_count_label)

        self.tables_tree = QTreeWidget()
        self.tables_tree.setHeaderHidden(True)
        self.tables_tree.currentItemChanged.connect(self._on_table_selected)
        left_layout.addWidget(self.tables_tree)

        right_box = QGroupBox("Table preview")
        right_layout = QVBoxLayout(right_box)

        title_row = QHBoxLayout()
        self._selected_table_label = QLabel("")
        title_row.addWidget(self._selected_table_label, 1)
        
        self._desc_btn = QPushButton("?")
        self._desc_btn.setFixedWidth(24)
        self._desc_btn.setEnabled(False)
        self._desc_btn.setStyleSheet(
            "QPushButton { font-size: 9px; font-weight: bold;"
            "  border: 1px solid #888; border-radius: 8px;"
            "  background: #ddd; color: #333; padding: 0px; }"
            "QPushButton:hover { background: #bbb; }"
        )
        self._desc_btn.setToolTip("Click for table description")
        self._desc_btn.clicked.connect(self._on_desc_btn_clicked)
        title_row.addWidget(self._desc_btn)
        right_layout.addLayout(title_row)

        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Filter:"))
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("Search table rows...")
        self.filter_edit.textChanged.connect(self._apply_filter)
        filter_row.addWidget(self.filter_edit)
        right_layout.addLayout(filter_row)

        self.row_count_label = QLabel("Select a table from the list on the left.")
        self.row_count_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        right_layout.addWidget(self.row_count_label)

        self.table_widget = QTableWidget()
        self.table_widget.setAlternatingRowColors(False)
        right_layout.addWidget(self.table_widget)

        layout.addWidget(left_box, 1)
        layout.addWidget(right_box, 3)

    def _show_desc_popup(self, table_name: str) -> None:
        desc = self._db.get_table_description(table_name) if self._db else None
        dlg = QDialog(self)
        dlg.setWindowTitle(f"Table: {table_name}")
        dlg.setMinimumWidth(420)
        dlg.setWindowFlags(
            dlg.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint
        )
        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(0, 0, 0, 12)
        layout.setSpacing(0)

        header = QLabel(f"  {table_name}")
        header.setObjectName("title_label")
        header.setStyleSheet(
            "background-color: #1a3a5c; color: white;"
            "font-family: 'Tahoma'; font-size: 12px; font-weight: bold;"
            "padding: 8px 10px;"
        )
        layout.addWidget(header)

        content = QVBoxLayout()
        content.setContentsMargins(14, 12, 14, 0)
        content.setSpacing(6)

        if desc:
            name_lbl = QLabel(desc[0])
            name_lbl.setStyleSheet(
                "font-weight: bold; font-size: 11px; color: #1a3a5c;"
            )
            name_lbl.setWordWrap(True)
            content.addWidget(name_lbl)
            desc_lbl = QLabel(desc[1])
            desc_lbl.setWordWrap(True)
            desc_lbl.setStyleSheet("font-size: 10px; color: #333;")
            content.addWidget(desc_lbl)
        else:
            no_data = QLabel("No description available for this table.")
            no_data.setStyleSheet(
                "font-size: 10px; color: #888; font-style: italic;"
            )
            content.addWidget(no_data)

        layout.addLayout(content)

        ok_btn = QPushButton("OK")
        ok_btn.setFixedWidth(80)
        ok_btn.clicked.connect(dlg.accept)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(ok_btn)
        btn_row.setContentsMargins(0, 8, 14, 0)
        layout.addLayout(btn_row)
        dlg.exec()

    def load_tables(self, tables: list[Table]):
        self._tables = tables
        self._current_table = None
        self.tables_tree.clear()
        self.table_widget.clear()
        self.table_widget.setRowCount(0)
        self.table_widget.setColumnCount(0)
        self.filter_edit.clear()
        self.table_search_edit.clear()

        self.tables_count_label.setText(f"Tables: {len(tables)}")

        if not tables:
            self.row_count_label.setText("No tables in the file.")
            return

        top_items: dict[str, QTreeWidgetItem] = {}
        for category in ["Errors", "Status", "Bits", "Communication", "Other"]:
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

    def _on_desc_btn_clicked(self):
        if self._current_table:
            self._show_desc_popup(self._current_table.name)

    def _on_table_selected(self, current, previous):
        table = None
        if current:
            table = current.data(0, Qt.ItemDataRole.UserRole)
        self._current_table = table
        
        if table:
            self._selected_table_label.setText(f"Table: {table.name}")
            self._desc_btn.setEnabled(True)
        else:
            self._selected_table_label.setText("")
            self._desc_btn.setEnabled(False)
        
        self._apply_filter()

    def _apply_filter(self):
        if not self._current_table:
            self.row_count_label.setText("Select a table from the list on the left.")
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
            f"Rows: {len(visible_rows)} / {len(rows)}"
            if query else f"Rows: {len(rows)}"
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

        self.tables_count_label.setText(f"Tables: {visible_tables} / {len(self._tables)}")

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
        self.tables_count_label.setText("No file loaded")
        self.row_count_label.setText("Select a table from the list on the left.")
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

        left_box = QGroupBox("INPA Models")
        left_layout = QVBoxLayout(left_box)

        controls_row = QHBoxLayout()
        self.change_path_btn = QPushButton("Change INPA path")
        self.change_path_btn.clicked.connect(self.changeInpaPathRequested.emit)
        controls_row.addWidget(self.change_path_btn)
        controls_row.addStretch()
        left_layout.addLayout(controls_row)

        self.inpa_status_label = QLabel("INPA installation not found")
        self.inpa_status_label.setWordWrap(True)
        left_layout.addWidget(self.inpa_status_label)

        self.models_tree = QTreeWidget()
        self.models_tree.setHeaderHidden(True)
        self.models_tree.currentItemChanged.connect(self._on_tree_item_changed)
        left_layout.addWidget(self.models_tree)

        right_box = QGroupBox("ECU details")
        right_layout = QVBoxLayout(right_box)

        self.description_label = QLabel("—")
        self.description_label.setWordWrap(True)
        right_layout.addWidget(self.description_label)

        self.script_label = QLabel("INPA script: —")
        self.script_label.setWordWrap(True)
        right_layout.addWidget(self.script_label)

        self.prg_list_label = QLabel("Available PRG files:")
        right_layout.addWidget(self.prg_list_label)

        self.prg_list_widget = QListWidget()
        self.prg_list_widget.currentItemChanged.connect(self._on_prg_item_changed)
        right_layout.addWidget(self.prg_list_widget)

        self.prg_status_label = QLabel("—")
        self.prg_status_label.setWordWrap(True)
        right_layout.addWidget(self.prg_status_label)

        self.open_prg_btn = QPushButton("Open PRG file")
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
        self.script_label.setText("INPA script: —")
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
            f"INPA: {self._inpa_path}" if self._inpa_path else "INPA installation not found"
        )

        if not self._models_data:
            self.set_placeholder("No .ENG files found in CFGDAT")
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
                self.description_label.setText("Select an ECU from the expanded list on the left.")
            else:
                self.description_label.setText("Select a model on the left first.")
            self.script_label.setText("INPA script: —")
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
            item = QListWidgetItem("No PRG files detected")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.prg_list_widget.addItem(item)
            self.prg_status_label.setText("❌ No matches")
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
            self.prg_status_label.setText(f"✅ Found: {full_path}")
            self.open_prg_btn.setEnabled(True)
        else:
            ecu_folder = self._ecu_path or "EDIABAS\\Ecu"
            self.prg_status_label.setText(f"❌ Not found in {ecu_folder}")
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

        self.file_label  = QLabel("File: —")
        self.ver_label   = QLabel("BIP: —")
        self.rev_label   = QLabel("Rev: —")
        self.author_label = QLabel("Author: —")
        self.date_label  = QLabel("Date: —")

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
        self.file_label.setText(f"File: {name}")
        self.ver_label.setText(f"BIP: {prg.info.bip_version}")
        self.rev_label.setText(f"Rev: {prg.info.revision}")
        self.author_label.setText(f"Author: {prg.info.author[:30]}")
        self.date_label.setText(f"Date: {prg.info.last_changed[:24]}")


# ---------------------------------------------------------------------------
# Główne okno

class MainWindow(QMainWindow):

    def __init__(self):
        logger.info("MainWindow.__init__: start")
        super().__init__()
        self._prg: PrgFile | None = None
        self._filepath: str = ""
        self._lang: str = "de"
        self._db: Database | None = None
        logger.info("MainWindow.__init__: resolving runtime paths")
        self._runtime_profile: str = get_runtime_profile()
        self._db_path: Path = get_runtime_db_path(self._runtime_profile)
        self._inpa_path: str = self._detect_inpa_path() or ""
        self._ecu_path: str = self._detect_ecu_path() or ""
        logger.info("MainWindow.__init__: paths resolved (db=%s)", self._db_path)
        self._models_data: dict = {}
        self._models_loaded_for_path: str = ""
        self._models_parser_cls = None
        self._startup_guard_ran = False
        self._sa_config = self._load_sa_config()
        self._update_worker: UpdateCheckWorker | None = None

        if DB_AVAILABLE:
            logger.info("MainWindow.__init__: initializing database")
            try:
                self._db = Database(str(self._db_path))
            except Exception:
                logger.exception("MainWindow.__init__: database initialization failed")
                self._db = None
        else:
            logger.warning("MainWindow.__init__: database module unavailable")

        logger.info("MainWindow.__init__: setting app icon")
        self._set_app_icon()

        logger.info("MainWindow.__init__: UI setup")
        self._setup_ui()
        self._setup_menu()
        self._start_update_check()
        self.setStyleSheet(WIN98_STYLE)
        logger.info("MainWindow.__init__: startup guard will run after first showEvent")
        logger.info("MainWindow.__init__: done")

    def showEvent(self, event: QShowEvent):
        super().showEvent(event)
        if self._startup_guard_ran:
            return
        self._startup_guard_ran = True
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
        defaults = {
            "daten": r"C:\NCSEXPER\DATEN",
            "work": r"C:\NCSEXPER\WORK",
        }

        payload = self._load_paths_config_payload()
        if not payload:
            return defaults

        try:
            daten_path = str(payload.get("daten_path") or defaults["daten"]).strip() or defaults["daten"]
            trc_path = str(payload.get("trc_path") or "").strip()
            work_path = str(Path(trc_path).parent) if trc_path else defaults["work"]
            return {
                "daten": daten_path,
                "work": work_path,
            }
        except Exception:
            logger.exception("Failed to load SA config payload")
            return defaults

    def _load_paths_config_payload(self) -> dict:
        config_path = get_runtime_paths_config_path(self._runtime_profile)
        legacy_path = get_legacy_paths_config_path()

        if config_path.exists():
            try:
                return json.loads(config_path.read_text(encoding="utf-8"))
            except Exception:
                logger.exception("Failed to read startup path config from %s", config_path)
                return {}

        if not legacy_path.exists():
            return {}

        try:
            payload = json.loads(legacy_path.read_text(encoding="utf-8"))
        except Exception:
            logger.exception("Failed to read legacy startup path config from %s", legacy_path)
            return {}

        try:
            config_path.parent.mkdir(parents=True, exist_ok=True)
            config_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            logger.info("Migrated startup path config to %s", config_path)
        except Exception:
            logger.exception("Failed to migrate startup path config to %s", config_path)

        return payload

    def _set_app_icon(self):
        icon_path = Path(__file__).resolve().parent / "bimmerdatenlogo.ico"
        if icon_path.exists():
            icon = QIcon(str(icon_path))
            self.setWindowIcon(icon)

    def _resolve_startup_paths(self) -> dict:
        defaults = {
            "daten_path": r"C:\NCSEXPER\DATEN",
            "trc_path": r"C:\NCSEXPER\WORK\FSW_PSW.TRC",
            "translations_path": r"C:\NCS Dummy\Translations.csv",
            "work_path": r"C:\NCSEXPER\WORK",
        }

        payload = self._load_paths_config_payload()
        if not payload:
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

    def _save_startup_paths(self, paths: dict) -> None:
        config_path = get_runtime_paths_config_path(self._runtime_profile)
        payload: dict = self._load_paths_config_payload()

        payload.update(
            {
                "daten_path": str(paths.get("daten_path") or "").strip(),
                "trc_path": str(paths.get("trc_path") or "").strip(),
                "translations_path": str(paths.get("translations_path") or "").strip(),
            }
        )

        try:
            config_path.parent.mkdir(parents=True, exist_ok=True)
            config_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            logger.exception("Failed to save startup path config: %s", config_path)

    def _required_path_checks(self, paths: dict) -> list[tuple[str, str, str]]:
        return [
            ("DATEN folder", "daten_path", "dir"),
            ("TRC file", "trc_path", "file"),
            ("Translations.csv", "translations_path", "file"),
            ("WORK folder", "work_path", "dir"),
        ]

    def _pick_missing_required_paths(self, paths: dict) -> tuple[dict, bool]:
        updated = dict(paths)
        changed = False

        missing = []
        for label, key, kind in self._required_path_checks(updated):
            target = str(updated.get(key) or "").strip()
            exists = bool(target) and Path(target).exists()
            if not exists:
                missing.append((label, key, kind))

        if not missing:
            return updated, False

        ask = QMessageBox(self)
        ask.setWindowTitle("Startup Guard")
        ask.setIcon(QMessageBox.Icon.Warning)
        ask.setText("Some required paths are missing.")
        ask.setInformativeText("Do you want to locate the missing paths now?")
        ask.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if ask.exec() != int(QMessageBox.StandardButton.Yes):
            return updated, False

        base_start = str(Path.home())
        for label, key, kind in missing:
            current_value = str(updated.get(key) or "").strip()
            start_dir = current_value or base_start

            if kind == "dir":
                selected = QFileDialog.getExistingDirectory(
                    self,
                    f"Startup Guard - choose {label}",
                    start_dir,
                )
            else:
                if "Translations.csv" in label:
                    filter_text = "CSV Files (*.csv);;All Files (*)"
                else:
                    filter_text = "TRC Files (*.trc *.TRC);;All Files (*)"
                selected, _ = QFileDialog.getOpenFileName(
                    self,
                    f"Startup Guard - choose {label}",
                    start_dir,
                    filter_text,
                )

            if selected:
                updated[key] = selected
                changed = True

        if changed:
            trc_path = str(updated.get("trc_path") or "").strip()
            if trc_path:
                updated["work_path"] = str(Path(trc_path).parent)
            self._save_startup_paths(updated)

        return updated, changed

    def _build_startup_report(self, paths: dict | None = None) -> tuple[str, bool]:
        resolved_paths = paths or self._resolve_startup_paths()
        required_checks = [
            ("DATEN folder", resolved_paths["daten_path"]),
            ("TRC file", resolved_paths["trc_path"]),
            ("Translations.csv", resolved_paths["translations_path"]),
            ("WORK folder", resolved_paths["work_path"]),
        ]
        optional_checks = [
            ("INPA folder", self._inpa_path),
            ("EDIABAS ECU folder", self._ecu_path),
            ("Database file", str(self._db_path)),
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

    def _show_startup_report(self, force_show: bool = False, paths: dict | None = None):
        report_text, has_missing_required = self._build_startup_report(paths)

        if not force_show and not has_missing_required:
            return

        dialog = QMessageBox(self)
        dialog.setWindowTitle("Startup Guard")
        dialog.setIcon(QMessageBox.Icon.Warning if has_missing_required else QMessageBox.Icon.Information)
        if has_missing_required:
            dialog.setText("Missing required files/paths were detected for the full coding flow.")
            dialog.setInformativeText("Fill in the paths in the configuration to unlock all features.")
        else:
            dialog.setText("All required paths are available.")
            dialog.setInformativeText("Environment report below.")
        dialog.setDetailedText(report_text)
        dialog.setStandardButtons(QMessageBox.StandardButton.Ok)
        dialog.exec()

    def _run_startup_guard(self):
        paths = self._resolve_startup_paths()
        _report_text, has_missing_required = self._build_startup_report(paths)
        if has_missing_required:
            self.status_bar.showMessage("Startup Guard: some required files/paths are missing (details in the report).")
            self._show_startup_report(force_show=True, paths=paths)

            updated_paths, changed = self._pick_missing_required_paths(paths)
            if changed:
                _report_text, has_missing_required = self._build_startup_report(updated_paths)
                if has_missing_required:
                    self.status_bar.showMessage("Startup Guard: some required files/paths are still missing.")
                    self._show_startup_report(force_show=True, paths=updated_paths)
                else:
                    self.status_bar.showMessage("Startup Guard: required files/paths OK.")
                return

            self.status_bar.showMessage("Startup Guard: missing paths were not updated.")
            return

        self.status_bar.showMessage("Startup Guard: required files/paths OK.")

    def _setup_ui(self):
        self.setWindowTitle("BimmerDaten - Expert for EDIABAS and NCS")
        self.setMinimumSize(900, 600)
        self.resize(1100, 700)

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.update_bar = QWidget()
        self.update_bar.setVisible(False)
        self.update_bar.setStyleSheet("background-color: #fff3cd; border-bottom: 1px solid #c0a800;")

        bar_layout = QHBoxLayout(self.update_bar)
        bar_layout.setContentsMargins(8, 4, 8, 4)

        self.update_bar_label = QLabel("💡 Database update available")
        bar_layout.addWidget(self.update_bar_label, 1)

        update_now_btn = QPushButton("Update now")
        update_now_btn.setFixedWidth(100)
        update_now_btn.clicked.connect(self._update_database_github)
        bar_layout.addWidget(update_now_btn)

        dismiss_btn = QPushButton("Dismiss")
        dismiss_btn.setFixedWidth(70)
        dismiss_btn.clicked.connect(self.update_bar.hide)
        bar_layout.addWidget(dismiss_btn)

        main_layout.insertWidget(0, self.update_bar)

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

        self.open_btn = QPushButton("📂 Open .PRG")
        self.open_btn.clicked.connect(self._open_file)
        toolbar_layout.addWidget(self.open_btn)

        self.vehicle_info_label = QLabel("No file loaded")
        self.vehicle_info_label.setWordWrap(True)
        toolbar_layout.addWidget(self.vehicle_info_label, 1)

        toolbar_layout.addStretch()

        self.jobs_info = QLabel("No file loaded")
        toolbar_layout.addWidget(self.jobs_info)

        jobs_layout.addWidget(toolbar_widget)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(4)

        self.job_list_panel = JobListPanel()
        self.job_detail_panel = JobDetailPanel()
        self.job_detail_panel.languageChanged.connect(self._on_language_changed)
        self.job_detail_panel.showAllTablesRequested.connect(
            lambda: self.main_tabs.setCurrentWidget(self.tables_panel)
        )

        splitter.addWidget(self.job_list_panel)
        splitter.addWidget(self.job_detail_panel)
        splitter.setSizes([280, 820])

        jobs_layout.addWidget(splitter)
        self.main_tabs.addTab(jobs_tab, "💼 Jobs")

        # Tab 2: tabele
        self.tables_panel = TablesPanel(db=self._db)
        self.main_tabs.addTab(self.tables_panel, "📋 Tables")

        # Tab 3: modele INPA
        self.models_panel = ModelsPanel()
        self.models_panel.openPrgRequested.connect(self._open_file_direct)
        self.models_panel.changeInpaPathRequested.connect(self._choose_inpa_path)
        self.main_tabs.addTab(self.models_panel, "🚗 Models")

        self.models_tab_index = 2
        self.main_tabs.currentChanged.connect(self._on_main_tab_changed)

        self.top_tabs.addTab(diagnosis_tab, "🔧 Diagnosis")

        if CODING_AVAILABLE:
            self.coding_panel = CodingPanel(self._db)
        else:
            self.coding_panel = QWidget()
            fallback_layout = QVBoxLayout(self.coding_panel)
            fallback_layout.addWidget(QLabel("Failed to load the coding panel."))

        self.top_tabs.addTab(self.coding_panel, "⚙️ Coding")

        if SA_OPTIONS_AVAILABLE:
            self.sa_options_panel = SAOptionsWidget(self._db, self._sa_config, self)
        else:
            self.sa_options_panel = QWidget()
            sa_layout = QVBoxLayout(self.sa_options_panel)
            sa_layout.addWidget(QLabel("Failed to load the SA Options tab."))

        self.top_tabs.addTab(self.sa_options_panel, "🔧 SA Options")

        if not self._inpa_path:
            self.models_panel.set_placeholder("INPA installation not found")
        else:
            self.models_panel.set_placeholder("Open the Models tab to load the INPA parser")

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
        file_menu = menubar.addMenu("File")
        open_action = QAction("Open .PRG...", self)
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self._open_file)
        file_menu.addAction(open_action)

        update_menu = file_menu.addMenu("Update Database")

        github_action = update_menu.addAction("From GitHub")
        github_action.setStatusTip("Download latest translations and presets from GitHub")
        github_action.triggered.connect(self._update_database_github)

        csv_action = update_menu.addAction("From CSV file...")
        csv_action.setStatusTip("Import a local CSV seed file into the database")
        csv_action.triggered.connect(self._update_database_csv)

        file_menu.addSeparator()
        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # Menu Pomoc
        help_menu = menubar.addMenu("Help")
        report_action = QAction("Startup Guard report", self)
        report_action.triggered.connect(lambda: self._show_startup_report(force_show=True))
        help_menu.addAction(report_action)
        logs_action = QAction("Open Logs Folder", self)
        logs_action.triggered.connect(self._open_logs_folder)
        help_menu.addAction(logs_action)
        about_action = QAction("About", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    def _open_logs_folder(self):
        logs_dir = Path(get_logs_dir_path())
        try:
            logs_dir.mkdir(parents=True, exist_ok=True)
            if platform.system() == "Windows":
                os.startfile(str(logs_dir))
            else:
                QMessageBox.information(self, "Logs", f"Logs folder:\n{logs_dir}")
        except Exception:
            logger.exception("Failed to open logs folder: %s", logs_dir)
            QMessageBox.warning(self, "Logs", f"Failed to open logs folder:\n{logs_dir}")

    def _start_update_check(self):
        if not self._db:
            return

        local_version = (self._db.get_setting("seeds_version", "") or "").strip()

        # Bootstrap DB setting from bundled seeds/version.txt on first run.
        bundled_version = ""
        try:
            version_file = Path(__file__).resolve().parent / "seeds" / "version.txt"
            if version_file.exists():
                bundled_version = version_file.read_text(encoding="utf-8").strip()
        except Exception:
            logger.exception("Failed to read bundled seeds version file")

        if not local_version:
            local_version = bundled_version or "0000-00-00"
            if local_version:
                try:
                    self._db.set_setting("seeds_version", local_version)
                except Exception:
                    logger.exception("Failed to bootstrap seeds_version setting")

        self._update_worker = UpdateCheckWorker(local_version)
        self._update_worker.update_available.connect(self._on_update_available)
        self._update_worker.start()

    def _on_update_available(self, remote_version: str):
        self.update_bar_label.setText(
            f"💡 Database update available (v{remote_version}) — "
            "new presets and translations ready to download"
        )
        self.update_bar.setVisible(True)

    def _update_database_github(self):
        if not self._db:
            QMessageBox.warning(self, "Update Database", "Database is not available.")
            return

        progress = QProgressDialog("Connecting to GitHub...", None, 0, 0, self)
        progress.setWindowTitle("Update Database")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.setValue(0)
        progress.show()
        QApplication.processEvents()

        def on_progress(msg: str):
            progress.setLabelText(msg)
            QApplication.processEvents()

        try:
            results = self._db.update_from_github(progress_callback=on_progress)
        except Exception as exc:
            progress.close()
            QMessageBox.critical(
                self,
                "Update Database",
                f"Failed to connect to GitHub:\n{exc}\n\nCheck your internet connection.",
            )
            return

        progress.close()

        if self._db:
            try:
                import urllib.request

                with urllib.request.urlopen(UpdateCheckWorker.VERSION_URL, timeout=5) as resp:
                    remote_version = resp.read().decode("utf-8").strip()
                if remote_version:
                    self._db.set_setting("seeds_version", remote_version)
                self.update_bar.setVisible(False)
            except Exception:
                logger.exception("Failed to persist seeds_version after GitHub update")

        lines = []
        for table, result in results.items():
            if isinstance(result, dict):
                added = int(result.get("added", 0))
                existing = int(result.get("existing", 0))
                lines.append(f"  {table}: {added} rows added, {existing} already existed")
            elif isinstance(result, int):
                lines.append(f"  {table}: {result} rows added")
            else:
                lines.append(f"  {table}: {result}")

        QMessageBox.information(
            self,
            "Update Database",
            "Database update complete:\n\n" + "\n".join(lines),
        )

    def _update_database_csv(self):
        if not self._db:
            QMessageBox.warning(self, "Update Database", "Database is not available.")
            return

        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select CSV seed file",
            "",
            "CSV files (*.csv);;All files (*)",
        )
        if not path:
            return

        import os

        filename = os.path.basename(path).lower().replace(".csv", "")
        known_tables = [
            "table_descriptions",
            "translations",
            "coding_presets",
            "sa_translations",
        ]
        suggested = filename if filename in known_tables else ""

        table_name, ok = QInputDialog.getItem(
            self,
            "Select target table",
            f"File: {os.path.basename(path)}\n\nImport into which table?",
            known_tables,
            current=known_tables.index(suggested) if suggested else 0,
            editable=False,
        )
        if not ok or not table_name:
            return

        try:
            count = self._db.import_csv_file(path, table_name)
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Update Database",
                f"Failed to import CSV:\n{exc}",
            )
            return

        QMessageBox.information(
            self,
            "Update Database",
            f"Import complete.\n\n  {table_name}: {count} rows imported from file.",
        )

    def _open_file(self):
        if not DECODER_AVAILABLE:
            self.status_bar.showMessage(
                "ERROR: Cannot import decoderPrg.py!"
            )
            return

        default_dir = r"C:\EDIABAS\Ecu"
        if not Path(default_dir).exists():
            default_dir = ""

        filepath, _ = QFileDialog.getOpenFileName(
            self,
            "Open EDIABAS PRG file",
            default_dir,
            "EDIABAS PRG Files (*.prg *.PRG);;All Files (*)"
        )
        if not filepath:
            return

        self._open_file_direct(filepath)

    def _open_file_direct(self, filepath: str):
        if not DECODER_AVAILABLE:
            self.status_bar.showMessage(
                "ERROR: Cannot import decoderPrg.py!"
            )
            return

        self.status_bar.showMessage(f"Loading: {filepath}...")
        QApplication.processEvents()

        try:
            self._prg = parse_prg(filepath)
            self._filepath = filepath
            self._load_prg()
            self.top_tabs.setCurrentIndex(0)
            self.main_tabs.setCurrentIndex(0)
            self.status_bar.showMessage(
                f"Loaded: {Path(filepath).name} — "
                f"{len(self._prg.jobs)} jobs, "
                f"{len(self._prg.tables)} tables"
            )
        except Exception as e:
            self.status_bar.showMessage(f"ERROR: {e}")

    def _choose_inpa_path(self):
        start_dir = self._inpa_path or r"C:\EC-APPS\INPA"
        folder = QFileDialog.getExistingDirectory(
            self,
            "Choose INPA folder",
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
            self.status_bar.showMessage(f"INPA parser error: {exc}")
            return None

        self._models_parser_cls = INPAParser
        return self._models_parser_cls

    def _load_models_data(self, force_reload: bool = False):
        if not self._inpa_path:
            self.models_panel.set_placeholder("INPA installation not found")
            return

        if not force_reload and self._models_loaded_for_path == self._inpa_path:
            self.models_panel.set_models_data(self._models_data, self._inpa_path, self._ecu_path)
            return

        parser_cls = self._ensure_inpa_parser()
        if parser_cls is None:
            self.models_panel.set_placeholder("Failed to load the INPA parser")
            return

        try:
            parser = parser_cls(self._inpa_path)
            self._models_data = parser.parse_all()
            self._models_loaded_for_path = self._inpa_path
            self.models_panel.set_parser(parser)
            self.models_panel.set_models_data(self._models_data, self._inpa_path, self._ecu_path)
            if self._models_data:
                self.status_bar.showMessage(f"Loaded INPA models from {self._inpa_path}")
            else:
                self.status_bar.showMessage("No .ENG files found in CFGDAT")
        except Exception as exc:
            self.models_panel.set_placeholder(f"INPA load error: {exc}")
            self.status_bar.showMessage(f"INPA load error: {exc}")

    def _load_prg(self):
        if not self._prg:
            return

        self.job_list_panel.load_jobs(self._prg.jobs)
        self.tables_panel.load_tables(self._prg.tables)
        self.job_detail_panel.clear()
        self._update_vehicle_info_bar()
        self.jobs_info.setText(
            f"Jobs: {len(self._prg.jobs)} | Tables: {len(self._prg.tables)}"
        )

    def _update_vehicle_info_bar(self):
        if not self._prg or not self._filepath:
            self.vehicle_info_label.setText("No file loaded")
            return

        file_name = Path(self._filepath).name
        info = self._prg.info
        parts = [f"File: {file_name}"]
        if info.bip_version:
            parts.append(f"BIP: {info.bip_version}")
        if info.revision:
            parts.append(f"Rev: {info.revision}")
        if info.author:
            parts.append(f"Author: {info.author}")
        if info.last_changed:
            parts.append(f"Date: {info.last_changed}")
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
        self.status_bar.showMessage(f"Translation language: {self._lang.upper()}")

    def _show_about(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("About")
        dialog.setFixedSize(520, 560)
        dialog.setWindowFlags(dialog.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        dialog.setStyleSheet(WIN98_STYLE)

        layout = QVBoxLayout(dialog)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 12)

        # Title bar (navy, matching JOB title bar style)
        header = QLabel("  BimmerDaten")
        header.setObjectName("title_label")
        header.setFont(QFont("Tahoma", 13, QFont.Weight.Bold))
        header.setFixedHeight(36)
        layout.addWidget(header)

        content_layout = QVBoxLayout()
        content_layout.setContentsMargins(16, 14, 16, 0)
        content_layout.setSpacing(10)

        # Version / author row
        meta = QLabel(
            "<b>Version:</b> v1.0 &nbsp;&nbsp; "
            "<b>Author:</b> Filip Dzitko (zer02dev) &nbsp;&nbsp; "
            "<b>License:</b> GPL-3.0"
        )
        meta.setWordWrap(True)
        content_layout.addWidget(meta)

        sep1 = QFrame()
        sep1.setFrameShape(QFrame.Shape.HLine)
        sep1.setObjectName("separator")
        content_layout.addWidget(sep1)

        # Features
        features = QTextBrowser()
        features.setOpenExternalLinks(True)
        features.setHtml(
            "<b>Features:</b>"
            "<ul style='margin-top:4px; margin-bottom:0; padding-left:18px;'>"
            "<li>EDIABAS job browser - arguments, results, disassembly, tables</li>"
            "<li>Live data (BETRIEBSWTAB) with DS2 telegram decoding</li>"
            "<li>TRC coding editor with change tracking and history</li>"
            "<li>Coding presets - save and load favorite configurations</li>"
            "<li>Export changes to .MAN / .TRC</li>"
            "<li>DE → EN / PL translations (offline DB + online fallback)</li>"
            "<li>FA/SA decoder from AT.000 and fa.trc files</li>"
            "<li>INPA model parser with PRG file discovery</li>"
            "<li>PDF reports with coding history and comparison</li>"
            "</ul>"
        )
        features.setMaximumHeight(185)
        content_layout.addWidget(features)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setObjectName("separator")
        content_layout.addWidget(sep2)

        # Credits
        credits = QTextBrowser()
        credits.setOpenExternalLinks(True)
        credits.setHtml(
            "<b>Dependencies:</b> PyQt6, deep-translator, reportlab<br><br>"
            "<b>NCS parameter translations:</b> Translations.csv &copy; REVTOR "
            "(NCS Dummy) - not bundled with the app, "
            "loaded from the user's local installation.<br><br>"
            "<b>Bug reports:</b> "
            "<a href='https://github.com/zer02dev/BimmerDaten/issues'>"
            "github.com/zer02dev/BimmerDaten</a>"
        )
        credits.setMaximumHeight(115)
        content_layout.addWidget(credits)

        layout.addLayout(content_layout)

        ok_btn = QPushButton("OK")
        ok_btn.setFixedWidth(80)
        ok_btn.clicked.connect(dialog.accept)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(ok_btn)
        btn_row.setContentsMargins(0, 8, 16, 0)
        layout.addLayout(btn_row)

        dialog.exec()

    def closeEvent(self, event):
        man_path = Path(r"C:\NCSEXPER\WORK\FSW_PSW.MAN")
        if man_path.exists() and man_path.stat().st_size > 0:
            dialog = QMessageBox(self)
            dialog.setWindowTitle("Close application?")
            dialog.setText(
                "FSW_PSW.MAN is not empty.\n\n"
                "Good NCS Expert practice is to clear the file after finishing work.\n"
                "Do you want to clear FSW_PSW.MAN?"
            )
            clear_button = dialog.addButton("Yes - clear it", QMessageBox.ButtonRole.YesRole)
            no_button = dialog.addButton("No", QMessageBox.ButtonRole.NoRole)
            cancel_button = dialog.addButton("Cancel closing", QMessageBox.ButtonRole.RejectRole)
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
                    QMessageBox.critical(self, "Error", f"Failed to clear the file:\n{exc}")
                    play_sound("error")
                    event.ignore()
                    return

        if self._db:
            self._db.close()
        super().closeEvent(event)


# ---------------------------------------------------------------------------
# Uruchomienie

class SplashScreen(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.SplashScreen
        )
        self.setFixedSize(420, 220)
        self.setStyleSheet("background-color: #d4d0c8;")

        screen = QApplication.primaryScreen().geometry()
        self.move(
            (screen.width() - self.width()) // 2,
            (screen.height() - self.height()) // 2
        )

        # Outer border (Win98 window border effect)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(2, 2, 2, 2)
        outer.setSpacing(0)

        inner = QWidget()
        inner.setStyleSheet(
            "QWidget {"
            "  background-color: #d4d0c8;"
            "  border-top: 2px solid #ffffff;"
            "  border-left: 2px solid #ffffff;"
            "  border-bottom: 2px solid #808080;"
            "  border-right: 2px solid #808080;"
            "}"
        )
        outer.addWidget(inner)

        main_layout = QVBoxLayout(inner)
        main_layout.setContentsMargins(0, 0, 0, 12)
        main_layout.setSpacing(0)

        # Title bar (navy, Win98 style)
        title_bar = QWidget()
        title_bar.setFixedHeight(24)
        title_bar.setStyleSheet(
            "QWidget {"
            "  background-color: #000080;"
            "  border: none;"
            "}"
        )
        title_layout = QHBoxLayout(title_bar)
        title_layout.setContentsMargins(6, 0, 6, 0)
        title_layout.setSpacing(6)

        icon_path = Path(__file__).resolve().parent / "bimmerdatenlogo.ico"
        if icon_path.exists():
            icon_label = QLabel()
            icon_label.setStyleSheet("border: none; background: transparent;")
            pixmap = QPixmap(str(icon_path)).scaled(
                16, 16,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            icon_label.setPixmap(pixmap)
            title_layout.addWidget(icon_label)

        title_text = QLabel("BimmerDaten")
        title_text.setStyleSheet(
            "color: #ffffff;"
            "font-family: 'Tahoma';"
            "font-size: 11px;"
            "font-weight: bold;"
            "background: transparent;"
            "border: none;"
        )
        title_layout.addWidget(title_text)
        title_layout.addStretch()

        ver_title = QLabel("v1.0")
        ver_title.setStyleSheet(
            "color: #aaaacc;"
            "font-family: 'Tahoma';"
            "font-size: 10px;"
            "background: transparent;"
            "border: none;"
        )
        title_layout.addWidget(ver_title)

        main_layout.addWidget(title_bar)

        # Content area
        content = QWidget()
        content.setStyleSheet("QWidget { border: none; background-color: #d4d0c8; }")
        content_layout = QHBoxLayout(content)
        content_layout.setContentsMargins(16, 16, 16, 8)
        content_layout.setSpacing(16)

        # Logo
        if icon_path.exists():
            logo_label = QLabel()
            logo_label.setStyleSheet("border: none; background: transparent;")
            pixmap_large = QPixmap(str(icon_path)).scaled(
                64, 64,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            logo_label.setPixmap(pixmap_large)
            logo_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
            logo_label.setFixedWidth(72)
            content_layout.addWidget(logo_label)

        # Right side: text
        right_col = QVBoxLayout()
        right_col.setSpacing(4)

        app_name = QLabel("BimmerDaten")
        app_name.setStyleSheet(
            "font-family: 'Tahoma';"
            "font-size: 18px;"
            "font-weight: bold;"
            "color: #000080;"
            "border: none;"
            "background: transparent;"
        )
        right_col.addWidget(app_name)

        sub_text = QLabel("Expert for EDIABAS and NCS")
        sub_text.setStyleSheet(
            "font-family: 'Tahoma';"
            "font-size: 10px;"
            "color: #444444;"
            "border: none;"
            "background: transparent;"
        )
        right_col.addWidget(sub_text)

        right_col.addSpacing(12)

        # Separator line (inset, Win98)
        sep_widget = QFrame()
        sep_widget.setFrameShape(QFrame.Shape.HLine)
        sep_widget.setStyleSheet(
            "border-top: 1px solid #808080;"
            "border-bottom: 1px solid #ffffff;"
        )
        right_col.addWidget(sep_widget)
        right_col.addSpacing(8)

        self.status_label = QLabel("Starting...")
        self.status_label.setStyleSheet(
            "font-family: 'Tahoma';"
            "font-size: 10px;"
            "color: #444444;"
            "border: none;"
            "background: transparent;"
        )
        right_col.addWidget(self.status_label)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setFixedHeight(16)
        self.progress.setTextVisible(False)
        self.progress.setStyleSheet(
            "QProgressBar {"
            "  background-color: #ffffff;"
            "  border-top: 1px solid #808080;"
            "  border-left: 1px solid #808080;"
            "  border-bottom: 1px solid #ffffff;"
            "  border-right: 1px solid #ffffff;"
            "  border-radius: 0px;"
            "}"
            "QProgressBar::chunk {"
            "  background-color: #000080;"
            "  border-radius: 0px;"
            "}"
        )
        right_col.addWidget(self.progress)
        right_col.addStretch()

        content_layout.addLayout(right_col)
        main_layout.addWidget(content)

    def set_status(self, text: str):
        self.status_label.setText(text)
        QApplication.processEvents()

def main():
    session_logger = setup_logger()
    session_logger.info("main(): startup")

    def _handle_unhandled_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return

        session_logger.exception(
            "Unhandled exception",
            exc_info=(exc_type, exc_value, exc_traceback),
        )
        log_path = get_log_file_path() or "(log file not initialized)"
        message = (
            f"Unexpected error:\n{exc_value}\n\n"
            f"Log file:\n{log_path}"
        )
        try:
            QMessageBox.critical(None, "BimmerDaten - Error", message)
        except Exception:
            session_logger.exception("Failed to show critical error dialog")

    sys.excepthook = _handle_unhandled_exception

    session_logger.info("main(): before Windows AppUserModelID setup")
    if platform.system() == "Windows":
        try:
            session_logger.info("main(): before import ctypes")
            import ctypes
            session_logger.info("main(): after import ctypes")

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "BimmerDaten.PRGViewer"
            )
        except Exception:
            session_logger.exception("main(): failed setting Windows AppUserModelID")

    session_logger.info("main(): before QApplication construction")
    app = QApplication(sys.argv)
    session_logger.info("main(): after QApplication construction")
    app.setApplicationName("BimmerDaten")
    app.setStyle("Windows")  # styl Windows dla lepszego efektu retro
    icon_path = Path(__file__).resolve().parent / "bimmerdatenlogo.ico"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    splash = SplashScreen()
    splash.show()
    app.processEvents()

    splash.set_status("Loading modules...")
    app.processEvents()

    splash.set_status("Initializing database...")
    app.processEvents()

    splash.set_status("Building interface...")
    session_logger.info("main(): before MainWindow() construction")
    window = MainWindow()
    session_logger.info("main(): after MainWindow() construction")

    splash.set_status("Ready.")
    app.processEvents()

    window.show()
    session_logger.info("main(): before splash.close()")
    splash.close()
    session_logger.info("main(): after splash.close()")
    session_logger.info("main(): entering Qt event loop")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()