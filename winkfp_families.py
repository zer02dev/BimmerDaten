"""
winkfp_families.py
ECU family inventory for the WinKFP tab: status of every family, vehicle / engine
info from the flash file headers (cached), ZB table and restore from backups.
"""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from winkfp_parser import (
    DatEntry,
    FamilyFolder,
    InfoEntry,
    KfconfEntry,
    WinkfpPaths,
    find_backup_dirs,
    find_info_file,
    list_family_folders,
    list_files_ci,
    list_flash_files,
    load_kfconf,
    parse_dat,
    parse_flash_header,
    parse_his,
    parse_hwh,
    parse_info,
    read_install_info,
)

logger = logging.getLogger("bimmerdaten.winkfp_families")

STATUS_COMPLETE = "complete"
STATUS_INCOMPLETE = "incomplete"
STATUS_BACKUP_ONLY = "backup"
STATUS_NO_DATA = "nodata"

HEADER_KEYS = ("K_F1", "K_F2", "K_F3", "K_F4", "K_V1", "K_V2", "ZL_System", "ZL_Projekt")

# Chassis codes (E30..E99, F01..F99, R50..R69) and engine families (M40..M79, N40..N79, S50..S89).
_CHASSIS_RE = re.compile(r"(?<![A-Za-z0-9])(E[3-9]\d|F\d\d|R[56]\d)(?=x|[^0-9]|$)")
_ENGINE_RE = re.compile(r"(?<![A-Za-z0-9])([MN][4-7]\d|S[5-8]\d)(?=[A-Z]|B\d|\b|/)")


# ---------------------------------------------------------------------------
# Header cache


def get_cache_path() -> Path:
    appdata = os.environ.get("LOCALAPPDATA")
    base = Path(appdata) if appdata else (Path.home() / "AppData" / "Local")
    profile = (os.environ.get("BIMMERDATEN_PROFILE", "") or "").strip().lower()
    suffix = "-Dev" if profile in {"dev", "development"} else ""
    return base / f"BimmerDaten{suffix}" / "WinKFP_cache" / "flash_headers.json"


class HeaderCache:
    """Flash file header fields cached by path, size and modification time."""

    def __init__(self, path: Path | None = None):
        self.path = path or get_cache_path()
        self._data: dict[str, list] = {}
        self._dirty = False
        if self.path.is_file():
            try:
                self._data = json.loads(self.path.read_text(encoding="utf-8"))
            except Exception:
                logger.exception("Invalid header cache, rebuilding: %s", self.path)
                self._data = {}

    def get(self, file_path: Path) -> dict[str, str]:
        key = str(file_path).lower()
        try:
            stat = file_path.stat()
        except OSError:
            return {}
        cached = self._data.get(key)
        if cached and cached[0] == stat.st_size and cached[1] == int(stat.st_mtime):
            return cached[2]
        header = parse_flash_header(file_path, max_bytes=4096)
        fields = {k: header.get(k) for k in HEADER_KEYS if header.get(k)}
        self._data[key] = [stat.st_size, int(stat.st_mtime), fields]
        self._dirty = True
        return fields

    def save(self) -> None:
        if not self._dirty:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self._data, ensure_ascii=False), encoding="utf-8")
            self._dirty = False
        except OSError:
            logger.exception("Cannot write header cache: %s", self.path)


def describe_header(fields: dict[str, str]) -> str:
    """Short human readable description of a flash file, e.g. 'E89x / MT / 130 kW · N47 oL'."""
    vehicle = " / ".join(fields.get(f"K_F{i}", "") for i in range(1, 5) if fields.get(f"K_F{i}"))
    usage = " / ".join(v for v in (fields.get("K_V1", ""), fields.get("K_V2", "")) if v)
    parts = [p for p in (vehicle, usage) if p and p != "--"]
    if not parts and fields.get("ZL_Projekt"):
        parts.append(fields["ZL_Projekt"])
    return " · ".join(parts)


# ---------------------------------------------------------------------------
# Family records


@dataclass
class FamilyRecord:
    name: str
    status: str
    folder: FamilyFolder | None = None          # folder with the data (current DATA or backup)
    backup_name: str = ""                       # backup folder the data comes from (status backup)
    kfconf: KfconfEntry | None = None
    info: InfoEntry | None = None
    pabd_ok: bool = False
    psgbd_ok: bool = False
    problems: list[str] = field(default_factory=list)
    zb_count: int = 0
    chassis: set[str] = field(default_factory=set)
    engines: set[str] = field(default_factory=set)
    systems: set[str] = field(default_factory=set)

    @property
    def address(self) -> str:
        return self.kfconf.address if self.kfconf else (self.info.address if self.info else "")

    @property
    def description(self) -> str:
        return self.info.description if self.info else ""


def _family_problems(folder: FamilyFolder, entry: KfconfEntry | None, info: InfoEntry | None,
                     pabd_ok: bool, psgbd_ok: bool) -> tuple[list[str], int]:
    problems: list[str] = []
    for label, value in (("DAT", folder.dat_file), ("HIS", folder.his_file), ("HWH", folder.hwh_file)):
        if value is None:
            problems.append(f"{folder.name}.{label} missing")
    if entry is None:
        problems.append("no KFCONF entry (Comfort mode will not offer it)")
    else:
        if not pabd_ok:
            problems.append(f"PABD {entry.pabd} missing in SGDAT")
        if not psgbd_ok:
            problems.append(f"P-SGBD {entry.psgbd} missing in EDIABAS\\Ecu")
        if info is None:
            problems.append("no INFO entry (no integration position in Comfort mode)")
    zb_count = 0
    if folder.dat_file is not None:
        dat = parse_dat(folder.dat_file)
        zb_count = len(dat.entries)
        files = list_files_ci(folder.path)
        prefix = entry.data_prefix if entry else ""
        missing = 0
        for row in dat.entries:
            if row.program_file_name().lower() not in files:
                missing += 1
            elif prefix and row.has_data_file and row.data_file_name(prefix).lower() not in files:
                missing += 1
        if missing:
            problems.append(f"{missing} ZB number(s) with missing flash files")
    return problems, zb_count


