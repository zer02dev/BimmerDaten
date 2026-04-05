"""
trc_coding.py
Panel kodowania NCS Expert oraz narzędzia do pracy z plikami TRC.
"""

from __future__ import annotations

import os
import configparser
import json
import re
from html import escape as html_escape
from dataclasses import dataclass, field
from pathlib import Path

from PyQt6.QtCore import QObject, QThread, Qt, pyqtSignal, QSettings
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
    QHeaderView,
)

from database import Database
from daten_parser import detect_module_from_trc, load_module, parse_trc as parse_trc_file
from trc_translator import TrcTranslator

try:
    import winreg
except Exception:
    winreg = None


DEFAULT_TRC_PATH = Path(r"C:\NCSEXPER\WORK\FSW_PSW.TRC")
DEFAULT_DATEN_PATH = Path(r"C:\NCSEXPER\DATEN")
DEFAULT_TRANSLATIONS_PATH = Path(r"C:\NCS Dummy\Translations.csv")
DEFAULT_MAND_PATH = Path(r"C:\NCSEXPER\WORK\FSW_PSW.MAN")
DEFAULT_WORK_PATH = Path(r"C:\NCSEXPER\WORK")
CONFIG_PATH = Path(__file__).resolve().parent / "data" / "ncs_coding_paths.json"


@dataclass
class TrcSegment:
    kind: str
    option: str = ""
    value: str = ""
    raw_lines: list[str] = field(default_factory=list)
    original_value: str = ""


@dataclass
class CodingPaths:
    trc_path: str = str(DEFAULT_TRC_PATH)
    daten_path: str = str(DEFAULT_DATEN_PATH)
    translations_path: str = str(DEFAULT_TRANSLATIONS_PATH)


def read_text_file(path: Path) -> str:
    for encoding in ("utf-8-sig", "cp1250", "latin1", "mbcs"):
        try:
            return path.read_text(encoding=encoding)
        except Exception:
            continue
    return path.read_text(encoding="latin1", errors="ignore")


def _read_ncs_last_profile_name() -> str:
    if winreg is None:
        return ""

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\BMWGroup\ISSS\NCSExpert") as key:
            value, _ = winreg.QueryValueEx(key, "LastProfile")
            return str(value or "").strip()
    except Exception:
        return ""


def _parse_pfl_profile(pfl_path: Path) -> dict:
    result = {
        "profile_name": pfl_path.stem,
        "can_read": False,
        "can_write": False,
        "profile_path": str(pfl_path),
    }

    try:
        text = read_text_file(pfl_path)
    except Exception:
        return result

    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str
    try:
        parser.read_string(text)
    except Exception:
        parser = None

    values: dict[str, str] = {}
    if parser is not None:
        for section_name in parser.sections():
            for key, value in parser.items(section_name):
                values[key.strip().casefold()] = str(value).strip()
        for key, value in parser.defaults().items():
            values[key.strip().casefold()] = str(value).strip()

    if not values:
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith((";", "#", "[")):
                continue
            if "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            values[key.strip().casefold()] = value.strip()

    def _is_enabled(name: str) -> bool:
        return values.get(name.casefold(), "").strip() in {"1", "true", "yes", "tak", "on"}

    result["can_read"] = _is_enabled("FswPswLesenModus")
    result["can_write"] = _is_enabled("FswPswManipulieren") and _is_enabled("FktSgCodieren")

    for key in ("profile_name", "profilname", "name"):
        if values.get(key):
            result["profile_name"] = values[key].strip()
            break

    return result


def _collect_pfl_profiles(base_path: Path) -> list[dict]:
    profiles: list[dict] = []
    if not base_path.exists():
        return profiles

    pfl_files = sorted(
        [path for path in set(list(base_path.glob("*.pfl")) + list(base_path.glob("*.PFL"))) if path.is_file()],
        key=lambda path: str(path).casefold(),
    )

    profile_hint = _read_ncs_last_profile_name().strip()
    hint_stem = Path(profile_hint).stem.casefold() if profile_hint else ""
    hint_name = profile_hint.casefold()

    for pfl_file in pfl_files:
        info = _parse_pfl_profile(pfl_file)
        can_read = bool(info.get("can_read"))
        can_write = bool(info.get("can_write"))
        if can_write:
            status = "full"
            status_label = "pełny dostęp (odczyt + zapis)"
            color = "#228B22"
        elif can_read:
            status = "read"
            status_label = "tylko odczyt"
            color = "#FFD700"
        else:
            status = "blocked"
            status_label = "brak wymaganych uprawnień"
            color = "#FF8C00"

        profile_name = str(info.get("profile_name") or pfl_file.stem).strip() or pfl_file.stem
        profiles.append(
            {
                "found": True,
                "profile_name": profile_name,
                "can_read": can_read,
                "can_write": can_write,
                "profile_path": str(pfl_file),
                "status": status,
                "status_label": status_label,
                "color": color,
                "is_selected": bool(profile_hint) and (
                    pfl_file.stem.casefold() == hint_stem or pfl_file.name.casefold() == hint_name
                ),
            }
        )

    return profiles


def check_ncs_profile(ncs_path: str) -> dict:
    default_root = r"C:\NCSEXPER\\"
    base_path = Path((ncs_path or default_root).strip() or default_root)
    if base_path.is_file() and base_path.suffix.lower() == ".pfl":
        info = _parse_pfl_profile(base_path)
        info["found"] = True
        return {
            "found": True,
            "profile_name": info.get("profile_name", base_path.stem),
            "can_read": bool(info.get("can_read")),
            "can_write": bool(info.get("can_write")),
            "profile_path": str(base_path),
            "profiles": [
                {
                    "found": True,
                    "profile_name": info.get("profile_name", base_path.stem),
                    "can_read": bool(info.get("can_read")),
                    "can_write": bool(info.get("can_write")),
                    "profile_path": str(base_path),
                    "status": "full" if info.get("can_write") else "read" if info.get("can_read") else "blocked",
                    "status_label": "pełny dostęp (odczyt + zapis)"
                    if info.get("can_write")
                    else "tylko odczyt"
                    if info.get("can_read")
                    else "brak wymaganych uprawnień",
                    "color": "#228B22" if info.get("can_write") else "#FFD700" if info.get("can_read") else "#FF8C00",
                    "is_selected": True,
                }
            ],
        }

    profiles = _collect_pfl_profiles(base_path)
    if profiles:
        selected_profile = next((profile for profile in profiles if profile.get("is_selected")), profiles[0])
        return {
            "found": True,
            "profile_name": str(selected_profile.get("profile_name") or ""),
            "can_read": bool(selected_profile.get("can_read")),
            "can_write": bool(selected_profile.get("can_write")),
            "profile_path": str(selected_profile.get("profile_path") or ""),
            "profiles": profiles,
        }

    return {
        "found": False,
        "profile_name": "",
        "can_read": False,
        "can_write": False,
        "profile_path": "",
        "profiles": [],
    }


def parse_trc_content(content: str) -> list[TrcSegment]:
    lines = content.splitlines()
    segments: list[TrcSegment] = []
    index = 0

    while index < len(lines):
        current_line = lines[index]
        if not current_line.strip():
            segments.append(TrcSegment(kind="raw", raw_lines=[current_line]))
            index += 1
            continue

        if index + 1 < len(lines):
            next_line = lines[index + 1]
            if next_line.startswith(("\t", " ")):
                option = current_line.strip()
                value = next_line.strip()
                segments.append(
                    TrcSegment(
                        kind="option",
                        option=option,
                        value=value,
                        raw_lines=[current_line, next_line],
                        original_value=value,
                    )
                )
                index += 2
                continue

        segments.append(TrcSegment(kind="raw", raw_lines=[current_line]))
        index += 1

    return segments


def parse_sysdaten(work_folder: str) -> dict:
    base_folder = Path((work_folder or "").strip() or str(DEFAULT_WORK_PATH))
    file_path = base_folder / "SYSDATEN.TRC"
    if not file_path.exists():
        return {}

    wanted_keys = [
        "FAHRGESTELL_NR",
        "TEILENUMMER",
        "CODIERDATUM",
        "HAENDLER_NR",
        "CHECKSUM",
        "LACK_CODE",
        "POLSTER_CODE",
    ]
    parsed: dict[str, str] = {key: "" for key in wanted_keys}
    wanted_set = set(wanted_keys)
    for segment in parse_trc_content(read_text_file(file_path)):
        if segment.kind != "option":
            continue
        key = segment.option.strip().upper()
        if key in wanted_set:
            parsed[key] = segment.value.strip()
    return parsed


def parse_fa_trc(work_folder: str) -> dict:
    base_folder = Path((work_folder or "").strip() or str(DEFAULT_WORK_PATH))
    file_path = base_folder / "fa.trc"
    if not file_path.exists():
        return {}

    content = read_text_file(file_path).strip()
    if not content:
        return {}

    first_line = content.splitlines()[0].strip()
    model = first_line.split("_", 1)[0].strip() if "_" in first_line else ""

    production_date = ""
    hash_pos = first_line.find("#")
    if hash_pos >= 0:
        and_pos = first_line.find("&", hash_pos + 1)
        if and_pos > hash_pos:
            production_date = first_line[hash_pos + 1:and_pos].strip()
        else:
            production_date = first_line[hash_pos + 1:].strip()

    sa_codes = re.findall(r"\$([0-9A-Fa-f]+)", first_line)
    sa_codes = [code.upper() for code in sa_codes]

    return {
        "model": model,
        "production_date": production_date,
        "sa_codes": sa_codes,
    }


def format_trc_content(segments: list[TrcSegment]) -> str:
    lines: list[str] = []
    for segment in segments:
        if segment.kind == "option":
            lines.append(segment.option)
            lines.append(f"\t\t{segment.value}")
        else:
            lines.extend(segment.raw_lines or [""])
    if not lines:
        return ""
    return "\n".join(lines) + "\n"


def format_man_content(segments: list[TrcSegment]) -> str:
    lines: list[str] = []
    for segment in segments:
        if segment.kind == "option":
            lines.append(segment.option)
            lines.append(f"\t{segment.value}")
        else:
            lines.extend(segment.raw_lines or [""])
    if not lines:
        return ""
    return "\r\n".join(lines) + "\r\n"


def build_change_list(segments: list[TrcSegment]) -> list[dict]:
    changes: list[dict] = []
    for segment in segments:
        if segment.kind != "option":
            continue
        if segment.value == segment.original_value:
            continue
        changes.append(
            {
                "option": segment.option,
                "from": segment.original_value,
                "to": segment.value,
            }
        )
    return changes


