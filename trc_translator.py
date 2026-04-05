"""
trc_translator.py
Lokalny translator dla nazw opcji i wartości z pliku Translations.csv.
"""

from __future__ import annotations

import csv
from pathlib import Path


DEFAULT_TRANSLATIONS_PATH = Path(r"C:\NCS Dummy\Translations.csv")


class TrcTranslator:
    def __init__(self, csv_path: str | Path | None = None):
        self.csv_path = Path(csv_path) if csv_path else DEFAULT_TRANSLATIONS_PATH
        self._translations: dict[str, str] = {}
        self.reload()

    def reload(self) -> None:
        self._translations.clear()
        if not self.csv_path.exists():
            return

        rows = self._read_csv_rows(self.csv_path)
        if not rows:
            return

        header = [cell.strip() for cell in rows[0]]
        key_index, value_index = self._detect_columns(header)

        start_index = 1 if self._looks_like_header(header) else 0
        for row in rows[start_index:]:
            if not row:
                continue

            if key_index >= len(row) or value_index >= len(row):
                if len(row) >= 2:
                    key = row[0]
                    value = row[1]
                else:
                    continue
            else:
                key = row[key_index]
                value = row[value_index]

            normalized_key = self._normalize_key(key)
            if not normalized_key:
                continue

            normalized_value = (value or "").strip()
            if normalized_value:
                self._translations[normalized_key] = normalized_value

    def translate(self, key: str) -> str:
        normalized_key = self._normalize_key(key)
        if not normalized_key:
            return key
        return self._translations.get(normalized_key, key)

    def get_translation(self, key: str) -> str:
        return self.translate(key)

    def _normalize_key(self, key: str) -> str:
        return (key or "").strip().casefold()

    def _read_csv_rows(self, csv_path: Path) -> list[list[str]]:
        encodings = ("utf-8-sig", "cp1250", "latin1")
        sample_text = ""
        for encoding in encodings:
            try:
                with csv_path.open("r", encoding=encoding, newline="") as handle:
                    sample_text = handle.read(8192)
                break
            except Exception:
                continue

        if not sample_text:
            return []

        dialect = self._sniff_dialect(sample_text)
        for encoding in encodings:
            try:
                with csv_path.open("r", encoding=encoding, newline="") as handle:
                    return [row for row in csv.reader(handle, dialect)]
            except Exception:
                continue
        return []

    def _sniff_dialect(self, sample_text: str) -> csv.Dialect:
        try:
            return csv.Sniffer().sniff(sample_text, delimiters=";,\t|")
        except Exception:
            return csv.excel

    def _looks_like_header(self, header: list[str]) -> bool:
        normalized = {cell.casefold() for cell in header}
        return bool(
            normalized.intersection(
                {
                    "key",
                    "name",
                    "token",
                    "source",
                    "original",
                    "de",
                    "german",
                    "english",
                    "en",
                    "translation",
                }
            )
        )

    def _detect_columns(self, header: list[str]) -> tuple[int, int]:
        lowered = [cell.casefold() for cell in header]

        key_candidates = {
            "key",
            "name",
            "token",
            "source",
            "original",
            "de",
            "german",
            "option",
        }
        value_candidates = {
            "english",
            "en",
            "translation",
            "translated",
            "comment_en",
        }

        key_index = 0
        value_index = 1 if len(header) > 1 else 0

        for index, column_name in enumerate(lowered):
            if column_name in key_candidates:
                key_index = index
                break

        for index, column_name in enumerate(lowered):
            if column_name in value_candidates:
                value_index = index
                break

        return key_index, value_index


translator = TrcTranslator()


def translate(key: str) -> str:
    return translator.translate(key)
