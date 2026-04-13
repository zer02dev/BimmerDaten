"""Parser SA option codes from BMW DATEN AT.000 and fa.trc files."""

from __future__ import annotations

import logging
from pathlib import Path


logger = logging.getLogger("bimmerdaten.sa_parser")


def find_at_file(chassis: str, daten_folder: str) -> Path | None:
    """
    Search for <chassis>AT.000 in multiple locations:
    1. DATEN/<chassis>/<chassis>AT.000
    2. DATEN/<chassis>AT.000
    3. Any direct subfolder of DATEN containing <chassis>AT.000
    """
    chassis_name = (chassis or "").strip().upper()
    if not chassis_name:
        return None

    daten = Path(daten_folder)
    if not daten.exists():
        return None

    filename = f"{chassis_name}AT.000"

    p1 = daten / chassis_name / filename
    if p1.exists() and p1.is_file():
        return p1

    p2 = daten / filename
    if p2.exists() and p2.is_file():
        return p2

    try:
        for subfolder in daten.iterdir():
            if not subfolder.is_dir():
                continue
            p3 = subfolder / filename
            if p3.exists() and p3.is_file():
                return p3
    except Exception:
        logger.exception("Failed while scanning DATEN subfolders for %s", filename)
        return None

    return None


def list_available_chassis(daten_folder: str) -> list[str]:
    """
    Build dynamic chassis list by scanning DATEN root and direct subfolders
    for files matching *AT.000 and extracting chassis name from filename.
    """
    daten = Path(daten_folder)
    if not daten.exists():
        return []

    found: set[str] = set()

    def _extract_chassis(file_name: str) -> str | None:
        upper = file_name.upper()
        if not upper.endswith("AT.000"):
            return None
        chassis_name = upper[:-6]
        chassis_name = chassis_name.strip().rstrip("._- ")
        return chassis_name or None

    try:
        for path in daten.iterdir():
            if path.is_file():
                chassis_name = _extract_chassis(path.name)
                if chassis_name:
                    found.add(chassis_name)
            elif path.is_dir():
                for subfile in path.iterdir():
                    if not subfile.is_file():
                        continue
                    chassis_name = _extract_chassis(subfile.name)
                    if chassis_name:
                        found.add(chassis_name)
    except Exception:
        logger.exception("Failed while listing available chassis in %s", daten_folder)
        return sorted(found)

    return sorted(found)


def _guess_category(sa_code: str, asw_name: str, desc_de: str) -> str:
    """Guess category from ASW name and description."""
    text = f"{asw_name} {desc_de}".upper()

    if any(k in text for k in ["MOTOR", "TURBO", "M43", "M47", "M52", "M54", "N40", "N42", "N46", "S54", "M57"]):
        return "Silnik"
    if any(k in text for k in ["GETRIEBE", "AUTOMATIK", "SMG", "SCHALT"]):
        return "Skrzynia"
    if any(k in text for k in ["AIRBAG", "ABS", "DSC", "ASC", "MRS", "GURT", "EWS", "SEITENAIRB", "KOPFBAG"]):
        return "Bezpieczeństwo"
    if any(k in text for k in ["KLIMA", "HEIZ", "SHD", "SITZ", "MEMORY", "LENKRAD", "PDC", "PARK"]):
        return "Komfort"
    if any(k in text for k in ["RADIO", "NAVIGATION", "NAVI", "MONITOR", "BORDMONITOR", "CD", "HIFI", "TEL", "GSM"]):
        return "Multimedia"
    if any(k in text for k in ["XENON", "NEBEL", "TAGFAHR", "LSZ", "LICHT", "SCHEINW"]):
        return "Oświetlenie"
    if any(k in text for k in ["LACK", "POLSTER", "DACH", "VERDECK", "SPOILER", "FELGE", "RAD", "LM"]):
        return "Nadwozie"
    return "Inne"


def parse_at_file(chassis: str, daten_folder: str) -> list[dict]:
    """Parse <chassis>AT.000 file and return SA option dicts."""
    options: list[dict] = []
    chassis_name = (chassis or "").strip().upper()
    if not chassis_name:
        return options

    at_path = find_at_file(chassis_name, daten_folder)
    if not at_path:
        return options

    try:
        with open(at_path, encoding="latin-1", errors="ignore") as handle:
            for line in handle:
                line = line.strip()
                if not line or line.startswith("//"):
                    continue
                if not line.startswith("W "):
                    continue

                desc_de = ""
                if "//" in line:
                    desc_de = line.split("//", 1)[1].strip()
                    line = line.split("//", 1)[0].strip()

                parts = line.split()
                if len(parts) < 2:
                    continue

                sa_code = (parts[1] or "").strip().upper()
                if not sa_code:
                    continue
                asw_name = (parts[2] or "").strip() if len(parts) > 2 else ""

                options.append(
                    {
                        "sa_code": sa_code,
                        "asw_name": asw_name,
                        "desc_de": desc_de,
                        "desc_en": "",
                        "codierrelevant": bool(asw_name),
                        "category": _guess_category(sa_code, asw_name, desc_de),
                    }
                )
    except Exception:
        logger.exception("Failed parsing AT file: %s", at_path)
        return []

    return options


def parse_fa_trc(fa_path: str) -> list[str]:
    """Parse fa.trc and return list of SA codes."""
    try:
        content = Path(fa_path).read_text(encoding="latin-1", errors="ignore").strip()
    except Exception:
        logger.exception("Failed reading FA trace file: %s", fa_path)
        return []

    if not content:
        return []

    sa_codes: list[str] = []
    for part in content.split("$")[1:]:
        code = part.split("$")[0].split("&")[0].split("*")[0].strip().upper()
        if code:
            sa_codes.append(code)

    # Preserve order, remove duplicates.
    seen: set[str] = set()
    ordered_unique: list[str] = []
    for code in sa_codes:
        if code in seen:
            continue
        seen.add(code)
        ordered_unique.append(code)
    return ordered_unique