def build_option_map(content: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for segment in parse_trc_content(content):
        if segment.kind == "option":
            result[segment.option.upper()] = segment.value
    return result


def compare_trc_contents(content_a: str, content_b: str) -> list[tuple[str, str, str, bool]]:
    map_a = build_option_map(content_a)
    map_b = build_option_map(content_b)
    ordered_keys: list[str] = []
    seen: set[str] = set()

    for key in list(map_a.keys()) + list(map_b.keys()):
        if key not in seen:
            seen.add(key)
            ordered_keys.append(key)

    rows: list[tuple[str, str, str, bool]] = []
    for key in ordered_keys:
        value_a = map_a.get(key, "")
        value_b = map_b.get(key, "")
        same = value_a == value_b
        rows.append((key, value_a, value_b, same))
    return rows


def _read_json_config() -> dict:
    if not CONFIG_PATH.exists():
        return {}
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_json_config(data: dict) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _candidate_path(default_path: Path, config_value: str | None) -> Path:
    if default_path.exists():
        return default_path
    if config_value:
        candidate = Path(config_value)
        if candidate.exists():
            return candidate
        return candidate
    return default_path


class PathConfigDialog(QDialog):
    def __init__(self, paths: CodingPaths, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Zmień ścieżki")
        self.setModal(True)
        self._build_ui(paths)

    def _build_ui(self, paths: CodingPaths):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)

        self.trc_edit = self._path_row(form, "TRC", paths.trc_path, False)
        self.daten_edit = self._path_row(form, "DATEN", paths.daten_path, True)
        self.translations_edit = self._path_row(form, "Translations.csv", paths.translations_path, False)

        layout.addLayout(form)

        buttons = QDialogButtonBox()
        self.ok_button = QPushButton("Zapisz")
        self.cancel_button = QPushButton("Anuluj")
        self.ok_button.clicked.connect(self.accept)
        self.cancel_button.clicked.connect(self.reject)
        buttons.addButton(self.ok_button, QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.addButton(self.cancel_button, QDialogButtonBox.ButtonRole.RejectRole)
        layout.addWidget(buttons)

    def _path_row(self, form: QFormLayout, label: str, value: str, folder: bool) -> QLineEdit:
        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(4)

        edit = QLineEdit(value)
        browse = QPushButton("...")

        def choose_path():
            if folder:
                selected = QFileDialog.getExistingDirectory(self, f"Wybierz {label}", edit.text() or str(Path.home()))
                if selected:
                    edit.setText(selected)
            else:
                if label == "Translations.csv":
                    filter_text = "CSV Files (*.csv);;All Files (*)"
                else:
                    filter_text = "EDIABAS Files (*.trc *.TRC *.man *.MAN);;All Files (*)"
                selected, _ = QFileDialog.getOpenFileName(self, f"Wybierz {label}", edit.text() or str(Path.home()), filter_text)
                if selected:
                    edit.setText(selected)

        browse.clicked.connect(choose_path)
        row_layout.addWidget(edit, 1)
        row_layout.addWidget(browse)
        form.addRow(label, row_widget)
        return edit

    def get_paths(self) -> CodingPaths:
        return CodingPaths(
            trc_path=self.trc_edit.text().strip(),
            daten_path=self.daten_edit.text().strip(),
            translations_path=self.translations_edit.text().strip(),
        )


class ExportConfirmDialog(QDialog):
    def __init__(self, changes: list[dict], translator: TrcTranslator, module_file: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Potwierdzenie eksportu")
        self.setModal(True)
        self._translator = translator
        self._module_file = (module_file or "").strip()
        self._build_ui(changes)

    def _tr(self, keyword: str) -> str:
        text = str(keyword or "")
        if not text:
            return ""
        translated = self._translator.get_translation(text)
        return translated if translated else text

    def _de_en(self, de_text: str) -> str:
        de_value = str(de_text or "")
        en_value = self._tr(de_value)
        return f"{de_value} ({en_value})"

    def _build_ui(self, changes: list[dict]):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        module_text = self._module_file or "BRAK_MODULU"
        label = QLabel(f"Podsumowanie zmian - {module_text}")
        layout.addWidget(label)

        table = QTableWidget()
        table.setColumnCount(4)
        table.setHorizontalHeaderLabels(["Funkcja DE", "Funkcja EN", "Było DE (EN)", "Jest DE (EN)"])
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setStretchLastSection(True)
        table.setRowCount(len(changes))

        for row_index, change in enumerate(changes):
            option_de = str(change.get("option") or "")
            option_en = self._tr(option_de)
            value_from = str(change.get("from") or "")
            value_to = str(change.get("to") or "")

            table.setItem(row_index, 0, QTableWidgetItem(option_de))
            table.setItem(row_index, 1, QTableWidgetItem(option_en))
            table.setItem(row_index, 2, QTableWidgetItem(self._de_en(value_from)))
            table.setItem(row_index, 3, QTableWidgetItem(self._de_en(value_to)))

        layout.addWidget(table, 1)
        layout.addWidget(QLabel(f"Łącznie zmian: {len(changes)}"))

        notes_label = QLabel("Notatka (opcjonalnie):")
        layout.addWidget(notes_label)
        self.notes_edit = QLineEdit()
        layout.addWidget(self.notes_edit)

        button_row = QHBoxLayout()
        button_row.addStretch()
        self.cancel_button = QPushButton("Anuluj")
        self.export_button = QPushButton("Eksportuj")
        self.cancel_button.clicked.connect(self.reject)
        self.export_button.clicked.connect(self.accept)
        button_row.addWidget(self.cancel_button)
        button_row.addWidget(self.export_button)
        layout.addLayout(button_row)

    def notes(self) -> str:
        return self.notes_edit.text().strip()


class HistoryCompareDialog(QDialog):
    def __init__(
        self,
        versions: list[dict],
        history_rows: list[dict] | None = None,
        current_vin: str = "",
        db: Database | None = None,
        translator: TrcTranslator | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Historia i porównanie")
        self.setModal(True)
        self._all_versions = versions
        self._all_history_rows = history_rows or []
        self._history_rows = list(self._all_history_rows)
        self._current_vin = (current_vin or "").strip().upper()
        self._db = db
        self._translator = translator
        self._build_ui()

    def _tr(self, keyword: str) -> str:
        text = str(keyword or "")
        if not text:
            return ""
        if self._translator is None:
            return text
        translated = self._translator.get_translation(text)
        return translated if translated else text

    def _bilingual_html(self, de_text: str, en_text: str) -> str:
        return (
            f"<span style='font-weight:700'>{html_escape(de_text)}</span> "
            f"<span style='color:#666666'>({html_escape(en_text)})</span>"
        )

    def _set_bilingual_value_cell(self, row: int, column: int, de_text: str, en_text: str, changed: bool):
        label = QLabel()
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setText(self._bilingual_html(de_text, en_text))
        label.setContentsMargins(4, 2, 4, 2)
        if changed:
            label.setStyleSheet("QLabel { background-color: #FFE0E0; }")
        else:
            label.setStyleSheet("QLabel { background-color: #FFFFFF; }")
        self.diff_table.setCellWidget(row, column, label)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Filtr historii:"))
        self.vin_filter_mode = QComboBox()
        self.vin_filter_mode.addItem("Wszystkie VIN", "all")
        self.vin_filter_mode.addItem("Tylko aktualny VIN", "current")
        self.vin_filter_mode.addItem("Wybrany VIN", "selected")
        filter_row.addWidget(self.vin_filter_mode)

        filter_row.addWidget(QLabel("VIN:"))
        self.vin_filter_combo = QComboBox()
        self.vin_filter_combo.setMinimumWidth(220)
        filter_row.addWidget(self.vin_filter_combo, 1)
        layout.addLayout(filter_row)

        self.vin_filter_mode.currentIndexChanged.connect(self._apply_history_filters)
        self.vin_filter_combo.currentIndexChanged.connect(self._apply_history_filters)

        self.history_table = QTableWidget()
        self.history_table.setColumnCount(6)
        self.history_table.setHorizontalHeaderLabels([
            "VIN",
            "Moduł",
            "Nr części",
            "Data prod.",
            "Zmiany",
            "Data eksportu",
        ])
        self.history_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.history_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.history_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.history_table.horizontalHeader().setStretchLastSection(True)
        self._fill_history_table(self._history_rows)
        layout.addWidget(self.history_table)

        selectors = QHBoxLayout()
        selectors.addWidget(QLabel("Wersja A"))
        self.version_a = QComboBox()
        selectors.addWidget(self.version_a, 1)
        selectors.addWidget(QLabel("Wersja B"))
        self.version_b = QComboBox()
        selectors.addWidget(self.version_b, 1)
        layout.addLayout(selectors)

        self._populate_vin_values()
        self._refresh_version_combos(self._all_versions)
        self._apply_history_filters()

        action_row = QHBoxLayout()
        self.compare_button = QPushButton("Porównaj")
        self.only_diffs = QCheckBox("Pokaż tylko różnice")
        self.only_diffs.setChecked(True)
        self.export_history_button = QPushButton("Eksportuj zapisane zmiany")
        self.compare_button.clicked.connect(self._compare)
        self.export_history_button.clicked.connect(self._export_selected_history_entry)
        action_row.addWidget(self.compare_button)
        action_row.addWidget(self.export_history_button)
        action_row.addWidget(self.only_diffs)
        action_row.addStretch()
        layout.addLayout(action_row)

        self.diff_table = QTableWidget()
        self.diff_table.setColumnCount(4)
        self.diff_table.setHorizontalHeaderLabels(["Funkcja DE", "Funkcja EN", "Plik 1 DE (EN)", "Plik 2 DE (EN)"])
        self.diff_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.diff_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.diff_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.diff_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.diff_table, 1)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _fill_history_table(self, rows: list[dict]):
        self.history_table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            vin_item = QTableWidgetItem(row.get("vin", ""))
            vin_item.setData(Qt.ItemDataRole.UserRole, row)
            module_item = QTableWidgetItem(row.get("module", ""))
            teilenummer_item = QTableWidgetItem(row.get("teilenummer", ""))
            production_item = QTableWidgetItem(row.get("production_date_display", ""))
            changes_item = QTableWidgetItem(row.get("changes_text", ""))
            exported_item = QTableWidgetItem(row.get("exported_at", ""))

            self.history_table.setItem(row_index, 0, vin_item)
            self.history_table.setItem(row_index, 1, module_item)
            self.history_table.setItem(row_index, 2, teilenummer_item)
            self.history_table.setItem(row_index, 3, production_item)
            self.history_table.setItem(row_index, 4, changes_item)
            self.history_table.setItem(row_index, 5, exported_item)

    def _selected_history_entry(self) -> dict | None:
        row_index = self.history_table.currentRow()
        if row_index < 0:
            return None
        item = self.history_table.item(row_index, 0)
        if not item:
            return None
        entry = item.data(Qt.ItemDataRole.UserRole)
        return entry if isinstance(entry, dict) else None

    def _safe_export_component(self, value: str) -> str:
        text = re.sub(r"[<>:\\/*?\"|]", "_", (value or "").strip())
        text = re.sub(r"\s+", " ", text).strip()
        return text or "UNKNOWN"

    def _build_export_folder_name(self, row: dict) -> str:
        model = self._safe_export_component(str(row.get("model") or row.get("module") or "MODEL"))
        vin = self._safe_export_component(str(row.get("vin") or "VIN"))
        export_date = str(row.get("exported_at") or "").strip()
        if export_date:
            export_date = export_date.split(" ", 1)[0]
        export_date = self._safe_export_component(export_date or "DATE")
        return f"{model} - {vin} - {export_date}"

    def _normalize_crlf(self, content: str) -> str:
        text = (content or "").replace("\r\n", "\n").replace("\r", "\n")
        return text.replace("\n", "\r\n")

    def _apply_changes_to_content(self, base_content: str, changes: list[dict], value_key: str) -> str:
        if not base_content.strip() or not changes:
            return base_content

        segments = parse_trc_content(base_content)
        replacements: dict[str, str] = {}
        for change in changes:
            option = str(change.get("option") or "").strip().upper()
            if not option:
                continue
            replacements[option] = str(change.get(value_key) or "")

        for segment in segments:
            if segment.kind != "option":
                continue
            replacement = replacements.get(segment.option.strip().upper())
            if replacement is not None:
                segment.value = replacement

        return format_trc_content(segments)

    def _write_pdf_report(self, pdf_path: Path, row: dict, changes: list[dict]) -> None:
        try:
            from reportlab.lib import colors
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
            from reportlab.lib.units import mm
            from reportlab.pdfgen import canvas
            from reportlab.pdfbase import pdfmetrics
            from reportlab.pdfbase.ttfonts import TTFont
            from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
        except Exception as exc:
            raise RuntimeError(f"Brak biblioteki reportlab: {exc}")

        def _find_font_path(candidates: list[Path]) -> Path | None:
            for candidate in candidates:
                if candidate.exists():
                    return candidate
            return None

        app_dir = Path(__file__).resolve().parent
        font_path = _find_font_path(
            [
                Path(os.path.join(str(app_dir), "fonts", "DejaVuSans.ttf")),
                Path(r"C:\Windows\Fonts\arial.ttf"),
                Path(r"C:\Windows\Fonts\calibri.ttf"),
            ]
        )
        bold_font_path = _find_font_path(
            [
                Path(os.path.join(str(app_dir), "fonts", "DejaVuSans-Bold.ttf")),
                Path(r"C:\Windows\Fonts\arialbd.ttf"),
                Path(r"C:\Windows\Fonts\calibrib.ttf"),
            ]
        )

        base_font_name = "Helvetica"
        bold_font_name = "Helvetica-Bold"
        if font_path is not None:
            base_font_name = "CustomFont"
            pdfmetrics.registerFont(TTFont(base_font_name, str(font_path)))
            if bold_font_path is not None:
                bold_font_name = "CustomFont-Bold"
                pdfmetrics.registerFont(TTFont(bold_font_name, str(bold_font_path)))
                try:
                    pdfmetrics.registerFontFamily(
                        base_font_name,
                        normalFont=base_font_name,
                        boldFont=bold_font_name,
                        italicFont=base_font_name,
                        boldItalicFont=bold_font_name,
                    )
                except Exception:
                    pass
            else:
                bold_font_name = base_font_name

        class NumberedCanvas(canvas.Canvas):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self._saved_page_states: list[dict] = []

            def showPage(self):
                self._saved_page_states.append(dict(self.__dict__))
                self._startPage()

            def save(self):
                total_pages = len(self._saved_page_states)
                for state in self._saved_page_states:
                    self.__dict__.update(state)
                    self.setFont(base_font_name, 8)
                    self.setFillColor(colors.HexColor("#4A4A4A"))
                    self.drawString(15 * mm, 8 * mm, "Wygenerowano przez BimmerDaten v0.2 - GPL-3.0")
                    self.drawRightString(195 * mm, 8 * mm, f"Strona {self._pageNumber} / {total_pages}")
                    super().showPage()
                super().save()

        doc = SimpleDocTemplate(
            str(pdf_path),
            pagesize=A4,
            leftMargin=40,
            rightMargin=40,
            topMargin=12 * mm,
            bottomMargin=16 * mm,
        )
        page_width = A4[0] - 80
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            "PdfTitle",
            parent=styles["Heading2"],
            fontName=bold_font_name,
            fontSize=12,
            textColor=colors.HexColor("#000000"),
            spaceAfter=0,
        )
        normal_style = ParagraphStyle(
            "PdfNormal",
            parent=styles["Normal"],
            fontName=base_font_name,
            fontSize=9,
            leading=11,
        )
        centered_style = ParagraphStyle(
            "PdfCentered",
            parent=normal_style,
            alignment=1,
        )
        changed_style = ParagraphStyle(
            "ChangedCell",
            parent=normal_style,
            fontName=bold_font_name,
            textColor=colors.HexColor("#00008B"),
            fontSize=8,
            leading=10,
            wordWrap="CJK",
        )
        header_cell_style = ParagraphStyle(
            "HeaderCell",
            parent=normal_style,
            fontName=bold_font_name,
            fontSize=8,
            leading=10,
            textColor=colors.white,
            alignment=1,
            wordWrap="CJK",
        )
        cell_style = ParagraphStyle(
            "Cell",
            parent=normal_style,
            fontName=base_font_name,
            fontSize=8,
            leading=10,
            wordWrap="CJK",
        )

        def make_cell(value: str, style: ParagraphStyle = cell_style) -> Paragraph:
            text = html_escape(str(value or "")).replace("\n", "<br/>")
            return Paragraph(text, style)

        module_name = str(row.get("module") or "")
        module_file = str(row.get("module_file") or "")
        module_display = module_name
        if module_name and module_file:
            module_display = f"{module_name} ({module_file})"
        elif module_file:
            module_display = module_file

        metadata_rows = [
            ["VIN:", str(row.get("vin") or "")],
            ["Model:", str(row.get("model") or "")],
            ["Moduł:", module_display],
            ["Nr części:", str(row.get("teilenummer") or "")],
            ["Data prod.:", str(row.get("production_date_display") or row.get("production_date") or "")],
            ["Data eksportu:", str(row.get("exported_at") or "")],
            ["Notatka:", str(row.get("notes") or "")],
        ]

        story = []
        header = Table(
            [[Paragraph("BimmerDaten - FSW/PSW Export Report", title_style), Paragraph("BMW", centered_style)]],
            colWidths=[doc.width * 0.82, doc.width * 0.18],
        )
        header.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#D4D0C8")),
                    ("BOX", (0, 0), (-1, -1), 0.75, colors.HexColor("#808080")),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        story.append(header)
        story.append(Spacer(1, 6))

        meta_data = [[make_cell(label), make_cell(value)] for label, value in metadata_rows]
        meta_table = Table(meta_data, colWidths=[page_width * 0.25, page_width * 0.75])
        meta_table.setStyle(
            TableStyle(
                [
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#909090")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F0F0F0")),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ]
            )
        )
        story.append(meta_table)
        story.append(Spacer(1, 8))

        if not changes:
            story.append(Spacer(1, 14))
            story.append(Paragraph("Brak zmian", centered_style))
        else:
            raw_col_widths = [
                page_width * 0.04,
                page_width * 0.18,
                page_width * 0.18,
                page_width * 0.12,
                page_width * 0.12,
                page_width * 0.12,
                page_width * 0.12,
            ]
            raw_col_widths[-1] = page_width - sum(raw_col_widths[:-1])

            header_row = [
                make_cell("Nr", header_cell_style),
                make_cell("Funkcja (DE)", header_cell_style),
                make_cell("Funkcja (EN)", header_cell_style),
                make_cell("Było (DE)", header_cell_style),
                make_cell("Było (EN)", header_cell_style),
                make_cell("Jest (DE)", header_cell_style),
                make_cell("Jest (EN)", header_cell_style),
            ]
            table_rows = [header_row]
            for index, change in enumerate(changes, start=1):
                option_de = str(change.get("option") or "")
                option_en = self._tr(option_de)
                before_de = str(change.get("from") or "")
                before_en = self._tr(before_de)
                after_de = str(change.get("to") or "")
                after_en = self._tr(after_de)
                table_rows.append(
                    [
                        make_cell(str(index)),
                        make_cell(option_de),
                        make_cell(option_en),
                        make_cell(before_de),
                        make_cell(before_en),
                        make_cell(after_de, changed_style),
                        make_cell(after_en, changed_style),
                    ]
                )

            changes_table = Table(
                table_rows,
                colWidths=raw_col_widths,
                repeatRows=1,
            )
            table_style_commands = [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4A4A4A")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), bold_font_name),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#A0A0A0")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 3),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ("WORDWRAP", (0, 0), (-1, -1), True),
            ]
            for row_index in range(1, len(table_rows)):
                bg_color = colors.white if row_index % 2 else colors.HexColor("#F5F5F5")
                table_style_commands.append(("BACKGROUND", (0, row_index), (-1, row_index), bg_color))
                table_style_commands.append(("FONTNAME", (5, row_index), (6, row_index), bold_font_name))
                table_style_commands.append(("TEXTCOLOR", (5, row_index), (6, row_index), colors.HexColor("#00008B")))

            changes_table.setStyle(TableStyle(table_style_commands))
            story.append(changes_table)

        doc.build(story, canvasmaker=NumberedCanvas)

    def _export_selected_history_entry(self):
        export_dialog = HistoryExportDialog(self._history_rows, db=self._db, parent=self)
        if export_dialog.exec() != QDialog.DialogCode.Accepted:
            return

        row = export_dialog.selected_row()
        if not row:
            QMessageBox.information(self, "Eksport", "Wybierz wpis historii do eksportu.")
            return

        export_root = QFileDialog.getExistingDirectory(self, "Wybierz folder eksportu", str(Path.home()))
        if not export_root:
            return

        folder_name = self._build_export_folder_name(row)
        export_dir = Path(export_root) / folder_name
        try:
            export_dir.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            QMessageBox.critical(self, "Eksport", f"Nie udało się utworzyć folderu eksportu:\n{exc}")
            return

        before_content = self._normalize_crlf(str(row.get("content_before") or ""))
        after_content = self._normalize_crlf(str(row.get("content_after") or ""))
        changes = list(row.get("changed_options") or [])
        if not before_content and after_content and changes:
            before_content = self._normalize_crlf(self._apply_changes_to_content(after_content, changes, "from"))
        elif not after_content and before_content and changes:
            after_content = self._normalize_crlf(self._apply_changes_to_content(before_content, changes, "to"))
        before_path = export_dir / "FSW_PSWbefore.TRC"
        after_path = export_dir / "FSW_PSWafter.TRC"
        pdf_path = export_dir / "FSW_PSW_report.pdf"

        try:
            before_path.write_text(before_content, encoding="utf-8", newline="")
            after_path.write_text(after_content, encoding="utf-8", newline="")
            self._write_pdf_report(pdf_path, row, changes)
        except Exception as exc:
            QMessageBox.critical(self, "Eksport", f"Nie udało się zapisać plików eksportu:\n{exc}")
            return

        QMessageBox.information(
            self,
            "Eksport",
            f"Zapisano do:\n{export_dir}\n\nFSW_PSWbefore.TRC\nFSW_PSWafter.TRC\nFSW_PSW_report.pdf",
        )

    def _populate_vin_values(self):
        selected = (self.vin_filter_combo.currentData() or "").strip().upper()
        vin_details: dict[str, tuple[str, str]] = {}
        for row in self._all_history_rows:
            vin = str(row.get("vin") or "").strip().upper()
            if not vin or vin in vin_details:
                continue
            model = str(row.get("model") or "").strip().upper()
            production_date = str(row.get("production_date_display") or "").strip()
            vin_details[vin] = (model, production_date)

        vins = sorted(vin_details.keys())
        self.vin_filter_combo.blockSignals(True)
        self.vin_filter_combo.clear()
        self.vin_filter_combo.addItem("(dowolny)", "")
        for vin in vins:
            model, production_date = vin_details.get(vin, ("", ""))
            date_text = production_date if production_date else "brak daty"
            model_text = model if model else "brak modelu"
            self.vin_filter_combo.addItem(f"{vin} | {model_text} | {date_text}", vin)

        if self._current_vin:
            index = self.vin_filter_combo.findData(self._current_vin)
            if index >= 0:
                self.vin_filter_combo.setCurrentIndex(index)
            else:
                self.vin_filter_combo.setCurrentIndex(0)
        elif selected:
            index = self.vin_filter_combo.findData(selected)
            self.vin_filter_combo.setCurrentIndex(index if index >= 0 else 0)
        else:
            self.vin_filter_combo.setCurrentIndex(0)
        self.vin_filter_combo.blockSignals(False)

    def _history_id(self, version: dict) -> int:
        source = str(version.get("source") or "")
        if not source.startswith("history:"):
            return 0
        try:
            return int(source.split(":", 1)[1])
        except Exception:
            return 0

    def _refresh_version_combos(self, versions: list[dict]):
        selected_a = self.version_a.currentData()
        selected_b = self.version_b.currentData()

        self.version_a.blockSignals(True)
        self.version_b.blockSignals(True)
        self.version_a.clear()
        self.version_b.clear()

        for version in versions:
            label = version.get("label", "Bez nazwy")
            self.version_a.addItem(label, version)
            self.version_b.addItem(label, version)

        if selected_a is not None:
            for idx in range(self.version_a.count()):
                data = self.version_a.itemData(idx)
                if data and data.get("source") == selected_a.get("source"):
                    self.version_a.setCurrentIndex(idx)
                    break
            else:
                if self.version_a.count() > 0:
                    self.version_a.setCurrentIndex(0)
        elif self.version_a.count() > 0:
            self.version_a.setCurrentIndex(0)

        if selected_b is not None:
            for idx in range(self.version_b.count()):
                data = self.version_b.itemData(idx)
                if data and data.get("source") == selected_b.get("source"):
                    self.version_b.setCurrentIndex(idx)
                    break
            else:
                if self.version_b.count() > 1:
                    self.version_b.setCurrentIndex(1)
                elif self.version_b.count() > 0:
                    self.version_b.setCurrentIndex(0)
        else:
            if self.version_b.count() > 1:
                self.version_b.setCurrentIndex(1)
            elif self.version_b.count() > 0:
                self.version_b.setCurrentIndex(0)

        self.version_a.blockSignals(False)
        self.version_b.blockSignals(False)

    def _apply_history_filters(self):
        mode = str(self.vin_filter_mode.currentData() or "all")
        selected_vin = str(self.vin_filter_combo.currentData() or "").strip().upper()

        target_vin = ""
        if mode == "current" and self._current_vin:
            target_vin = self._current_vin
        elif mode == "selected" and selected_vin:
            target_vin = selected_vin

        if target_vin:
            rows = [row for row in self._all_history_rows if str(row.get("vin") or "").strip().upper() == target_vin]
        else:
            rows = list(self._all_history_rows)

        self._history_rows = rows
        self._fill_history_table(rows)

        allowed_ids = {int(row.get("id") or 0) for row in rows}
        visible_versions: list[dict] = []
        for version in self._all_versions:
            source = str(version.get("source") or "")
            if source == "current":
                visible_versions.append(version)
                continue
            history_id = self._history_id(version)
            if history_id and history_id in allowed_ids:
                visible_versions.append(version)

        self._refresh_version_combos(visible_versions)

    def _compare(self):
        version_a = self.version_a.currentData() or {}
        version_b = self.version_b.currentData() or {}
        content_a = version_a.get("content", "")
        content_b = version_b.get("content", "")
        rows = compare_trc_contents(content_a, content_b)

        if self.only_diffs.isChecked():
            rows = [row for row in rows if not row[3]]

        self.diff_table.setRowCount(len(rows))
        for row_index, (option, value_a, value_b, same) in enumerate(rows):
            option_en = self._tr(option)
            value_a_en = self._tr(value_a)
            value_b_en = self._tr(value_b)

            option_item = QTableWidgetItem(option)
            option_en_item = QTableWidgetItem(option_en)

            if not same:
                for item in (option_item, option_en_item):
                    item.setBackground(QColor("#FFE0E0"))
                    item.setForeground(QColor("#000000"))
            else:
                for item in (option_item, option_en_item):
                    item.setBackground(QColor("#FFFFFF"))
                    item.setForeground(QColor("#000000"))

            self.diff_table.setItem(row_index, 0, option_item)
            self.diff_table.setItem(row_index, 1, option_en_item)
            self._set_bilingual_value_cell(row_index, 2, value_a, value_a_en, not same)
            self._set_bilingual_value_cell(row_index, 3, value_b, value_b_en, not same)

        self.diff_table.resizeColumnsToContents()


class HistoryExportDialog(QDialog):
    def __init__(self, rows: list[dict], db: Database | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Eksport zapisanych zmian")
        self.setModal(True)
        self._rows = list(rows or [])
        self._db = db
        self._selected_row: dict | None = None
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        info_label = QLabel("Wybierz zapis z bazy danych do eksportu. Eksport dotyczy tylko danych zapisanych w DB.")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        self.rows_table = QTableWidget()
        self.rows_table.setColumnCount(7)
        self.rows_table.setHorizontalHeaderLabels([
            "VIN",
            "Model",
            "Moduł",
            "Nr części",
            "Data prod.",
            "Zmiany",
            "Data eksportu",
        ])
        self.rows_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.rows_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.rows_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.rows_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.rows_table.horizontalHeader().setStretchLastSection(True)
        self.rows_table.itemSelectionChanged.connect(self._update_preview)
        layout.addWidget(self.rows_table, 1)

        self.preview = QTextBrowser()
        self.preview.setMinimumHeight(160)
        layout.addWidget(self.preview)

        button_row = QHBoxLayout()
        button_row.addStretch()
        self.cancel_button = QPushButton("Anuluj")
        self.export_button = QPushButton("Eksportuj")
        self.cancel_button.clicked.connect(self.reject)
        self.export_button.clicked.connect(self._accept_selection)
        button_row.addWidget(self.cancel_button)
        button_row.addWidget(self.export_button)
        layout.addLayout(button_row)

        self._fill_rows()
        if self.rows_table.rowCount() > 0:
            self.rows_table.setCurrentCell(0, 0)
        else:
            self.preview.setPlainText("Brak zapisanych zmian w bazie danych.")
            self.export_button.setEnabled(False)

    def _fill_rows(self):
        self.rows_table.setRowCount(len(self._rows))
        for row_index, row in enumerate(self._rows):
            values = [
                str(row.get("vin") or ""),
                str(row.get("model") or ""),
                str(row.get("module") or ""),
                str(row.get("teilenummer") or ""),
                str(row.get("production_date_display") or ""),
                str(row.get("changes_text") or ""),
                str(row.get("exported_at") or ""),
            ]
            for column_index, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, row)
                self.rows_table.setItem(row_index, column_index, item)

    def _current_row(self) -> dict | None:
        row_index = self.rows_table.currentRow()
        if row_index < 0 or row_index >= len(self._rows):
            return None
        return self._rows[row_index]

    def _current_full_row(self) -> dict | None:
        row = self._current_row()
        if not row:
            return None

        record_id = int(row.get("id") or 0)
        if self._db and record_id > 0:
            full_row = self._db.get_trc_history_by_id(record_id)
            if full_row:
                production_display = str(row.get("production_date_display") or "").strip()
                if production_display and not full_row.get("production_date_display"):
                    full_row["production_date_display"] = production_display
                return full_row

        return row

    def _update_preview(self):
        row = self._current_full_row()
        if not row:
            self.preview.setPlainText("Brak wyboru.")
            return

        before_content = str(row.get("content_before") or "")
        after_content = str(row.get("content_after") or "")
        changes = row.get("changed_options") or []
        notes = str(row.get("notes") or "").strip()
        change_lines = []
        for change in changes:
            option = str(change.get("option") or "")
            value_from = str(change.get("from") or "")
            value_to = str(change.get("to") or "")
            change_lines.append(f"- {option}: {value_from} -> {value_to}")
        lines = [
            f"VIN: {row.get('vin', '')}",
            f"Model: {row.get('model', '')}",
            f"Moduł: {row.get('module', '')}",
            f"Nr części: {row.get('teilenummer', '')}",
            f"Data prod.: {row.get('production_date_display', '')}",
            f"Data eksportu: {row.get('exported_at', '')}",
            f"Notatka: {notes or 'brak'}",
            f"Liczba zmian: {len(change_lines)}",
            "",
            "Zmiany z changed_options:",
        ]

        lines.extend(change_lines or ["Brak zapisanych zmian."])
        if before_content or after_content:
            lines.extend([
                "",
                "Dane TRC zapisane w DB:",
                f"content_before: {len(before_content)} znaków",
                f"content_after: {len(after_content)} znaków",
            ])

        self.preview.setPlainText("\n".join(lines))

    def _accept_selection(self):
        row = self._current_full_row()
        if not row:
            QMessageBox.information(self, "Eksport", "Wybierz wpis z listy.")
            return
        self._selected_row = row
        self.accept()

    def selected_row(self) -> dict | None:
        return self._selected_row


class ModuleDetectDialog(QDialog):
    def __init__(self, candidates: list[tuple[str, float]], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Wykryte moduły")
        self.setModal(True)
        self._selected: tuple[str, float] | None = None
        self._build_ui(candidates[:3])

    def _build_ui(self, candidates: list[tuple[str, float]]):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        layout.addWidget(QLabel("Wybierz wykryty moduł:"))
        self.list_widget = QListWidget()
        for module_name, ratio in candidates:
            item = QListWidgetItem(f"{module_name} — {int(round(ratio * 100))}%")
            item.setData(Qt.ItemDataRole.UserRole, (module_name, ratio))
            self.list_widget.addItem(item)

        if self.list_widget.count() > 0:
            self.list_widget.setCurrentRow(0)
        self.list_widget.itemDoubleClicked.connect(lambda _: self._accept_selection())
        layout.addWidget(self.list_widget, 1)

        buttons = QDialogButtonBox()
        select_button = QPushButton("Wybierz")
        cancel_button = QPushButton("Anuluj")
        select_button.clicked.connect(self._accept_selection)
        cancel_button.clicked.connect(self.reject)
        buttons.addButton(select_button, QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.addButton(cancel_button, QDialogButtonBox.ButtonRole.RejectRole)
        layout.addWidget(buttons)

    def _accept_selection(self):
        item = self.list_widget.currentItem()
        if not item:
            return
        self._selected = item.data(Qt.ItemDataRole.UserRole)
        self.accept()

    def selected(self) -> tuple[str, float] | None:
        return self._selected


class ModuleDetectWorker(QObject):
    finished = pyqtSignal(list)
    failed = pyqtSignal(str)

    def __init__(self, trc_options: set[str], daten_path: str, model: str):
        super().__init__()
        self._trc_options = set(trc_options)
        self._daten_path = daten_path
        self._model = model

    def run(self):
        try:
            candidates = detect_module_from_trc(self._trc_options, self._daten_path, self._model)
            self.finished.emit(candidates)
        except Exception as exc:
            self.failed.emit(str(exc))


class CodingPanel(QWidget):
    def __init__(self, db: Database | None = None, parent=None):
        super().__init__(parent)
        self._db = db
        self._settings = QSettings("BimmerDaten", "BimmerDaten")
        self._paths = self._load_paths()
        self._translator = TrcTranslator(self._paths.translations_path)
        self._segments: list[TrcSegment] = []
        self._option_rows: list[int] = []
        self._row_editable: dict[int, bool] = {}
        self._module_options: set[str] = set()
        self._module_options_cache: dict[tuple[str, str], set[str]] = {}
        self._module_option_info: dict[str, dict] = {}
        self._module_loaded = False
        self._table_entries: list[dict] = []
        self._available_models: list[str] = []
        self._modules_by_model: dict[str, list[str]] = {}
        self._current_model = ""
        self._current_module = ""
        self._current_module_file = ""
        self._current_trc_content = ""
        self._baseline_content = ""
        self._trc_loaded = False
        self._detect_thread: QThread | None = None
        self._detect_worker: ModuleDetectWorker | None = None
        self._filter_text = ""
        self._column_min_widths: dict[int, int] = {}
        self._ncs_profile_status: dict = {
            "found": False,
            "profile_name": "",
            "can_read": False,
            "can_write": False,
            "profile_path": "",
        }
        self._setup_ui()
        self._refresh_warning_state()
        self._refresh_ncs_profile_status(initial=True)
        self.reload_model_tree()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        left_box = QWidget()
        left_box.setMinimumWidth(250)
        left_box.setMaximumWidth(300)
        left_layout = QVBoxLayout(left_box)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(4)

        self.path_warning_label = QLabel("Brak wymaganych ścieżek")
        self.path_warning_label.setWordWrap(True)
        self.path_warning_label.setStyleSheet(
            "background-color: #ffff99; color: #000000; border: 1px solid #808080; padding: 4px;"
        )
        self.path_warning_label.setVisible(False)
        left_layout.addWidget(self.path_warning_label)

        self.change_path_button = QPushButton("Zmień ścieżkę")
        self.change_path_button.clicked.connect(self._open_path_config_dialog)
        left_layout.addWidget(self.change_path_button)

        left_layout.addWidget(QLabel("Model:"))
        self.model_combo = QComboBox()
        self.model_combo.currentIndexChanged.connect(self._on_model_changed)
        left_layout.addWidget(self.model_combo)

        left_layout.addWidget(QLabel("Moduł:"))
        self.module_combo = QComboBox()
        self.module_combo.currentIndexChanged.connect(self._on_module_changed)
        left_layout.addWidget(self.module_combo)

        self.detect_module_button = QPushButton("🔍 Wykryj moduł")
        self.detect_module_button.clicked.connect(self.detect_module_from_current_trc)
        self.detect_module_button.setEnabled(False)
        left_layout.addWidget(self.detect_module_button)

        self.detect_progress = QProgressBar()
        self.detect_progress.setRange(0, 0)
        self.detect_progress.setVisible(False)
        self.detect_progress.setTextVisible(True)
        self.detect_progress.setFormat("Szukam modułu...")
        left_layout.addWidget(self.detect_progress)

        self.load_trc_button = QPushButton("📂 Załaduj TRC")
        self.load_trc_button.clicked.connect(self.load_selected_trc)
        self.load_trc_button.setEnabled(True)
        left_layout.addWidget(self.load_trc_button)
        left_layout.addStretch(1)

        self.refresh_button = QPushButton("🔄 Odśwież")
        self.refresh_button.clicked.connect(self.reload_current_trc)
        left_layout.addWidget(self.refresh_button)

        self.history_button = QPushButton("📂 Historia")
        self.history_button.clicked.connect(self.open_history_dialog)
        left_layout.addWidget(self.history_button)

        right_box = QWidget()
        right_layout = QVBoxLayout(right_box)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(4)

        self.profile_status_frame = QFrame()
        self.profile_status_frame.setFrameShape(QFrame.Shape.Panel)
        self.profile_status_frame.setFrameShadow(QFrame.Shadow.Raised)
        self.profile_status_frame.setStyleSheet("background-color: #FF8C00; color: #000000; border: 1px solid #808080;")
        profile_status_layout = QHBoxLayout(self.profile_status_frame)
        profile_status_layout.setContentsMargins(6, 4, 6, 4)
        profile_status_layout.setSpacing(8)

        self.profile_status_label = QWidget()
        self.profile_status_label_layout = QHBoxLayout(self.profile_status_label)
        self.profile_status_label_layout.setContentsMargins(0, 0, 0, 0)
        self.profile_status_label_layout.setSpacing(6)
        self.profile_status_label_layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.profile_status_label.setStyleSheet("background: transparent;")
        profile_status_layout.addWidget(self.profile_status_label, 1)

        self.profile_status_button = QPushButton("📁 Zmień folder")
        self.profile_status_button.clicked.connect(self._choose_ncs_profile_file)
        profile_status_layout.addWidget(self.profile_status_button)

        right_layout.addWidget(self.profile_status_frame)

        splitter = QSplitter(Qt.Orientation.Vertical)

        table_widget = QWidget()
        table_layout = QVBoxLayout(table_widget)
        table_layout.setContentsMargins(0, 0, 0, 0)
        table_layout.setSpacing(4)

        filter_row = QHBoxLayout()
        filter_row.setContentsMargins(0, 0, 0, 0)
        filter_row.setSpacing(4)

        self.search_icon_label = QLabel("🔍")
        self.search_icon_label.setFixedWidth(18)
        filter_row.addWidget(self.search_icon_label)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Filtruj opcje... (nazwa lub tłumaczenie)")
        self.search_edit.textChanged.connect(self._on_filter_text_changed)
        filter_row.addWidget(self.search_edit, 1)

        self.clear_search_button = QPushButton("✕")
        self.clear_search_button.setFixedWidth(24)
        self.clear_search_button.setToolTip("Wyczyść filtr")
        self.clear_search_button.clicked.connect(self.search_edit.clear)
        self.clear_search_button.setEnabled(False)
        filter_row.addWidget(self.clear_search_button)

        table_layout.addLayout(filter_row)

        self.context_label = QLabel("Wybierz model, następnie załaduj TRC")
        self.context_label.setWordWrap(True)
        table_layout.addWidget(self.context_label)

        self.trc_table = QTableWidget()
        self.trc_table.setColumnCount(6)
        self.trc_table.setHorizontalHeaderLabels([
            "Nr",
            "Opcja",
            "Tłumaczenie",
            "Wartość",
            "Tłumaczenie wartości",
            "Zmieniono",
        ])
        self.trc_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.trc_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.trc_table.setWordWrap(True)
        self.trc_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.trc_table.horizontalHeader().setStretchLastSection(False)
        self.trc_table.horizontalHeader().sectionResized.connect(self._on_table_section_resized)
        table_layout.addWidget(self.trc_table, 1)
        splitter.addWidget(table_widget)

        toolbar_widget = QWidget()
        toolbar_widget.setMaximumHeight(72)
        toolbar_layout = QHBoxLayout(toolbar_widget)
        toolbar_layout.setContentsMargins(0, 0, 0, 0)
        toolbar_layout.setSpacing(4)

        self.export_man_button = QPushButton("📤 Export .MAN")
        self.export_trc_button = QPushButton("📤 Export .TRC")
        self.change_count_label = QLabel("Zmieniono: 0 opcji")

        self.export_man_button.clicked.connect(lambda: self.export_current_file(".MAN"))
        self.export_trc_button.clicked.connect(lambda: self.export_current_file(".TRC"))

        toolbar_layout.addWidget(self.export_man_button)
        toolbar_layout.addWidget(self.export_trc_button)
        toolbar_layout.addStretch()
        toolbar_layout.addWidget(self.change_count_label)

        splitter.addWidget(toolbar_widget)
        splitter.setSizes([520, 90])
        right_layout.addWidget(splitter, 1)

        layout.addWidget(left_box)
        layout.addWidget(right_box, 1)

    def showEvent(self, event):
        super().showEvent(event)
        self._refresh_ncs_profile_status()

    def _load_saved_profile_path(self) -> str:
        return str(self._settings.value("coding/ncs_profile_path", "", type=str) or "").strip()

    def _save_profile_path(self, profile_path: str) -> None:
        folder = str(Path(profile_path)) if Path(profile_path).is_dir() else str(Path(profile_path).parent)
        self._settings.setValue("coding/ncs_profile_path", folder or "")

    def _set_profile_status_ui(self, profile_info: dict):
        found = bool(profile_info.get("found"))
        profiles = profile_info.get("profiles") or []

        while self.profile_status_label_layout.count():
            item = self.profile_status_label_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        if not found:
            self.profile_status_frame.setStyleSheet("background-color: #D9D9D9; color: #000000; border: 1px solid #808080;")
            no_profiles_label = QLabel("Brak profili .PFL w katalogu")
            no_profiles_label.setStyleSheet("color: #606060; font-weight: bold; background: transparent;")
            no_profiles_label.setWordWrap(False)
            self.profile_status_label_layout.addWidget(no_profiles_label)
            self.profile_status_frame.setFixedHeight(no_profiles_label.sizeHint().height() + 10)
            return

        chip_widgets = []
        for profile in profiles:
            profile_name = str(profile.get("profile_name") or "").strip() or "BRAK"
            can_write = bool(profile.get("can_write"))
            can_read = bool(profile.get("can_read"))
            color = "#1F8A1F" if can_write else "#C00000"
            chip = QPushButton(profile_name)
            chip.setStyleSheet(
                "QPushButton {"
                f"background-color: {color};"
                "color: #FFFFFF;"
                "border: 1px solid #808080;"
                "border-radius: 3px;"
                "padding: 1px 8px;"
                "font-weight: bold;"
                "text-align: center;"
                "}"
                "QPushButton:hover {"
                f"background-color: {'#228B22' if can_write else '#A00000'};"
                "}"
            )
            chip.setFlat(False)
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.setToolTip(f"{profile.get('profile_path', '')}\nKliknij, aby wyświetlić szczegóły")
            chip.setFixedHeight(chip.sizeHint().height())
            chip.clicked.connect(lambda checked, p=profile: self._show_profile_info(p))
            chip_widgets.append(chip)
            self.profile_status_label_layout.addWidget(chip)

        if not chip_widgets:
            self.profile_status_frame.setStyleSheet("background-color: #D9D9D9; color: #000000; border: 1px solid #808080;")
            fallback_label = QLabel("Brak profili .PFL w katalogu")
            fallback_label.setStyleSheet("color: #606060; font-weight: bold; background: transparent;")
            fallback_label.setWordWrap(False)
            self.profile_status_label_layout.addWidget(fallback_label)
            self.profile_status_frame.setFixedHeight(fallback_label.sizeHint().height() + 10)
            return

        self.profile_status_label_layout.addStretch(1)
        self.profile_status_frame.setStyleSheet("background-color: #D9D9D9; color: #000000; border: 1px solid #808080;")
        tallest_chip = max(chip.sizeHint().height() for chip in chip_widgets)
        self.profile_status_frame.setFixedHeight(tallest_chip + 10)

    def _show_profile_info(self, profile: dict):
        profile_name = str(profile.get("profile_name") or "").strip() or "BRAK"
        profile_path = str(profile.get("profile_path") or "")
        can_read = bool(profile.get("can_read"))
        can_write = bool(profile.get("can_write"))
        
        if can_write:
            status = "✅ Pełny dostęp (odczyt + zapis)"
            color = "#228B22"
        elif can_read:
            status = "🔒 Tylko odczyt"
            color = "#FFD700"
        else:
            status = "❌ Brak wymaganych uprawnień"
            color = "#FF8C00"
        
        dialog = QMessageBox(self)
        dialog.setWindowTitle("Informacje o profilu NCS Expert")
        dialog.setIcon(QMessageBox.Icon.Information)
        dialog.setText(
            f"Profil: <b>{html_escape(profile_name)}</b>\n\n"
            f"Ścieżka:\n{html_escape(profile_path)}\n\n"
            f"Status: {status}"
        )
        dialog.setStyleSheet(f"QMessageBox {{ background-color: #FFFFFF; }}")
        ok_button = dialog.addButton("OK", QMessageBox.ButtonRole.AcceptRole)
        dialog.exec()

    def _refresh_ncs_profile_status(self, initial: bool = False):
        profile_path = self._load_saved_profile_path()
        if initial and not profile_path:
            profile_path = "C:\\NCSEXPER\\"

        profile_info = check_ncs_profile(profile_path)
        self._ncs_profile_status = profile_info
        self._set_profile_status_ui(profile_info)

    def _choose_ncs_profile_file(self):
        saved_folder = self._load_saved_profile_path()
        start_dir = saved_folder or "C:\\NCSEXPER\\"
        start_dir = str(Path(start_dir)) if Path(start_dir).is_dir() else str(Path(start_dir).parent)
        
        selected_folder = QFileDialog.getExistingDirectory(
            self,
            "Wybierz folder z profilami NCS Expert",
            start_dir,
            QFileDialog.Option.ShowDirsOnly,
        )
        if not selected_folder:
            return

        self._save_profile_path(selected_folder)
        self._ncs_profile_status = check_ncs_profile(selected_folder)
        self._set_profile_status_ui(self._ncs_profile_status)

    def _warn_if_profile_blocks_write(self) -> bool:
        if bool(self._ncs_profile_status.get("can_write")):
            return True

        dialog = QMessageBox(self)
        dialog.setWindowTitle("Ostrzeżenie NCS Expert")
        dialog.setIcon(QMessageBox.Icon.Warning)
        dialog.setText(
            "⚠️ Aktywny profil NCS Expert nie pozwala na zapis.\n\n"
            "Aby wgrać zmiany do modułu, załaduj profil z pełnym dostępem\n"
            "(np. NCSDUMMY4.PFL lub EXPERTENMODE.PFL).\n"
            "Czy mimo to wyeksportować plik .MAN?"
        )
        yes_button = dialog.addButton("Tak, eksportuj", QMessageBox.ButtonRole.AcceptRole)
        cancel_button = dialog.addButton("Anuluj", QMessageBox.ButtonRole.RejectRole)
        dialog.exec()
        return dialog.clickedButton() == yes_button and cancel_button is not None

    def _load_paths(self) -> CodingPaths:
        config = _read_json_config()
        paths = CodingPaths()
        paths.trc_path = str(_candidate_path(DEFAULT_TRC_PATH, config.get("trc_path")))
        paths.daten_path = str(_candidate_path(DEFAULT_DATEN_PATH, config.get("daten_path")))
        paths.translations_path = str(_candidate_path(DEFAULT_TRANSLATIONS_PATH, config.get("translations_path")))
        return paths

    def _refresh_warning_state(self):
        missing = []
        if not Path(self._paths.trc_path).exists():
            missing.append("TRC")
        if not Path(self._paths.daten_path).exists():
            missing.append("DATEN")
        if not Path(self._paths.translations_path).exists():
            missing.append("Translations.csv")

        if missing:
            self.path_warning_label.setText("Brak ścieżek: " + ", ".join(missing))
            self.path_warning_label.setVisible(True)
        else:
            self.path_warning_label.setVisible(False)

    def _open_path_config_dialog(self):
        dialog = PathConfigDialog(self._paths, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        self._paths = dialog.get_paths()
        _write_json_config({
            "trc_path": self._paths.trc_path,
            "daten_path": self._paths.daten_path,
            "translations_path": self._paths.translations_path,
        })
        self._translator = TrcTranslator(self._paths.translations_path)
        self._refresh_warning_state()
        self.reload_model_tree(select_first=True)
        self.reload_current_trc()

    def reload_model_tree(self, select_first: bool = True):
        self.model_combo.blockSignals(True)
        self.module_combo.blockSignals(True)
        self.model_combo.clear()
        self.module_combo.clear()
        self._available_models = []
        self._modules_by_model.clear()
        self._current_model = ""
        self._current_module = ""
        self._current_module_file = ""
        self._module_options = set()
        self._module_option_info = {}
        self._module_loaded = False
        self._trc_loaded = False
        self.model_combo.setEnabled(False)
        self.module_combo.setEnabled(False)
        self.load_trc_button.setEnabled(True)
        self.detect_module_button.setEnabled(False)

        daten_path = Path(self._paths.daten_path)
        if daten_path.exists():
            for folder in sorted([item for item in daten_path.iterdir() if item.is_dir()], key=lambda p: p.name.upper()):
                modules = sorted(
                    [
                        entry.name
                        for entry in folder.iterdir()
                        if entry.is_file()
                        and len(entry.suffix) == 4
                        and entry.suffix[1:2].upper() == "C"
                        and entry.suffix[2:].isdigit()
                    ],
                    key=str.upper,
                )
                if not modules:
                    continue
                model_name = folder.name.upper()
                self._available_models.append(model_name)
                self._modules_by_model[model_name] = modules
                self.model_combo.addItem(model_name)

        self.model_combo.blockSignals(False)
        self.module_combo.blockSignals(False)

        if not self._available_models:
            self.context_label.setText("Nie znaleziono folderów chassis z plikami .Cxx w DATEN")
            self._module_options = set()
            self._render_table()
            self.load_trc_button.setEnabled(False)
            return

        if select_first:
            self.model_combo.setCurrentIndex(0)
        else:
            self.model_combo.setCurrentIndex(-1)
            self.context_label.setText("Najpierw załaduj TRC, potem wybierz model")

    def _on_model_changed(self, index: int):
        if index < 0:
            return
        model_name = self.model_combo.currentText().strip().upper()
        self._current_model = model_name
        self._current_module = ""
        self._current_module_file = ""
        self._module_options = set()
        self._module_option_info = {}
        self._module_loaded = False
        self._row_editable = {row_index: True for row_index in range(len(self._option_rows))}
        if self._segments:
            self._render_table()
        self.module_combo.blockSignals(True)
        self.module_combo.clear()
        self.module_combo.addItem("-- wybierz moduł --", "")
        for module_file in self._modules_by_model.get(model_name, []):
            self.module_combo.addItem(module_file, module_file)
        self.module_combo.blockSignals(False)

        self.module_combo.setCurrentIndex(0)
        self.load_trc_button.setEnabled(True)
        self.detect_module_button.setEnabled(self._trc_loaded)
        if self._trc_loaded:
            self.context_label.setText("TRC załadowane. Wybierz moduł lub użyj wykrywania, aby dopasować opcje.")
        else:
            self.context_label.setText(f"Model: {model_name} | Krok 2: kliknij '📂 Załaduj TRC'")

    def _on_module_changed(self, index: int):
        if index < 0 or not self._current_model:
            return
        module_file = (self.module_combo.currentData() or self.module_combo.currentText() or "").strip()
        if not module_file or module_file.startswith("--"):
            self._current_module = ""
            self._current_module_file = ""
            self._module_options = set()
            self._module_option_info = {}
            self._module_loaded = False
            if self._segments:
                self._row_editable = {row_index: True for row_index in range(len(self._option_rows))}
                self._render_table()
                self.context_label.setText("TRC załadowane bez filtrowania modułu.")
            return

        self._current_module_file = module_file
        self._current_module = module_file.split(".", 1)[0].upper() if module_file else ""

        cache_key = (self._current_model, module_file.upper())
        if cache_key in self._module_options_cache:
            self._module_options = self._module_options_cache[cache_key]
            parsed_options = []
        else:
            parsed_options = load_module(self._paths.daten_path, self._current_model, module_file)
            option_names = {
                str(item.get("name", "")).strip().upper()
                for item in parsed_options
                if str(item.get("name", "")).strip()
            }
            self._module_options_cache[cache_key] = option_names
            self._module_options = option_names

        # Always refresh option info from parsed module so editors can show allowed values and groups.
        self._module_option_info = {}
        if not parsed_options:
            parsed_options = load_module(self._paths.daten_path, self._current_model, module_file)
        for option in parsed_options:
            option_name = str(option.get("name", "")).strip().upper()
            params = option.get("params") or []
            if option_name:
                self._module_option_info[option_name] = {
                    "params": list(params),
                    "group": str(option.get("group", "")).strip(),
                }
        self._module_loaded = bool(self._module_option_info)

        if self._segments:
            self._apply_module_filter_to_table()
        else:
            self.context_label.setText(f"Model: {self._current_model} | Moduł: {self._current_module_file}")

    def detect_module_from_current_trc(self):
        if not self._current_model:
            QMessageBox.information(self, "Wykrywanie", "Najpierw wybierz model.")
            return
        if not self._trc_loaded:
            QMessageBox.information(self, "Wykrywanie", "Najpierw załaduj FSW_PSW.TRC.")
            return

        if self._detect_thread and self._detect_thread.isRunning():
            return

        trc_path = Path(self._paths.trc_path)
        trc_map = parse_trc_file(str(trc_path))
        if not trc_map:
            QMessageBox.information(self, "Wykrywanie", "Nie udało się odczytać opcji z FSW_PSW.TRC.")
            return

        self.detect_module_button.setEnabled(False)
        self.load_trc_button.setEnabled(False)
        self.detect_progress.setVisible(True)
        self.context_label.setText("Szukam modułu...")
        QApplication.processEvents()

        self._detect_thread = QThread(self)
        self._detect_worker = ModuleDetectWorker(set(trc_map.keys()), self._paths.daten_path, self._current_model)
        self._detect_worker.moveToThread(self._detect_thread)

        self._detect_thread.started.connect(self._detect_worker.run)
        self._detect_worker.finished.connect(self._on_detect_finished)
        self._detect_worker.failed.connect(self._on_detect_failed)
        self._detect_worker.finished.connect(self._detect_thread.quit)
        self._detect_worker.failed.connect(self._detect_thread.quit)
        self._detect_thread.finished.connect(self._cleanup_detect_worker)

        self._detect_thread.start()

    def _on_detect_finished(self, candidates: list[tuple[str, float]]):
        self._stop_detect_ui()
        if not candidates:
            QMessageBox.information(self, "Wykrywanie", "Brak kandydatów powyżej 30% dopasowania.")
            return

        dialog = ModuleDetectDialog(candidates, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        selected = dialog.selected()
        if not selected:
            return

        module_file, ratio = selected
        module_index = self.module_combo.findText(module_file)
        if module_index >= 0:
            self.module_combo.setCurrentIndex(module_index)

        self.context_label.setText(f"Wykryto moduł: {module_file} ({int(round(ratio * 100))}%).")

    def _on_detect_failed(self, message: str):
        self._stop_detect_ui()
        QMessageBox.warning(self, "Wykrywanie", f"Błąd podczas wyszukiwania modułu:\n{message}")

    def _stop_detect_ui(self):
        self.detect_progress.setVisible(False)
        self.detect_module_button.setEnabled(True)
        self.load_trc_button.setEnabled(True)

    def _cleanup_detect_worker(self):
        if self._detect_worker:
            self._detect_worker.deleteLater()
            self._detect_worker = None
        if self._detect_thread:
            self._detect_thread.deleteLater()
            self._detect_thread = None

    def load_selected_trc(self):
        self.load_trc_from_path(Path(self._paths.trc_path))

    def reload_current_trc(self):
        self._refresh_warning_state()
        self.load_trc_from_path(Path(self._paths.trc_path))

    def load_trc_from_path(self, trc_path: Path):
        if not trc_path.exists():
            self._segments = []
            self._option_rows = []
            self._row_editable = {}
            self._table_entries = []
            self._current_trc_content = ""
            self._baseline_content = ""
            self._trc_loaded = False
            self.model_combo.setEnabled(False)
            self.module_combo.setEnabled(False)
            self.detect_module_button.setEnabled(False)
            self._render_table()
            self.context_label.setText(f"Nie znaleziono pliku: {trc_path}")
            return

        content = read_text_file(trc_path)
        self._current_trc_content = content
        self._baseline_content = content
        self._segments = parse_trc_content(content)
        self._option_rows = [index for index, segment in enumerate(self._segments) if segment.kind == "option"]
        self._trc_loaded = True
        self.model_combo.setEnabled(True)
        self.module_combo.setEnabled(True)
        if self.model_combo.currentIndex() < 0 and self.model_combo.count() > 0:
            self.model_combo.setCurrentIndex(0)
        self.detect_module_button.setEnabled(bool(self._current_model))

        if self._current_module_file:
            self._apply_module_filter_to_table()
        else:
            self._row_editable = {row_index: True for row_index in range(len(self._option_rows))}
            self._render_table()
            self.context_label.setText(
                f"Załadowano TRC ({len(self._option_rows)} opcji). Wybierz model i moduł lub użyj '🔍 Wykryj moduł'."
            )

    def _apply_module_filter_to_table(self):
        self._row_editable = {}
        matched = 0
        total = len(self._option_rows)
        for row_index, segment_index in enumerate(self._option_rows):
            option_name = self._segments[segment_index].option.strip().upper()
            editable = option_name in self._module_options if self._module_loaded else True
            self._row_editable[row_index] = editable
            if editable:
                matched += 1

        percentage = int(round((matched / total) * 100)) if total else 0
        self._render_table()

        if self._module_loaded:
            self.context_label.setText(
                f"Załadowano: {self._current_module_file} — {matched}/{total} opcji dopasowanych ({percentage}%)"
            )
        else:
            self.context_label.setText(
                f"Model: {self._current_model} | Moduł: {self._current_module_file} — brak opisu .Cxx"
            )

    def _render_table(self):
        self._table_entries = self._build_table_entries()
        self.trc_table.setRowCount(len(self._table_entries))
        self.trc_table.clearContents()
        self.trc_table.clearSpans()

        for row_index, entry in enumerate(self._table_entries):
            if entry.get("kind") == "group":
                group_name = entry.get("group", "")
                header_text = f"── {group_name} ──"
                header_item = QTableWidgetItem(header_text)
                header_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
                header_item.setBackground(QColor("#D4D0C8"))
                header_item.setForeground(QColor("#000000"))
                font = header_item.font()
                font.setBold(True)
                header_item.setFont(font)
                self.trc_table.setItem(row_index, 0, header_item)
                self.trc_table.setSpan(row_index, 0, 1, self.trc_table.columnCount())
                self.trc_table.setRowHeight(row_index, max(self.trc_table.rowHeight(row_index), 22))
                continue

            segment_index = entry["segment_index"]
            option_index = entry["option_index"]
            segment = self._segments[segment_index]
            editable = self._row_editable.get(option_index, True)

            number_item = QTableWidgetItem(str(option_index + 1))
            number_item.setFlags(number_item.flags() & ~Qt.ItemFlag.ItemIsEditable)

            option_item = QTableWidgetItem(segment.option)
            option_item.setFlags(option_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            translation_item = QTableWidgetItem(self._translator.translate(segment.option))
            translation_item.setFlags(translation_item.flags() & ~Qt.ItemFlag.ItemIsEditable)

            option_name_raw = segment.option.strip()
            option_name_upper = option_name_raw.upper()
            params = []
            if self._module_loaded:
                option_info = self._module_option_info.get(option_name_upper, {})
                params = option_info.get("params", []) or []

            if self._module_loaded:
                if editable and params:
                    value_editor = self._build_value_combo(row_index, segment.value, params)
                    self.trc_table.setCellWidget(row_index, 3, value_editor)
                else:
                    value_item = QTableWidgetItem(segment.value)
                    value_item.setFlags(value_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    value_item.setForeground(QColor("#888888"))
                    self.trc_table.setItem(row_index, 3, value_item)
            else:
                value_editor = QLineEdit(segment.value)
                value_editor.textChanged.connect(lambda text, row=row_index: self._on_value_changed(row, text))
                value_editor.setMinimumWidth(180)
                value_editor.setReadOnly(not editable)
                self.trc_table.setCellWidget(row_index, 3, value_editor)

            value_translation_item = QTableWidgetItem(self._translator.translate(segment.value))
            value_translation_item.setFlags(value_translation_item.flags() & ~Qt.ItemFlag.ItemIsEditable)

            changed_item = QTableWidgetItem("Nie")
            changed_item.setFlags(changed_item.flags() & ~Qt.ItemFlag.ItemIsEditable)

            self.trc_table.setItem(row_index, 0, number_item)
            self.trc_table.setItem(row_index, 1, option_item)
            self.trc_table.setItem(row_index, 2, translation_item)
            self.trc_table.setItem(row_index, 4, value_translation_item)
            self.trc_table.setItem(row_index, 5, changed_item)
            self._apply_row_style(row_index)

        self.trc_table.resizeColumnsToContents()
        self._apply_table_column_constraints()
        self._apply_table_filter()
        self._update_change_count()

    def _on_filter_text_changed(self, text: str):
        self._filter_text = (text or "").strip().casefold()
        self.clear_search_button.setEnabled(bool(self._filter_text))
        self._apply_table_filter()

    def _apply_table_filter(self):
        if not self._table_entries:
            return

        query = (self._filter_text or "").strip()
        if not query:
            for row_index in range(len(self._table_entries)):
                self.trc_table.setRowHidden(row_index, False)
            return

        group_row_visible: dict[int, bool] = {}
        option_row_visible: dict[int, bool] = {}
        current_group_row: int | None = None

        for row_index, entry in enumerate(self._table_entries):
            if entry.get("kind") == "group":
                group_row_visible[row_index] = False
                current_group_row = row_index
                continue

            segment = self._segments[entry["segment_index"]]
            option_name = segment.option or ""
            option_translation = self._translator.translate(option_name)
            is_match = query in option_name.casefold() or query in option_translation.casefold()
            option_row_visible[row_index] = is_match

            if is_match and entry.get("group") and current_group_row is not None:
                group_row_visible[current_group_row] = True

        for row_index, entry in enumerate(self._table_entries):
            if entry.get("kind") == "group":
                self.trc_table.setRowHidden(row_index, not group_row_visible.get(row_index, False))
            else:
                self.trc_table.setRowHidden(row_index, not option_row_visible.get(row_index, False))

    def _build_table_entries(self) -> list[dict]:
        entries: list[dict] = []
        last_group = ""
        for option_index, segment_index in enumerate(self._option_rows):
            segment = self._segments[segment_index]
            option_name = segment.option.strip().upper()
            group_name = ""
            if self._module_loaded:
                option_info = self._module_option_info.get(option_name, {})
                group_name = str(option_info.get("group", "")).strip()

            if group_name and group_name != last_group:
                entries.append({"kind": "group", "group": group_name})
                last_group = group_name

            entries.append(
                {
                    "kind": "option",
                    "segment_index": segment_index,
                    "option_index": option_index,
                    "group": group_name,
                }
            )
        return entries

    def _on_value_changed(self, row_index: int, text: str):
        if row_index < 0 or row_index >= len(self._table_entries):
            return
        entry = self._table_entries[row_index]
        if entry.get("kind") != "option":
            return
        option_index = entry["option_index"]
        if not self._row_editable.get(option_index, True):
            return

        segment_index = entry["segment_index"]
        segment = self._segments[segment_index]
        segment.value = text

        value_item = self.trc_table.item(row_index, 4)
        if value_item:
            value_item.setText(self._translator.translate(text))

        self._apply_row_style(row_index)
        self._update_change_count()

    def _build_value_combo(self, row_index: int, current_value: str, params: list[dict]) -> QComboBox:
        combo = QComboBox()
        combo.setMinimumWidth(180)
        combo.setEditable(False)

        names = [str(param.get("name", "")).strip() for param in params if str(param.get("name", "")).strip()]
        if current_value not in names:
            combo.addItem(f"⚠️ {current_value}")
            combo.setItemData(0, f"{current_value} (unknown)", Qt.ItemDataRole.ToolTipRole)

        for param in params:
            name = str(param.get("name", "")).strip()
            if not name:
                continue
            data_value = int(param.get("data", 0)) & 0xFF
            combo.addItem(name)
            combo.setItemData(combo.count() - 1, f"{name} (0x{data_value:02X})", Qt.ItemDataRole.ToolTipRole)

        target_index = combo.findText(current_value)
        if target_index >= 0:
            combo.setCurrentIndex(target_index)

        combo.currentTextChanged.connect(lambda text, row=row_index: self._on_value_changed(row, text.replace("⚠️ ", "")))
        return combo

    def _on_table_section_resized(self, logical_index: int, old_size: int, new_size: int):
        minimum_width = self._column_min_widths.get(logical_index)
        if minimum_width is None or new_size >= minimum_width:
            return

        header = self.trc_table.horizontalHeader()
        header.blockSignals(True)
        header.resizeSection(logical_index, minimum_width)
        header.blockSignals(False)

    def _apply_table_column_constraints(self):
        if not self._table_entries:
            self._column_min_widths = {}
            return

        header = self.trc_table.horizontalHeader()
        metrics = self.trc_table.fontMetrics()
        labels = [self.trc_table.horizontalHeaderItem(index).text() for index in range(self.trc_table.columnCount())]
        min_widths: dict[int, int] = {}

        for column_index, label in enumerate(labels):
            max_width = metrics.horizontalAdvance(label) + 28
            for row_index, entry in enumerate(self._table_entries):
                if entry.get("kind") == "group":
                    text = f"── {entry.get('group', '')} ──" if column_index == 0 else ""
                else:
                    segment = self._segments[entry["segment_index"]]
                    if column_index == 0:
                        text = str(entry["option_index"] + 1)
                    elif column_index == 1:
                        text = segment.option
                    elif column_index == 2:
                        text = self._translator.translate(segment.option)
                    elif column_index == 3:
                        widget = self.trc_table.cellWidget(row_index, 3)
                        if isinstance(widget, QComboBox):
                            text = widget.currentText()
                        else:
                            item = self.trc_table.item(row_index, 3)
                            text = item.text() if item else segment.value
                    elif column_index == 4:
                        text = self._translator.translate(segment.value)
                    elif column_index == 5:
                        item = self.trc_table.item(row_index, 5)
                        text = item.text() if item else ""
                    else:
                        text = ""

                if not text:
                    continue

                words = text.split()
                if words:
                    wrapped_width = max(metrics.horizontalAdvance(word) for word in words)
                else:
                    wrapped_width = metrics.horizontalAdvance(text)
                max_width = max(max_width, wrapped_width + 28)

            min_widths[column_index] = max_width
            if header.sectionSize(column_index) < max_width:
                header.blockSignals(True)
                header.resizeSection(column_index, max_width)
                header.blockSignals(False)

        self._column_min_widths = min_widths

    def _apply_row_style(self, row_index: int):
        if row_index < 0 or row_index >= len(self._table_entries):
            return

        entry = self._table_entries[row_index]
        if entry.get("kind") != "option":
            return

        segment_index = entry["segment_index"]
        segment = self._segments[segment_index]
        changed = segment.value != segment.original_value
        editable = self._row_editable.get(entry["option_index"], True)
        changed_color = QColor("#CDEFC8")
        locked_color = QColor("#E0E0E0")

        for column in range(self.trc_table.columnCount()):
            item = self.trc_table.item(row_index, column)
            if item:
                if not editable:
                    item.setBackground(locked_color)
                    item.setForeground(QColor("#606060"))
                elif changed:
                    item.setBackground(changed_color)
                    item.setForeground(QColor("#000000"))
                else:
                    item.setBackground(QColor("#FFFFFF"))
                    item.setForeground(QColor("#000000"))

        value_widget = self.trc_table.cellWidget(row_index, 3)
        if isinstance(value_widget, QLineEdit):
            if not editable:
                value_widget.setStyleSheet("background-color: #E0E0E0; color: #606060;")
            elif changed:
                value_widget.setStyleSheet("background-color: #CDEFC8; color: #000000;")
            else:
                value_widget.setStyleSheet("")
        elif isinstance(value_widget, QComboBox):
            if not editable:
                value_widget.setStyleSheet("background-color: #E0E0E0; color: #606060;")
            elif changed:
                value_widget.setStyleSheet("background-color: #CDEFC8; color: #000000;")
            else:
                value_widget.setStyleSheet("")

        status_item = self.trc_table.item(row_index, 5)
        if status_item:
            status_item.setText("Tak" if changed and editable else "Nie")

        self.trc_table.resizeRowToContents(row_index)

    def _update_change_count(self):
        self._sync_values_from_widgets()
        changed_count = 0
        for row_index, entry in enumerate(self._table_entries):
            if entry.get("kind") != "option":
                continue
            segment = self._segments[entry["segment_index"]]
            if segment.value != segment.original_value:
                changed_count += 1
        self.change_count_label.setText(f"Zmieniono: {changed_count} opcji")

    def _sync_values_from_widgets(self):
        for row_index, entry in enumerate(self._table_entries):
            if entry.get("kind") != "option":
                continue
            segment_index = entry["segment_index"]
            widget = self.trc_table.cellWidget(row_index, 3)
            if isinstance(widget, QLineEdit):
                self._segments[segment_index].value = widget.text()
            elif isinstance(widget, QComboBox):
                value = widget.currentText()
                if value.startswith("⚠️ "):
                    value = value[3:].strip()
                self._segments[segment_index].value = value
            else:
                value_item = self.trc_table.item(row_index, 3)
                if value_item:
                    self._segments[segment_index].value = value_item.text()

    def _current_content(self) -> str:
        self._sync_values_from_widgets()
        return format_trc_content(self._segments)

    def _current_baseline_content(self) -> str:
        if self._trc_loaded and self._segments:
            return self._current_content()
        return ""

    def _current_changes(self) -> list[dict]:
        self._sync_values_from_widgets()
        return build_change_list(self._segments)

    def export_current_file(self, extension: str):
        changes = self._current_changes()
        if not changes:
            QMessageBox.information(self, "Eksport", "Brak zmian do eksportu.")
            return

        if extension.upper() == ".MAN":
            confirm = ExportConfirmDialog(
                changes,
                self._translator,
                self._current_module_file or self._current_module,
                self,
            )
            if confirm.exec() != QDialog.DialogCode.Accepted:
                return

            export_path = DEFAULT_MAND_PATH
            notes = confirm.notes()
        else:
            confirm = ExportConfirmDialog(
                changes,
                self._translator,
                self._current_module_file or self._current_module,
                self,
            )
            if confirm.exec() != QDialog.DialogCode.Accepted:
                return

            default_directory = Path(self._paths.trc_path).parent if Path(self._paths.trc_path).exists() else Path.home()
            suggested_path = default_directory / DEFAULT_TRC_PATH.name
            file_filter = "NCS Expert Files (*.MAN *.TRC);;All Files (*)"
            selected_path, _ = QFileDialog.getSaveFileName(
                self,
                "Eksportuj zmiany",
                str(suggested_path),
                file_filter,
            )
            if not selected_path:
                return

            export_path = Path(selected_path)
            if not export_path.suffix:
                export_path = export_path.with_suffix(extension)
            notes = confirm.notes()

        self._sync_values_from_widgets()
        content_after = format_man_content(self._segments)
        try:
            export_path.parent.mkdir(parents=True, exist_ok=True)
            export_path.write_text(content_after, encoding="utf-8", newline="")
        except Exception as exc:
            QMessageBox.critical(self, "Eksport", f"Nie udało się zapisać pliku:\n{exc}")
            return

        if self._db and self._current_model and self._current_module:
            try:
                work_folder = str(Path(self._paths.trc_path).parent) if self._paths.trc_path else str(DEFAULT_WORK_PATH)
                sysdaten = parse_sysdaten(work_folder)
                fa_data = parse_fa_trc(work_folder)
                self._db.save_trc_history(
                    self._current_model,
                    self._current_module,
                    self._current_module_file,
                    self._baseline_content,
                    content_after,
                    changes,
                    notes=notes,
                    vin=str(sysdaten.get("FAHRGESTELL_NR", "")).strip(),
                    teilenummer=str(sysdaten.get("TEILENUMMER", "")).strip(),
                    production_date=str(fa_data.get("production_date", "")).strip(),
                    sa_codes=list(fa_data.get("sa_codes", []) or []),
                )
            except Exception:
                pass

        self._baseline_content = content_after
        for segment_index in self._option_rows:
            self._segments[segment_index].original_value = self._segments[segment_index].value
        self._render_table()

        QMessageBox.information(self, "Eksport", f"Zapisano do:\n{export_path}")

    def open_history_dialog(self):
        versions, history_rows, current_vin = self._build_history_versions()
        if len(history_rows) < 1 and not self._current_baseline_content():
            QMessageBox.information(self, "Historia", "Brak danych do porównania.")
            return

        dialog = HistoryCompareDialog(
            versions,
            history_rows=history_rows,
            current_vin=current_vin,
            db=self._db,
            translator=self._translator,
            parent=self,
        )
        dialog.exec()

    def _build_history_versions(self) -> tuple[list[dict], list[dict], str]:
        versions: list[dict] = []
        if self._db:
            history_rows = self._db.list_all_trc_history(limit=200)
            for row in history_rows:
                label = self._format_history_label(row)
                versions.append(
                    {
                        "label": label,
                        "content": row.get("content_after", ""),
                        "source": f"history:{row.get('id', 0)}",
                        "vin": str(row.get("vin") or "").strip().upper(),
                    }
                )
        else:
            history_rows = []

        work_folder = str(Path(self._paths.trc_path).parent) if self._paths.trc_path else str(DEFAULT_WORK_PATH)
        sysdaten_current = parse_sysdaten(work_folder)
        current_vin = str(sysdaten_current.get("FAHRGESTELL_NR", "")).strip().upper()

        current_content = self._current_baseline_content()
        if current_content:
            current_label = f"Aktualny plik ({Path(self._paths.trc_path).name})"
            versions.insert(
                0,
                {
                    "label": current_label,
                    "content": current_content,
                    "source": "current",
                    "vin": current_vin,
                },
            )

        overview_rows: list[dict] = []
        for row in history_rows:
            changes = row.get("changed_options") or []
            changes_count = len(changes) if isinstance(changes, list) else 0
            production_raw = str(row.get("production_date") or "").strip()
            production_display = self._format_production_date(production_raw)
            overview_rows.append(
                {
                    "id": int(row.get("id") or 0),
                    "vin": str(row.get("vin") or "").strip(),
                    "model": str(row.get("model") or "").strip().upper(),
                    "module": str(row.get("module") or "").strip(),
                    "teilenummer": str(row.get("teilenummer") or "").strip(),
                    "production_date_display": production_display,
                    "changes_text": "1 zmiana" if changes_count == 1 else f"{changes_count} zmian",
                    "exported_at": str(row.get("exported_at") or "").strip(),
                }
            )

        return versions, overview_rows, current_vin

    def _format_production_date(self, production_date: str) -> str:
        value = (production_date or "").strip()
        if len(value) == 4 and value.isdigit():
            month = value[:2]
            year = value[2:]
            return f"{month}/20{year}"
        return value

    def _format_history_label(self, row: dict) -> str:
        exported_at = (row.get("exported_at") or "").strip()
        module = (row.get("module") or "").strip()
        notes = (row.get("notes") or "").strip()
        if exported_at:
            try:
                from datetime import datetime

                parsed = datetime.strptime(exported_at, "%Y-%m-%d %H:%M:%S")
                exported_at = parsed.strftime("%Y-%m-%d %H:%M")
            except Exception:
                pass

        label = exported_at or "Brak daty"
        if module:
            label = f"{label} — {module}"
        if notes:
            label = f"{label} — {notes}"
        return label
