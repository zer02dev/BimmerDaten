"""
inpa_parser.py
Parser for INPA configuration files (.ENG and .IPO).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional


class INPAParser:
    CATEGORY_MAP = {
        "ROOT_MOTOR": "Silnik",
        "ROOT_GETRIEBE": "Skrzynia",
        "ROOT_FAHRWERK": "Podwozie",
        "ROOT_KAROSSERIE": "Karoseria",
        "ROOT_KOMMUNIKATION": "Komunikacja",
    }

    CATEGORY_ORDER = [
        "Silnik",
        "Skrzynia",
        "Podwozie",
        "Karoseria",
        "Komunikacja",
    ]

    COMMON_KEYWORDS = {
        "SGBD",
        "SGBDS",
        "ECU",
        "TEST",
        "INFO",
        "IDENT",
        "JOB",
        "START",
        "STOP",
        "STATUS",
        "CONFIG",
        "MENU",
        "TEXT",
        "DATA",
        "MODULE",
        "SCRIPT",
        "INPA",
    }

    ECU_PREFIXES = (
        "ME9",
        "MS4",
        "MSS",
        "DDE",
        "DSC",
        "GS",
        "ZKE",
        "IHKA",
        "MSD",
        "MSV",
        "EWS",
        "ABS",
        "SMG",
        "MRS",
        "EKP",
        "LCM",
        "KOMBI",
        "DME",
        "EGS",
        "CAS",
        "FRM",
        "JBBF",
        "PDC",
        "RAD",
        "CCC",
        "CIC",
        "NFRM",
        "KAFAS",
        "VTG",
        "SZL",
        "ICM",
        "TPMS",
        "RLS",
        "PMA",
        "SMG",
    )

    def __init__(self, inpa_path: str):
        self.inpa_path = Path(inpa_path)
        self.cfgdat_dir = self.inpa_path / "CFGDAT"
        self.sgdat_dir = self.inpa_path / "SGDAT"
        self._ipo_cache: dict[str, list[str]] = {}

    def parse_all(self) -> dict:
        result: dict[str, dict[str, list[dict[str, object]]]] = {}
        if not self.cfgdat_dir.exists():
            return result

        eng_files = sorted(self.cfgdat_dir.rglob("*.ENG"))
        if not eng_files:
            eng_files = sorted(self.cfgdat_dir.rglob("*.eng"))

        for eng_path in eng_files:
            model = self._model_from_filename(eng_path)
            if not model:
                continue

            model_bucket = result.setdefault(
                model,
                {category: [] for category in self.CATEGORY_ORDER},
            )

            current_category: Optional[str] = None
            for raw_line in self._read_text_lines(eng_path):
                line = raw_line.strip()
                if not line or line.startswith("//*"):
                    continue

                upper = line.upper()
                if upper == "[ROOT]":
                    current_category = None
                    continue

                if upper.startswith("[") and upper.endswith("]"):
                    current_category = self.CATEGORY_MAP.get(upper.strip("[]"))
                    continue

                if not upper.startswith("ENTRY=") or not current_category:
                    continue

                entry = line.split("=", 1)[1].strip()
                script_name, description = self._parse_entry(entry)
                if not script_name or not description:
                    continue

                prg_file = self.get_prg_for_script(script_name)
                model_bucket.setdefault(current_category, []).append(
                    {
                        "description": description,
                        "script": script_name,
                        "prg_file": prg_file,
                    }
                )

        return result

    def get_prg_for_script(self, script_name: str) -> list[str]:
        script_name = (script_name or "").strip()
        if not script_name:
            return []

        cached = self._ipo_cache.get(script_name.upper())
        if cached is not None:
            return cached

        ipo_path = self._find_ipo_file(script_name)
        if not ipo_path:
            self._ipo_cache[script_name.upper()] = []
            return []

        prg_files = self._extract_prg_from_ipo(ipo_path)
        if not prg_files:
            prg_files = self._find_prg_by_filename(script_name)
        self._ipo_cache[script_name.upper()] = prg_files
        return prg_files

    def _model_from_filename(self, eng_path: Path) -> str:
        stem = eng_path.stem
        match = re.match(r"[A-Za-z0-9]+", stem)
        return match.group(0).upper() if match else stem.upper()

    def _read_text_lines(self, path: Path) -> list[str]:
        for encoding in ("utf-8-sig", "cp1250", "latin1", "mbcs"):
            try:
                return path.read_text(encoding=encoding).splitlines()
            except Exception:
                continue
        return path.read_text(encoding="latin1", errors="ignore").splitlines()

    def _parse_entry(self, entry: str) -> tuple[Optional[str], Optional[str]]:
        if not entry or entry == "," or entry == ",,":
            return None, None

        parts = entry.split(",", 1)
        if len(parts) < 2:
            return None, None

        script_name = parts[0].strip().strip('"')
        description = parts[1].strip().strip('"')
        if not script_name or not description:
            return None, None
        return script_name, description

    def _find_ipo_file(self, script_name: str) -> Optional[Path]:
        if not self.sgdat_dir.exists():
            return None

        candidates = [
            self.sgdat_dir / f"{script_name}.IPO",
            self.sgdat_dir / f"{script_name}.ipo",
            self.sgdat_dir / f"{script_name.upper()}.IPO",
            self.sgdat_dir / f"{script_name.lower()}.ipo",
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate

        direct_matches = list(self.sgdat_dir.rglob(f"{script_name}.IPO"))
        if direct_matches:
            return direct_matches[0]
        direct_matches = list(self.sgdat_dir.rglob(f"{script_name}.ipo"))
        if direct_matches:
            return direct_matches[0]

        script_upper = script_name.upper()
        for ipo_path in self.sgdat_dir.rglob("*.IPO"):
            if ipo_path.stem.upper() == script_upper:
                return ipo_path
        for ipo_path in self.sgdat_dir.rglob("*.ipo"):
            if ipo_path.stem.upper() == script_upper:
                return ipo_path

        return None

    def _extract_prg_from_ipo(self, ipo_path: Path) -> list[str]:
        try:
            data = ipo_path.read_bytes()
        except Exception:
            return []

        results: list[str] = []
        seen: set[str] = set()
        for match in re.finditer(rb"[A-Za-z0-9_]{3,}", data):
            candidate = match.group(0).decode("ascii", errors="ignore").upper()
            if self._is_prg_candidate(candidate):
                if candidate not in seen:
                    seen.add(candidate)
                    results.append(candidate)
        return results

    def _find_prg_by_filename(self, script_name: str) -> list[str]:
        target_name = f"{script_name}.prg"
        candidate_dirs = [
            self.inpa_path.parent / "EDIABAS" / "Ecu",
            self.inpa_path.parent / "Ecu",
            Path(r"C:\EDIABAS\Ecu"),
            Path(r"C:\EC-APPS\EDIABAS\Ecu"),
        ]

        for folder in candidate_dirs:
            if not folder or not folder.exists():
                continue
            for file_path in folder.iterdir():
                if file_path.is_file() and file_path.suffix.lower() == ".prg":
                    if file_path.name.lower() == target_name.lower():
                        return [script_name]
        return []

    def _is_prg_candidate(self, candidate: str) -> bool:
        if not (4 <= len(candidate) <= 20):
            return False
        if candidate in self.COMMON_KEYWORDS:
            return False
        if not candidate.startswith(self.ECU_PREFIXES):
            return False
        if not any(char.isdigit() for char in candidate) and "_" not in candidate:
            return False
        return True


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python inpa_parser.py <INPA_ROOT>")
        raise SystemExit(1)

    parser = INPAParser(sys.argv[1])
    models = parser.parse_all()
    print(f"Models found: {len(models)}")
    for model, categories in models.items():
        print(model)
        for category, entries in categories.items():
            print(f"  {category}: {len(entries)}")
