"""
winkfp_presets.py
Named Expert-mode presets for WinKFP and loading them into WINKFPT.INI.

WinKFP keeps exactly one Expert-mode configuration in WINKFPT.INI, section
[Expert-Modus-Konfiguration]; it offers it when Expert mode is entered. In Expert
mode the file dialogs for data / program / NAAB files only list DATA\\DEVELOP, so
loading a preset also copies the needed flash files there.

Values are written in the same form as WinKFP's batch control files
(MF_PABD=21EK928.IPO, MF_SG_ADR=12, MF_DATEN_DATEI=Q7525491.0DA ...).
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from winkfp_health import CopyFileFix, Fix
from winkfp_parser import (
    ENCODING,
    IPO_KIND_CABD,
    classify_ipo,
    WinkfpPaths,
    find_backup_dirs,
    find_child_dir,
    find_child_file,
    list_files_ci,
    read_install_info,
)

logger = logging.getLogger("bimmerdaten.winkfp_presets")

EXPERT_SECTION = "Expert-Modus-Konfiguration"
EXPERT_KEYS = (
    "KF_HW_INTERFACE", "KF_DIAG_PROT", "KF_PSGBD", "KF_PABD", "KF_SG_ADR",
    "KF_DATEN_DATEI", "KF_PROGRAMM_DATEI", "KF_HW_INTERFACE_UNIT", "KF_NAAB_DATEI",
)


def get_presets_path() -> Path:
    appdata = os.environ.get("LOCALAPPDATA")
    base = Path(appdata) if appdata else (Path.home() / "AppData" / "Local")
    profile = (os.environ.get("BIMMERDATEN_PROFILE", "") or "").strip().lower()
    suffix = "-Dev" if profile in {"dev", "development"} else ""
    return base / f"BimmerDaten{suffix}" / "winkfp_presets.json"


@dataclass
class ExpertPreset:
    name: str
    family: str = ""
    zb_nr: str = ""
    pabd: str = ""
    psgbd: str = ""
    address: str = ""
    program_file: str = ""
    data_file: str = ""
    naab_file: str = ""
    hw_interface: str = ""
    hw_unit: str = ""
    diag_protocol: str = ""
    notes: str = ""
    created: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))

    def ini_values(self) -> dict[str, str]:
        return {
            "KF_HW_INTERFACE": self.hw_interface,
            "KF_DIAG_PROT": self.diag_protocol,
            "KF_PSGBD": self.psgbd,
            "KF_PABD": self.pabd,
            "KF_SG_ADR": self.address,
            "KF_DATEN_DATEI": self.data_file,
            "KF_PROGRAMM_DATEI": self.program_file,
            "KF_HW_INTERFACE_UNIT": self.hw_unit,
            "KF_NAAB_DATEI": self.naab_file,
        }

    @classmethod
    def from_ini_values(cls, name: str, values: dict[str, str]) -> "ExpertPreset":
        get = lambda key: (values.get(key) or "").strip()  # noqa: E731
        return cls(
            name=name, pabd=get("KF_PABD"), psgbd=get("KF_PSGBD"), address=get("KF_SG_ADR"),
            program_file=get("KF_PROGRAMM_DATEI"), data_file=get("KF_DATEN_DATEI"),
            naab_file=get("KF_NAAB_DATEI"), hw_interface=get("KF_HW_INTERFACE"),
            hw_unit=get("KF_HW_INTERFACE_UNIT"), diag_protocol=get("KF_DIAG_PROT"),
        )


def load_presets(path: Path | None = None) -> list[ExpertPreset]:
    path = path or get_presets_path()
    if not path.is_file():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        logger.exception("Invalid presets file: %s", path)
        return []
    known = set(ExpertPreset.__dataclass_fields__)
    return [ExpertPreset(**{k: v for k, v in item.items() if k in known}) for item in payload if item.get("name")]


def save_presets(presets: list[ExpertPreset], path: Path | None = None) -> None:
    path = path or get_presets_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([asdict(p) for p in presets], ensure_ascii=False, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# WINKFPT.INI


def winkfpt_ini_path(paths: WinkfpPaths) -> Path:
    return find_child_file(paths.bin_dir, "Winkfpt.ini") or (paths.bin_dir / "Winkfpt.ini")


def read_current_expert_config(paths: WinkfpPaths) -> dict[str, str]:
    return read_install_info(paths).expert_config


def hw_interfaces(paths: WinkfpPaths) -> list[tuple[str, str]]:
    """(label, value) pairs from the [HW-Interface] section of WINKFPT.INI."""
    info = read_install_info(paths)
    section = next((v for k, v in info.winkfpt_ini.items() if k.lower() == "hw-interface"), {})
    return [(label, value) for label, value in section.items()]


def update_ini_section(text: str, section: str, values: dict[str, str]) -> str:
    """Set keys in one INI section, keeping every other line (comments, order, CRLF) untouched."""
    newline = "\r\n" if "\r\n" in text else "\n"
    lines = text.split(newline)
    header = f"[{section}]".lower()
    start = next((i for i, line in enumerate(lines) if line.strip().lower() == header), None)
    if start is None:
        while lines and lines[-1] == "":
            lines.pop()
        lines.append(f"[{section}]")
        lines.extend(f"{key}={value}" for key, value in values.items())
        lines.append("")
        return newline.join(lines)

    end = start + 1
    while end < len(lines) and not lines[end].strip().startswith("["):
        end += 1
    remaining = dict(values)
    for idx in range(start + 1, end):
        stripped = lines[idx].strip()
        if not stripped or stripped.startswith(";") or "=" not in stripped:
            continue
        key = stripped.split("=", 1)[0].strip()
        match = next((k for k in remaining if k.lower() == key.lower()), None)
        if match is not None:
            lines[idx] = f"{key}={remaining.pop(match)}"
    insert_at = end
    while insert_at > start + 1 and not lines[insert_at - 1].strip():
        insert_at -= 1
    for offset, (key, value) in enumerate(remaining.items()):
        lines.insert(insert_at + offset, f"{key}={value}")
    return newline.join(lines)


@dataclass
class IniSectionFix(Fix):
    """Write keys of one INI section (used for the Expert-mode configuration)."""

    ini_path: Path = Path()
    section: str = EXPERT_SECTION
    values: dict[str, str] = field(default_factory=dict)

    def target_files(self) -> list[Path]:
        return [self.ini_path]

    def preview(self) -> str:
        body = "\n".join(f"  {key}={value}" for key, value in self.values.items())
        return f"{self.ini_path.name} [{self.section}]:\n{body}"

    def validate(self) -> str | None:
        if not self.ini_path.is_file():
            return f"File not found: {self.ini_path}"
        return None

    def apply(self) -> None:
        text = self.ini_path.read_bytes().decode(ENCODING)
        self.ini_path.write_bytes(update_ini_section(text, self.section, self.values).encode(ENCODING))


# ---------------------------------------------------------------------------
# Loading a preset into WinKFP


def develop_dir(paths: WinkfpPaths) -> Path:
    return find_child_dir(paths.data_dir, "DEVELOP") or (paths.data_dir / "DEVELOP")


def find_flash_file(paths: WinkfpPaths, family: str, file_name: str) -> Path | None:
    """Find a flash file in DATA\\<family>, DATA\\DEVELOP or a DATA backup folder."""
    if not file_name:
        return None
    candidates: list[Path] = []
    if family:
        folder = find_child_dir(paths.data_dir, family)
        if folder:
            candidates.append(folder)
    candidates.append(develop_dir(paths))
    for backup in find_backup_dirs(paths.nfs_root):
        if backup.base.upper() == "DATA" and family:
            folder = find_child_dir(backup.path, family)
            if folder:
                candidates.append(folder)
    for folder in candidates:
        match = list_files_ci(folder).get(file_name.lower())
        if match is not None:
            return match
    return None


@dataclass
class LoadPlan:
    fixes: list[Fix]
    messages: list[str]
    errors: list[str]


def plan_load(preset: ExpertPreset, paths: WinkfpPaths) -> LoadPlan:
    fixes: list[Fix] = []
    messages: list[str] = []
    errors: list[str] = []

    sgdat = list_files_ci(paths.sgdat_dir)
    ecu = list_files_ci(paths.ecu_dir)
    if preset.pabd and preset.pabd.lower() not in sgdat:
        errors.append(f"PABD {preset.pabd} is not in SGDAT.")
    elif preset.pabd and classify_ipo(sgdat[preset.pabd.lower()]).kind == IPO_KIND_CABD:
        errors.append(
            f"{preset.pabd} is a coding file (CABD) for NCS Expert, not a flash PABD — WinKFP would fail with error 1063."
        )
    if preset.psgbd and preset.psgbd.lower() not in ecu:
        errors.append(f"P-SGBD {preset.psgbd} is not in EDIABAS\\Ecu.")
    if preset.address and not (len(preset.address) <= 2 and all(c in "0123456789abcdefABCDEF" for c in preset.address)):
        errors.append(f"ECU address '{preset.address}' must be a 2-digit hexadecimal number (e.g. 12).")

    develop = develop_dir(paths)
    develop_files = list_files_ci(develop)
    for label, name in (("program", preset.program_file), ("data", preset.data_file), ("NAAB", preset.naab_file)):
        if not name:
            continue
        if name.lower() in develop_files:
            messages.append(f"{label.capitalize()} file {name} is already in DATA\\DEVELOP.")
            continue
        source = find_flash_file(paths, preset.family, name)
        if source is None:
            errors.append(f"{label.capitalize()} file {name} was not found (DATA\\{preset.family or '?'}, DEVELOP, backups).")
            continue
        if paths.data_dir not in source.parents:
            messages.append(f"{name} is copied from the backup folder {source.parent.parent.name}.")
        fixes.append(CopyFileFix(
            description=f"Copy {name} to DATA\\DEVELOP (Expert mode file list)",
            source=source, destination=develop / source.name,
        ))

    ini_path = winkfpt_ini_path(paths)
    fixes.append(IniSectionFix(
        description=f"Load preset '{preset.name}' into WINKFPT.INI",
        ini_path=ini_path, values=preset.ini_values(),
    ))
    return LoadPlan(fixes=fixes, messages=messages, errors=errors)
