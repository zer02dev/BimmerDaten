"""
vin_decoder.py
Offline VIN decoding for BMW / MINI cars.

What a VIN can tell (no internet needed):
  - positions 1-3  manufacturer code (WMI)
  - positions 4-7  BMW type key, looked up in the NCS Expert *AT.000 files
                   (model, body, engine, drive side, production period)
  - position 9     check digit (required in North America)
  - position 10    model year (North America; usually "0" on European cars)
  - position 11    plant letter (unofficial: public lists disagree)
  - positions 11-17 short VIN used by NCS / ISTA

The list of SA options is NOT in the VIN; it is in the vehicle order (FA),
which NCS Expert reads from the car into FA.TRC.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

logger = logging.getLogger("bimmerdaten.vin_decoder")

VIN_LENGTH = 17
FORBIDDEN_CHARS = set("IOQ")

# Manufacturer codes (positions 1-3) used on BMW group cars.
WMI_NAMES = {
    "WBA": "BMW AG, Germany (passenger cars)",
    "WBS": "BMW M GmbH, Germany",
    "WBY": "BMW AG, Germany (BMW i)",
    "WMW": "MINI (BMW AG)",
    "4US": "BMW Manufacturing, USA",
    "5UX": "BMW Manufacturing, USA (X models)",
    "5YM": "BMW M, USA-built X models",
}

# Plant letters (position 11). BMW does not publish an official list and public
# lists disagree, so only letters on which the common lists agree are named.
PLANT_HINTS = {
    "A": "Munich",
    "F": "Munich",
    "K": "Munich",
    "B": "Dingolfing",
    "C": "Dingolfing",
    "D": "Dingolfing",
    "E": "Regensburg",
    "J": "Regensburg",
    "L": "Spartanburg (USA)",
    "N": "Rosslyn (South Africa)",
}

# Model year codes (position 10), 30-year cycle starting 1980 / 2010.
_YEAR_CODES = "ABCDEFGHJKLMNPRSTVWXY123456789"

BODY_NAMES = {
    "LIM": "Sedan",
    "TOUR": "Touring",
    "COUP": "Coupé",
    "CABR": "Convertible",
    "COMP": "Compact",
}
DRIVE_SIDE = {"LL": "Left-hand drive", "RL": "Right-hand drive"}
MARKETS = {
    "ECE": "Europe (ECE)", "EUR": "Europe", "US": "USA", "KANADA": "Canada",
    "JAPAN": "Japan", "CHINA": "China", "KOREA": "Korea", "THAILAND": "Thailand",
    "MALAYSIA": "Malaysia", "INDONESIEN": "Indonesia", "PHILIPPINEN": "Philippines",
    "INDIEN": "India", "AEGYPTEN": "Egypt", "RUSSLAND": "Russia", "MEXIKO": "Mexico",
    "BRASILIEN": "Brazil", "SUEDAFRIKA": "South Africa", "AUSTRALIEN": "Australia",
}

_ENGINE_RE = re.compile(r"^[MNSPW]\d{2}[A-Z]\d{2}[A-Z]?\d?$")
_ENGINE_SHORT_RE = re.compile(r"^[MNS]\d{2}$")
_CHASSIS_RE = re.compile(r"^[EFGRIK]\d{2}$")
_TYPE_LINE_RE = re.compile(r"^W ([A-Z0-9]{4})\s+(.*)$")
_PERIOD_RE = re.compile(r"\d{2}/\d{2}\s*-\s*(?:\d{2}/\d{2})?")
_BACKUP_DIR_RE = re.compile(r"_\d{8}_\d{6}$")

_TRANSLIT = {
    **{str(d): d for d in range(10)},
    "A": 1, "B": 2, "C": 3, "D": 4, "E": 5, "F": 6, "G": 7, "H": 8,
    "J": 1, "K": 2, "L": 3, "M": 4, "N": 5, "P": 7, "R": 9,
    "S": 2, "T": 3, "U": 4, "V": 5, "W": 6, "X": 7, "Y": 8, "Z": 9,
}
_WEIGHTS = [8, 7, 6, 5, 4, 3, 2, 10, 0, 9, 8, 7, 6, 5, 4, 3, 2]


# --- Type keys from NCS *AT.000 -------------------------------------------------


@dataclass
class TypeKeyInfo:
    code: str
    chassis: str = ""
    body: str = ""
    engine: str = ""
    drive_side: str = ""
    markets: list[str] = field(default_factory=list)
    cylinders: int = 0
    description: str = ""
    period: str = ""
    attributes: list[str] = field(default_factory=list)
    source: str = ""

    @property
    def title(self) -> str:
        return self.description or " ".join(x for x in (self.chassis, self.body, self.engine) if x)


def _at_files(daten_folder: str | Path) -> list[Path]:
    daten = Path(daten_folder)
    if not daten.is_dir():
        return []
    files: list[Path] = []
    seen_names: set[str] = set()
    # Chassis subfolders first (DATEN/E46/E46AT.000), then the DATEN root.
    candidates = sorted(daten.glob("*/*AT.000")) + sorted(daten.glob("*AT.000"))
    for path in candidates:
        parent = path.parent
        if parent != daten and _BACKUP_DIR_RE.search(parent.name):
            continue  # skip user backup folders
        if parent != daten and not path.name.upper().startswith(parent.name.upper()):
            continue  # e.g. DATEN/E39/E46AT.000 - a stray copy
        key = path.name.upper()
        if key in seen_names:
            continue
        seen_names.add(key)
        files.append(path)
    return files


def _parse_type_line(code: str, rest: str, chassis_hint: str, source: str) -> TypeKeyInfo:
    parts = rest.split("//")
    tokens = [t for t in parts[0].split() if not re.match(r"^[VN]\d{4}$|^=", t)]
    segments = [" ".join(p.split()) for p in parts[1:] if p.strip()]
    engine_tokens = {t for t in tokens if _ENGINE_RE.match(t)}
    # Drop engine-variant notes such as "N52B30oL KP (N52B30O1)"; keep the model text.
    readable = [s for s in segments if not any(s.startswith(e) for e in engine_tokens)]
    comment = " · ".join(readable or segments)

    info = TypeKeyInfo(code=code, source=source)
    for token in tokens:
        if not info.chassis and _CHASSIS_RE.match(token):
            info.chassis = token
        elif not info.body and token in BODY_NAMES:
            info.body = BODY_NAMES[token]
        elif not info.engine and _ENGINE_RE.match(token):
            info.engine = token
        elif not info.drive_side and token in DRIVE_SIDE:
            info.drive_side = DRIVE_SIDE[token]
        elif token in MARKETS:
            info.markets.append(MARKETS[token])
        else:
            info.attributes.append(token)
    if not info.engine:
        short = next((t for t in tokens if _ENGINE_SHORT_RE.match(t)), "")
        info.engine = short
        if short in info.attributes:
            info.attributes.remove(short)
    if not info.chassis:
        info.chassis = chassis_hint
    family = info.engine[:3]
    info.attributes = [
        t for t in info.attributes
        if not re.match(r"^[EFG]\dX$", t)            # series group, e.g. E9X
        and not (family and t.startswith(family))  # engine family / variant
        and t not in MARKETS
    ]
    cylinders = next((t for t in tokens if re.match(r"^ZYL\d+$", t)), "")
    if cylinders:
        info.attributes.remove(cylinders)
        info.cylinders = int(cylinders[3:])
    info.description = comment
    period = _PERIOD_RE.search(comment)
    info.period = period.group(0).replace(" ", "") if period else ""
    return info


def load_type_keys(daten_folder: str | Path) -> dict[str, list[TypeKeyInfo]]:
    """Read every type key ("W XX99 ..." line) from the NCS *AT.000 files."""
    result: dict[str, list[TypeKeyInfo]] = {}
    for path in _at_files(daten_folder):
        chassis_hint = path.name.upper().split("AT.")[0]
        try:
            lines = path.read_text(encoding="latin-1", errors="ignore").splitlines()
        except OSError:
            logger.exception("Cannot read %s", path)
            continue
        current: TypeKeyInfo | None = None
        for line in lines:
            if line.startswith(">>>") and current is not None:
                current.attributes.extend(line[3:].split("//")[0].split())
                continue
            current = None
            match = _TYPE_LINE_RE.match(line)
            if not match or match.group(1).isdigit():
                continue  # SA lines have 3-digit codes
            code = match.group(1)
            info = _parse_type_line(code, match.group(2), chassis_hint, path.name)
            entries = result.setdefault(code, [])
            if any(e.description == info.description and e.chassis == info.chassis for e in entries):
                continue  # same type listed again (summary section, date variants)
            entries.append(info)
            current = info
    return result


# --- Vehicle order (FA.TRC) -----------------------------------------------------


@dataclass
class FaInfo:
    raw: str
    chassis: str = ""
    production_date: str = ""  # MMYY
    type_key: str = ""
    sa_codes: list[str] = field(default_factory=list)
    e_words: list[str] = field(default_factory=list)
    ho_words: list[str] = field(default_factory=list)
    other_codes: list[str] = field(default_factory=list)

    @property
    def production_text(self) -> str:
        value = self.production_date
        if len(value) == 4 and value.isdigit():
            month, year = int(value[:2]), int(value[2:])
            year += 2000 if year < 80 else 1900
            if 1 <= month <= 12:
                return f"{month:02d}/{year}"
        return value


def parse_fa_string(text: str) -> FaInfo:
    """Split an NCS vehicle order like 'E46_#0903&G7AT%0A07*AT51$205-BFDY+XYZ'."""
    raw = (text or "").strip().splitlines()[0].strip() if (text or "").strip() else ""
    info = FaInfo(raw=raw)
    if not raw:
        return info
    body = raw
    if "_" in raw:
        info.chassis, body = raw.split("_", 1)
        info.chassis = info.chassis.strip().upper()
    for marker, value in re.findall(r"([#%&*$+\-])([^#%&*$+\-]*)", body):
        value = value.strip().upper()
        if not value:
            continue
        if marker == "#" and not info.production_date:
            info.production_date = value
        elif marker == "*" and not info.type_key:
            info.type_key = value
        elif marker == "$":
            info.sa_codes.append(value)
        elif marker == "-":
            info.e_words.append(value)
        elif marker == "+":
            info.ho_words.append(value)
        else:
            info.other_codes.append(marker + value)
    return info


def read_fa_file(path: str | Path) -> FaInfo | None:
    try:
        text = Path(path).read_text(encoding="latin-1", errors="ignore")
    except OSError:
        return None
    info = parse_fa_string(text)
    return info if info.raw else None


# --- VIN ------------------------------------------------------------------------


@dataclass
class VinField:
    positions: str
    chars: str
    meaning: str
    value: str
    status: str = "info"  # ok | warn | error | info


@dataclass
class VinReport:
    vin: str
    problems: list[str] = field(default_factory=list)
    fields: list[VinField] = field(default_factory=list)
    type_key: str = ""
    type_matches: list[TypeKeyInfo] = field(default_factory=list)
    short_vin: str = ""
    check_digit_expected: str = ""
    check_digit_ok: bool | None = None
    model_years: list[int] = field(default_factory=list)


def normalize_vin(text: str) -> str:
    return re.sub(r"[\s\-]", "", text or "").upper()


def check_digit(vin: str) -> str:
    """ISO 3779 / North American check digit for a 17-character VIN."""
    total = 0
    for char, weight in zip(vin, _WEIGHTS):
        value = _TRANSLIT.get(char)
        if value is None:
            return ""
        total += value * weight
    remainder = total % 11
    return "X" if remainder == 10 else str(remainder)


def model_years(code: str, today: date | None = None) -> list[int]:
    """Possible model years for position 10, newest first, never in the future."""
    if code not in _YEAR_CODES:
        return []
    today = today or date.today()
    index = _YEAR_CODES.index(code)
    years = [1980 + index, 2010 + index, 2040 + index]
    return sorted((y for y in years if y <= today.year + 1), reverse=True)


def decode_vin(text: str, type_keys: dict[str, list[TypeKeyInfo]] | None = None) -> VinReport:
    vin = normalize_vin(text)
    report = VinReport(vin=vin)
    if not vin:
        report.problems.append("No VIN entered.")
        return report

    if len(vin) != VIN_LENGTH:
        report.problems.append(f"The VIN has {len(vin)} characters; a VIN always has {VIN_LENGTH}.")
    bad = sorted({c for c in vin if c in FORBIDDEN_CHARS})
    if bad:
        report.problems.append(
            f"Contains {', '.join(bad)}: the letters I, O and Q are never used in a VIN "
            "(easily confused with 1 and 0)."
        )
    other = sorted({c for c in vin if not c.isalnum() or not c.isascii()})
    if other:
        report.problems.append(f"Contains characters that are not allowed: {' '.join(other)}")

    def part(start: int, end: int) -> str:
        return vin[start:end]

    wmi = part(0, 3)
    if wmi:
        name = WMI_NAMES.get(wmi)
        report.fields.append(VinField(
            "1-3", wmi, "Manufacturer (WMI)",
            name or "Not a known BMW / MINI manufacturer code",
            "ok" if name else "warn",
        ))

    type_key = part(3, 7)
    if len(type_key) == 4:
        report.type_key = type_key
        report.type_matches = list((type_keys or {}).get(type_key, []))
        if report.type_matches:
            value = "; ".join(m.title for m in report.type_matches)
            status = "ok"
        elif type_keys:
            value = "Not found in your NCS Expert data (older model or data not installed)"
            status = "warn"
        else:
            value = "NCS Expert DATEN folder not found, cannot look up"
            status = "warn"
        report.fields.append(VinField("4-7", type_key, "Type key (model, body, engine, market)", value, status))

    if len(vin) >= 8:
        report.fields.append(VinField(
            "8", part(7, 8), "Restraint system / version",
            "Used mainly on North American cars; often 0 elsewhere",
        ))

    if len(vin) >= 9:
        given = part(8, 9)
        expected = check_digit(vin) if len(vin) == VIN_LENGTH else ""
        report.check_digit_expected = expected
        if expected:
            report.check_digit_ok = given == expected
            value = (
                "Correct" if report.check_digit_ok
                else f"Does not match (expected {expected}). Required on North American cars; "
                     "a mismatch on a European car is not unusual, elsewhere it suggests a typo."
            )
            status = "ok" if report.check_digit_ok else "warn"
        else:
            value = "Cannot be checked (the VIN length or characters are wrong)"
            status = "warn"
        report.fields.append(VinField("9", given, "Check digit", value, status))

    if len(vin) >= 10:
        code = part(9, 10)
        report.model_years = model_years(code)
        if code == "0":
            value = "Not encoded (usual on European BMWs)"
        elif report.model_years:
            value = " or ".join(str(y) for y in report.model_years) + " (model year, North American cars)"
        else:
            value = "Not a model year code"
        report.fields.append(VinField("10", code, "Model year", value))

    if len(vin) >= 11:
        plant = part(10, 11)
        hint = PLANT_HINTS.get(plant)
        report.fields.append(VinField(
            "11", plant, "Assembly plant",
            f"Probably {hint} (unofficial, public lists disagree)" if hint
            else "Unknown (BMW does not publish an official list)",
        ))

    if len(vin) >= 12:
        report.fields.append(VinField("12-17", part(11, 17), "Serial number", "Production sequence number"))

    if len(vin) >= VIN_LENGTH:
        report.short_vin = part(10, 17)
        report.fields.append(VinField(
            "11-17", report.short_vin, "Short VIN",
            "The last 7 characters. NCS Expert, ISTA and the ECUs use this short form.",
        ))
    return report
