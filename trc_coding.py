"""
trc_coding.py
Panel kodowania NCS Expert oraz narzędzia do pracy z plikami TRC.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
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
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
    QHeaderView,
)

from database import Database
from trc_translator import TrcTranslator


DEFAULT_TRC_PATH = Path(r"C:\NCSEXPER\WORK\FSW_PSW.TRC")
DEFAULT_DATEN_PATH = Path(r"C:\NCSEXPER\DATEN")
DEFAULT_TRANSLATIONS_PATH = Path(r"C:\NCS Dummy\Translations.csv")
DEFAULT_MAND_PATH = Path(r"C:\NCSEXPER\WORK\FSW_PSW.MAN")
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


@dataclass
class ParsedModuleFile:
    model: str
    module: str
    module_file: str
    source_path: Path
    modules: list[dict] = field(default_factory=list)


def read_text_file(path: Path) -> str:
    for encoding in ("utf-8-sig", "cp1250", "latin1", "mbcs"):
        try:
            return path.read_text(encoding=encoding)
        except Exception:
            continue
    return path.read_text(encoding="latin1", errors="ignore")


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


def discover_model_files(daten_path: Path) -> dict[str, ParsedModuleFile]:
    result: dict[str, ParsedModuleFile] = {}
    if not daten_path.exists():
        return result

    search_patterns = ["*SGFAM.DAT", "*SGFAM.dat"]
    dat_files: list[Path] = []
    for pattern in search_patterns:
        dat_files.extend(daten_path.rglob(pattern))

    seen_paths: set[Path] = set()
    for dat_path in sorted(dat_files):
        if dat_path in seen_paths:
            continue
        seen_paths.add(dat_path)
        model_name = _derive_model_name(dat_path)
        modules = _parse_module_entries(dat_path)
        result[model_name] = ParsedModuleFile(
            model=model_name,
            module="",
            module_file=dat_path.name,
            source_path=dat_path,
            modules=modules,
        )
    return result


def _derive_model_name(dat_path: Path) -> str:
    parent_name = dat_path.parent.name.strip().upper()
    if parent_name and len(parent_name) <= 8:
        return parent_name

    stem = dat_path.stem.upper()
    if "SGFAM" in stem:
        return stem.split("SGFAM", 1)[0].strip(" _-.") or stem
    return stem


def _parse_module_entries(dat_path: Path) -> list[dict]:
    text = read_text_file(dat_path)
    modules: list[dict] = []
    seen_files: set[str] = set()
    file_pattern = re.compile(r"([A-Za-z0-9_]+)\.([A-Za-z0-9]{2,4})")

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        for match in file_pattern.finditer(line):
            stem = match.group(1).upper()
            extension = match.group(2).upper()
            module_file = f"{stem}.{extension}"
            if module_file in seen_files:
                continue
            seen_files.add(module_file)

            prefix = line[: match.start()].strip(" \t-_:;,.()[]{}")
            if prefix:
                module_name = prefix.split(",")[-1].split(";")[-1].split("|")[-1].strip().upper()
            else:
                module_name = stem

            if not module_name:
                module_name = stem

            modules.append(
                {
                    "module": module_name,
                    "module_file": module_file,
                    "label": f"{module_name} ({module_file})",
                }
            )

    modules.sort(key=lambda entry: (entry["module"], entry["module_file"]))
    return modules


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
    def __init__(self, changes: list[dict], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Potwierdzenie eksportu")
        self.setModal(True)
        self._build_ui(changes)

    def _build_ui(self, changes: list[dict]):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        label = QLabel("Eksportujesz następujące zmiany:")
        layout.addWidget(label)

        browser = QTextBrowser()
        browser.setMinimumHeight(200)
        lines = []
        for change in changes:
            option = change.get("option", "")
            value_from = change.get("from", "")
            value_to = change.get("to", "")
            lines.append(f"- {option}: {value_from} -> {value_to}")
        browser.setPlainText("\n".join(lines) if lines else "Brak zmian.")
        layout.addWidget(browser)

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
    def __init__(self, versions: list[dict], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Historia i porównanie")
        self.setModal(True)
        self._versions = versions
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        selectors = QHBoxLayout()
        selectors.addWidget(QLabel("Wersja A"))
        self.version_a = QComboBox()
        selectors.addWidget(self.version_a, 1)
        selectors.addWidget(QLabel("Wersja B"))
        self.version_b = QComboBox()
        selectors.addWidget(self.version_b, 1)
        layout.addLayout(selectors)

        for version in self._versions:
            label = version.get("label", "Bez nazwy")
            self.version_a.addItem(label, version)
            self.version_b.addItem(label, version)

        if self.version_a.count() > 0:
            self.version_a.setCurrentIndex(0)
        if self.version_b.count() > 1:
            self.version_b.setCurrentIndex(1)

        action_row = QHBoxLayout()
        self.compare_button = QPushButton("Porównaj")
        self.only_diffs = QCheckBox("Pokaż tylko różnice")
        self.only_diffs.setChecked(True)
        self.compare_button.clicked.connect(self._compare)
        action_row.addWidget(self.compare_button)
        action_row.addWidget(self.only_diffs)
        action_row.addStretch()
        layout.addLayout(action_row)

        self.diff_table = QTableWidget()
        self.diff_table.setColumnCount(4)
        self.diff_table.setHorizontalHeaderLabels(["Opcja", "Wartość A", "Wartość B", "Zmiana"])
        self.diff_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.diff_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.diff_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.diff_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.diff_table, 1)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

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
            option_item = QTableWidgetItem(option)
            value_a_item = QTableWidgetItem(value_a)
            value_b_item = QTableWidgetItem(value_b)
            status_item = QTableWidgetItem("✅ same" if same else "⚠ different")

            if not same:
                for item in (option_item, value_a_item, value_b_item, status_item):
                    item.setBackground(QColor("#FFE0E0"))
                    item.setForeground(QColor("#000000"))

            self.diff_table.setItem(row_index, 0, option_item)
            self.diff_table.setItem(row_index, 1, value_a_item)
            self.diff_table.setItem(row_index, 2, value_b_item)
            self.diff_table.setItem(row_index, 3, status_item)

        self.diff_table.resizeColumnsToContents()


class CodingPanel(QWidget):
    def __init__(self, db: Database | None = None, parent=None):
        super().__init__(parent)
        self._db = db
        self._paths = self._load_paths()
        self._translator = TrcTranslator(self._paths.translations_path)
        self._segments: list[TrcSegment] = []
        self._option_rows: list[int] = []
        self._current_model = ""
        self._current_module = ""
        self._current_module_file = ""
        self._current_trc_content = ""
        self._baseline_content = ""
        self._model_files: dict[str, ParsedModuleFile] = {}
        self._setup_ui()
        self._refresh_warning_state()
        self.reload_model_tree(select_first=True)

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

        self.model_tree = QTreeWidget()
        self.model_tree.setHeaderHidden(True)
        self.model_tree.currentItemChanged.connect(self._on_tree_selection_changed)
        left_layout.addWidget(self.model_tree, 1)

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

        splitter = QSplitter(Qt.Orientation.Vertical)

        table_widget = QWidget()
        table_layout = QVBoxLayout(table_widget)
        table_layout.setContentsMargins(0, 0, 0, 0)
        table_layout.setSpacing(4)

        self.context_label = QLabel("Wybierz model i moduł po lewej")
        self.context_label.setWordWrap(True)
        table_layout.addWidget(self.context_label)

        self.trc_table = QTableWidget()
        self.trc_table.setColumnCount(5)
        self.trc_table.setHorizontalHeaderLabels([
            "Opcja",
            "Tłumaczenie",
            "Wartość",
            "Tłumaczenie wartości",
            "Zmieniono",
        ])
        self.trc_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.trc_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.trc_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.trc_table.horizontalHeader().setStretchLastSection(True)
        table_layout.addWidget(self.trc_table, 1)
        splitter.addWidget(table_widget)

        toolbar_widget = QWidget()
        toolbar_widget.setMaximumHeight(72)
        toolbar_layout = QHBoxLayout(toolbar_widget)
        toolbar_layout.setContentsMargins(0, 0, 0, 0)
        toolbar_layout.setSpacing(4)

        self.export_man_button = QPushButton("📤 Export .MAN")
        self.export_trc_button = QPushButton("📤 Export .TRC")
        self.compare_button = QPushButton("👁 Porównaj zmiany")
        self.change_count_label = QLabel("Zmieniono: 0 opcji")

        self.export_man_button.clicked.connect(lambda: self.export_current_file(".MAN"))
        self.export_trc_button.clicked.connect(lambda: self.export_current_file(".TRC"))
        self.compare_button.clicked.connect(self.open_history_dialog)

        toolbar_layout.addWidget(self.export_man_button)
        toolbar_layout.addWidget(self.export_trc_button)
        toolbar_layout.addWidget(self.compare_button)
        toolbar_layout.addStretch()
        toolbar_layout.addWidget(self.change_count_label)

        splitter.addWidget(toolbar_widget)
        splitter.setSizes([520, 90])
        right_layout.addWidget(splitter, 1)

        layout.addWidget(left_box)
        layout.addWidget(right_box, 1)

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

    def reload_model_tree(self, select_first: bool = False):
        self.model_tree.blockSignals(True)
        self.model_tree.clear()
        self._model_files = discover_model_files(Path(self._paths.daten_path))

        for model_name in sorted(self._model_files.keys()):
            model_data = self._model_files[model_name]
            model_item = QTreeWidgetItem([model_name])
            model_item.setData(0, Qt.ItemDataRole.UserRole, {"kind": "model", "model": model_name})
            self.model_tree.addTopLevelItem(model_item)

            for module in model_data.modules:
                module_label = module.get("label", "")
                module_item = QTreeWidgetItem([module_label])
                module_item.setData(
                    0,
                    Qt.ItemDataRole.UserRole,
                    {
                        "kind": "module",
                        "model": model_name,
                        "module": module.get("module", ""),
                        "module_file": module.get("module_file", ""),
                    },
                )
                model_item.addChild(module_item)

            model_item.setExpanded(True)

        self.model_tree.blockSignals(False)
        if select_first:
            self._select_first_module()

        if not self._model_files:
            self.context_label.setText("Nie znaleziono plików E46SGFAM.DAT w DATEN")
        else:
            self.context_label.setText("Wybierz model i moduł po lewej")

    def _select_first_module(self):
        if self.model_tree.topLevelItemCount() == 0:
            return

        for top_index in range(self.model_tree.topLevelItemCount()):
            model_item = self.model_tree.topLevelItem(top_index)
            if model_item.childCount() == 0:
                continue
            first_module = model_item.child(0)
            if first_module:
                self.model_tree.setCurrentItem(first_module)
                return

    def _on_tree_selection_changed(self, current, previous):
        if not current:
            return

        data = current.data(0, Qt.ItemDataRole.UserRole) or {}
        kind = data.get("kind")
        if kind == "model":
            self.context_label.setText(f"Model: {data.get('model', '')}")
            return

        if kind != "module":
            return

        self._current_model = data.get("model", "")
        self._current_module = data.get("module", "")
        self._current_module_file = data.get("module_file", "")
        self.context_label.setText(
            f"Model: {self._current_model} | Moduł: {self._current_module} | Plik: {self._current_module_file}"
        )
        self.load_trc_from_path(Path(self._paths.trc_path))

    def reload_current_trc(self):
        self._refresh_warning_state()
        if not self._current_module:
            self.context_label.setText("Wybierz moduł po lewej, aby wczytać FSW_PSW.TRC")
            return
        self.load_trc_from_path(Path(self._paths.trc_path))

    def load_trc_from_path(self, trc_path: Path):
        if not trc_path.exists():
            self._segments = []
            self._option_rows = []
            self._current_trc_content = ""
            self._baseline_content = ""
            self._render_table()
            self.context_label.setText(f"Nie znaleziono pliku: {trc_path}")
            return

        content = read_text_file(trc_path)
        self._current_trc_content = content
        self._baseline_content = content
        self._segments = parse_trc_content(content)
        self._option_rows = [index for index, segment in enumerate(self._segments) if segment.kind == "option"]
        self._render_table()
        self.context_label.setText(
            f"Model: {self._current_model} | Moduł: {self._current_module} | TRC: {trc_path}"
        )

    def _render_table(self):
        self.trc_table.setRowCount(len(self._option_rows))
        self.trc_table.clearContents()

        for row_index, segment_index in enumerate(self._option_rows):
            segment = self._segments[segment_index]

            option_item = QTableWidgetItem(segment.option)
            option_item.setFlags(option_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            translation_item = QTableWidgetItem(self._translator.translate(segment.option))
            translation_item.setFlags(translation_item.flags() & ~Qt.ItemFlag.ItemIsEditable)

            value_edit = QLineEdit(segment.value)
            value_edit.textChanged.connect(lambda text, row=row_index: self._on_value_changed(row, text))
            value_edit.setMinimumWidth(180)

            value_translation_item = QTableWidgetItem(self._translator.translate(segment.value))
            value_translation_item.setFlags(value_translation_item.flags() & ~Qt.ItemFlag.ItemIsEditable)

            changed_item = QTableWidgetItem("Nie")
            changed_item.setFlags(changed_item.flags() & ~Qt.ItemFlag.ItemIsEditable)

            self.trc_table.setItem(row_index, 0, option_item)
            self.trc_table.setItem(row_index, 1, translation_item)
            self.trc_table.setCellWidget(row_index, 2, value_edit)
            self.trc_table.setItem(row_index, 3, value_translation_item)
            self.trc_table.setItem(row_index, 4, changed_item)
            self._apply_row_style(row_index)

        self.trc_table.resizeColumnsToContents()
        self._update_change_count()

    def _on_value_changed(self, row_index: int, text: str):
        if row_index < 0 or row_index >= len(self._option_rows):
            return

        segment_index = self._option_rows[row_index]
        segment = self._segments[segment_index]
        segment.value = text

        value_item = self.trc_table.item(row_index, 3)
        if value_item:
            value_item.setText(self._translator.translate(text))

        self._apply_row_style(row_index)
        self._update_change_count()

    def _apply_row_style(self, row_index: int):
        if row_index < 0 or row_index >= len(self._option_rows):
            return

        segment_index = self._option_rows[row_index]
        segment = self._segments[segment_index]
        changed = segment.value != segment.original_value

        for column in range(self.trc_table.columnCount()):
            item = self.trc_table.item(row_index, column)
            if item:
                if changed:
                    item.setBackground(QColor("#FFFF99"))
                    item.setForeground(QColor("#000000"))
                else:
                    item.setBackground(QColor("#FFFFFF"))
                    item.setForeground(QColor("#000000"))

        value_widget = self.trc_table.cellWidget(row_index, 2)
        if isinstance(value_widget, QLineEdit):
            if changed:
                value_widget.setStyleSheet("background-color: #FFFF99; color: #000000;")
            else:
                value_widget.setStyleSheet("")

        status_item = self.trc_table.item(row_index, 4)
        if status_item:
            status_item.setText("Tak" if changed else "Nie")

    def _update_change_count(self):
        changed_count = 0
        for segment_index in self._option_rows:
            segment = self._segments[segment_index]
            if segment.value != segment.original_value:
                changed_count += 1
        self.change_count_label.setText(f"Zmieniono: {changed_count} opcji")

    def _current_content(self) -> str:
        return format_trc_content(self._segments)

    def _current_changes(self) -> list[dict]:
        return build_change_list(self._segments)

    def export_current_file(self, extension: str):
        changes = self._current_changes()
        if not changes:
            QMessageBox.information(self, "Eksport", "Brak zmian do eksportu.")
            return

        confirm = ExportConfirmDialog(changes, self)
        if confirm.exec() != QDialog.DialogCode.Accepted:
            return

        default_directory = Path(self._paths.trc_path).parent if Path(self._paths.trc_path).exists() else Path.home()
        suggested_name = DEFAULT_MAND_PATH.name if extension.upper() == ".MAN" else DEFAULT_TRC_PATH.name
        suggested_path = default_directory / suggested_name
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

        content_after = self._current_content()
        try:
            export_path.parent.mkdir(parents=True, exist_ok=True)
            export_path.write_text(content_after, encoding="utf-8", newline="\n")
        except Exception as exc:
            QMessageBox.critical(self, "Eksport", f"Nie udało się zapisać pliku:\n{exc}")
            return

        if self._db and self._current_model and self._current_module:
            try:
                self._db.save_trc_history(
                    self._current_model,
                    self._current_module,
                    self._current_module_file,
                    self._baseline_content,
                    content_after,
                    changes,
                    notes=confirm.notes(),
                )
            except Exception:
                pass

        self._baseline_content = content_after
        for segment_index in self._option_rows:
            self._segments[segment_index].original_value = self._segments[segment_index].value
        self._render_table()
        QMessageBox.information(self, "Eksport", f"Zapisano do:\n{export_path}")

    def open_history_dialog(self):
        versions = self._build_history_versions()
        if len(versions) < 1:
            QMessageBox.information(self, "Historia", "Brak danych do porównania.")
            return

        dialog = HistoryCompareDialog(versions, self)
        dialog.exec()

    def _build_history_versions(self) -> list[dict]:
        versions: list[dict] = []
        current_label = f"Aktualny plik ({Path(self._paths.trc_path).name})"
        versions.append(
            {
                "label": current_label,
                "content": self._current_content(),
                "source": "current",
            }
        )

        if self._db and self._current_model and self._current_module:
            history_rows = self._db.get_trc_history(self._current_model, self._current_module, limit=50)
            for row in history_rows:
                label = f"{row.get('exported_at', '')} — {row.get('module', '')}"
                notes = (row.get("notes") or "").strip()
                if notes:
                    label += f" — {notes}"
                versions.append(
                    {
                        "label": label,
                        "content": row.get("content_after", ""),
                        "source": f"history:{row.get('id', 0)}",
                    }
                )

        return versions