def load_family_records(paths: WinkfpPaths, include_without_data: bool = True) -> list[FamilyRecord]:
    kfconf = {}
    for entry in load_kfconf(paths.gdaten_dir):
        kfconf.setdefault(entry.family.upper(), entry)
    language = read_install_info(paths).language or "ger"
    info_path = find_info_file(paths.gdaten_dir, language) or find_info_file(paths.gdaten_dir, "ger")
    infos = {e.family.upper(): e for e in parse_info(info_path).entries} if info_path else {}
    sgdat = list_files_ci(paths.sgdat_dir)
    ecu = list_files_ci(paths.ecu_dir)

    def checks(name: str) -> tuple[KfconfEntry | None, InfoEntry | None, bool, bool]:
        entry = kfconf.get(name)
        pabd_ok = bool(entry and entry.pabd.lower() in sgdat)
        psgbd_ok = bool(entry and entry.psgbd.lower() in ecu)
        return entry, infos.get(name), pabd_ok, psgbd_ok

    records: dict[str, FamilyRecord] = {}
    for folder in list_family_folders(paths.data_dir):
        entry, info, pabd_ok, psgbd_ok = checks(folder.name)
        problems, zb_count = _family_problems(folder, entry, info, pabd_ok, psgbd_ok)
        records[folder.name] = FamilyRecord(
            name=folder.name, status=STATUS_INCOMPLETE if problems else STATUS_COMPLETE,
            folder=folder, kfconf=entry, info=info, pabd_ok=pabd_ok, psgbd_ok=psgbd_ok,
            problems=problems, zb_count=zb_count,
        )

    # Families that exist only in update backups (newest backup wins).
    data_backups = [b for b in find_backup_dirs(paths.nfs_root) if b.base.upper() == "DATA"]
    for backup in sorted(data_backups, key=lambda b: b.created or 0, reverse=True):
        for folder in list_family_folders(backup.path):
            if folder.name in records or folder.dat_file is None:
                continue
            entry, info, pabd_ok, psgbd_ok = checks(folder.name)
            problems, zb_count = _family_problems(folder, entry, info, pabd_ok, psgbd_ok)
            records[folder.name] = FamilyRecord(
                name=folder.name, status=STATUS_BACKUP_ONLY, folder=folder, backup_name=backup.path.name,
                kfconf=entry, info=info, pabd_ok=pabd_ok, psgbd_ok=psgbd_ok,
                problems=problems, zb_count=zb_count,
            )

    if include_without_data:
        for name, entry in kfconf.items():
            if name in records:
                continue
            _, info, pabd_ok, psgbd_ok = checks(name)
            records[name] = FamilyRecord(
                name=name, status=STATUS_NO_DATA, kfconf=entry, info=info,
                pabd_ok=pabd_ok, psgbd_ok=psgbd_ok,
            )
    return sorted(records.values(), key=lambda r: r.name)


def enrich_with_headers(records: list[FamilyRecord], cache: HeaderCache) -> None:
    """Fill chassis / engines / systems from the flash file headers (slow first time, then cached)."""
    for record in records:
        if record.folder is None:
            continue
        for flash_file in list_flash_files(record.folder.path):
            fields = cache.get(flash_file)
            text = " ".join(fields.values())
            record.chassis.update(_CHASSIS_RE.findall(text))
            record.engines.update(_ENGINE_RE.findall(text))
            system = fields.get("ZL_System", "")
            if system and system != "--":
                record.systems.add(system)
    cache.save()


# ---------------------------------------------------------------------------
# ZB table


@dataclass
class ZbRow:
    entry: DatEntry
    program_file: str
    program_exists: bool
    data_file: str
    data_exists: bool
    latest_zb: str
    description: str


def load_zb_rows(record: FamilyRecord, cache: HeaderCache) -> list[ZbRow]:
    if record.folder is None or record.folder.dat_file is None:
        return []
    dat = parse_dat(record.folder.dat_file)
    files = list_files_ci(record.folder.path)
    his = parse_his(record.folder.his_file) if record.folder.his_file else None
    prefix = record.kfconf.data_prefix if record.kfconf else ""
    rows: list[ZbRow] = []
    for entry in dat.entries:
        program_name = entry.program_file_name()
        program_path = files.get(program_name.lower())
        data_name = entry.data_file_name(prefix) if (prefix and entry.has_data_file) else ""
        data_path = files.get(data_name.lower()) if data_name else None
        source = data_path or program_path
        description = describe_header(cache.get(source)) if source else ""
        latest = his.latest(entry.zb_nr)[-1] if his else entry.zb_nr
        rows.append(ZbRow(
            entry=entry,
            program_file=program_path.name if program_path else program_name,
            program_exists=program_path is not None,
            data_file=data_path.name if data_path else data_name,
            data_exists=data_path is not None or not data_name,
            latest_zb=latest if latest != entry.zb_nr else "",
            description=description,
        ))
    cache.save()
    return rows


def load_hwh_groups(record: FamilyRecord) -> list[list[str]]:
    if record.folder is None or record.folder.hwh_file is None:
        return []
    hwh = parse_hwh(record.folder.hwh_file)
    return [[f"{item.hw_nr}{item.index} ({item.status})" for item in group] for group in hwh.groups]
