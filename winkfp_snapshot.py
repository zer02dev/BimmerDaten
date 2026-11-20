"""
winkfp_snapshot.py
Snapshots of a WinKFP installation and comparison between snapshots / backup folders.

A snapshot records every file of DATA, SGDAT, EDIABAS Ecu and the WinKFP
configuration (size + modification time; small, important files also get a
SHA-1). Snapshots are stored as JSON in %LOCALAPPDATA%\\BimmerDaten\\WinKFP_snapshots.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from winkfp_parser import NON_FAMILY_DIRS, WinkfpPaths, find_backup_dirs

logger = logging.getLogger("bimmerdaten.winkfp_snapshot")

SECTION_DATA = "DATA"
SECTION_SGDAT = "SGDAT"
SECTION_ECU = "ECU"
SECTION_CONFIG = "CONFIG"
SECTION_TITLES = {
    SECTION_DATA: "DATA (flash data)",
    SECTION_SGDAT: "SGDAT (PABD / CABD)",
    SECTION_ECU: "EDIABAS Ecu (SGBD)",
    SECTION_CONFIG: "WinKFP configuration",
}

# Content hashes are computed only for these (small) sections / folders.
HASH_SECTIONS = {SECTION_SGDAT, SECTION_CONFIG}
HASH_DATA_SUBDIRS = {"GDATEN"}
# WinKFP rebuilds this cache on every start - not a real change.
SKIP_DATA_SUBDIRS = {"KONV.TMP"}

CONFIG_FILES = ("BIN/Winkfpt.ini", "BIN/NFS.INI", "CFGDAT/COAPI.INI", "VERSION.TXT")


def get_snapshot_root() -> Path:
    appdata = os.environ.get("LOCALAPPDATA")
    base = Path(appdata) if appdata else (Path.home() / "AppData" / "Local")
    profile = (os.environ.get("BIMMERDATEN_PROFILE", "") or "").strip().lower()
    suffix = "-Dev" if profile in {"dev", "development"} else ""
    return base / f"BimmerDaten{suffix}" / "WinKFP_snapshots"


def _sha1(path: Path) -> str:
    digest = hashlib.sha1()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def scan_folder(folder: Path, hash_all: bool = False, hash_subdirs: set[str] | None = None,
                skip_subdirs: set[str] | None = None) -> dict[str, list]:
    """Return {relative/path (lower-case): [display path, size, mtime, sha1 or ""]} for all files."""
    result: dict[str, list] = {}
    if not folder.is_dir():
        return result
    hash_subdirs = {d.upper() for d in (hash_subdirs or set())}
    skip_subdirs = {d.upper() for d in (skip_subdirs or set())}
    stack = [folder]
    while stack:
        current = stack.pop()
        try:
            entries = list(os.scandir(current))
        except OSError:
            logger.exception("Cannot scan folder: %s", current)
            continue
        for entry in entries:
            if entry.is_dir(follow_symlinks=False):
                if current == folder and entry.name.upper() in skip_subdirs:
                    continue
                stack.append(Path(entry.path))
                continue
            if not entry.is_file(follow_symlinks=False):
                continue
            path = Path(entry.path)
            rel = path.relative_to(folder).as_posix()
            stat = entry.stat()
            top = rel.split("/", 1)[0].upper() if "/" in rel else ""
            digest = ""
            if hash_all or (top and top in hash_subdirs):
                try:
                    digest = _sha1(path)
                except OSError:
                    logger.exception("Cannot hash file: %s", path)
            result[rel.lower()] = [rel, stat.st_size, int(stat.st_mtime), digest]
    return result


@dataclass
class Snapshot:
    created: str
    nfs_root: str
    ecu_dir: str
    sections: dict[str, dict[str, list]] = field(default_factory=dict)
    backups: list[str] = field(default_factory=list)
    label: str = ""
    path: Path | None = None

    @property
    def created_dt(self) -> datetime | None:
        try:
            return datetime.fromisoformat(self.created)
        except ValueError:
            return None

    @property
    def title(self) -> str:
        stamp = self.created.replace("T", " ")
        return f"{stamp} — {self.label}" if self.label else stamp

    def to_json(self) -> dict:
        return {
            "created": self.created,
            "nfs_root": self.nfs_root,
            "ecu_dir": self.ecu_dir,
            "label": self.label,
            "backups": self.backups,
            "sections": self.sections,
        }

    @classmethod
    def from_json(cls, payload: dict, path: Path | None = None) -> "Snapshot":
        return cls(
            created=payload.get("created", ""),
            nfs_root=payload.get("nfs_root", ""),
            ecu_dir=payload.get("ecu_dir", ""),
            sections=payload.get("sections", {}),
            backups=payload.get("backups", []),
            label=payload.get("label", ""),
            path=path,
        )


def take_snapshot(paths: WinkfpPaths, label: str = "") -> Snapshot:
    config: dict[str, list] = {}
    for rel in CONFIG_FILES:
        file_path = paths.nfs_root / rel
        if file_path.is_file():
            stat = file_path.stat()
            config[rel.lower()] = [rel, stat.st_size, int(stat.st_mtime), _sha1(file_path)]
    return Snapshot(
        created=datetime.now().isoformat(timespec="seconds"),
        nfs_root=str(paths.nfs_root),
        ecu_dir=str(paths.ecu_dir),
        label=label,
        sections={
            SECTION_DATA: scan_folder(paths.data_dir, hash_subdirs=HASH_DATA_SUBDIRS, skip_subdirs=SKIP_DATA_SUBDIRS),
            SECTION_SGDAT: scan_folder(paths.sgdat_dir, hash_all=True),
            SECTION_ECU: scan_folder(paths.ecu_dir),
            SECTION_CONFIG: config,
        },
        backups=sorted(b.path.name for b in find_backup_dirs(paths.nfs_root)),
    )


def save_snapshot(snapshot: Snapshot, root: Path | None = None) -> Path:
    root = root or get_snapshot_root()
    root.mkdir(parents=True, exist_ok=True)
    stamp = (snapshot.created_dt or datetime.now()).strftime("%Y%m%d_%H%M%S")
    path = root / f"snapshot_{stamp}.json"
    suffix = 1
    while path.exists():
        path = root / f"snapshot_{stamp}_{suffix}.json"
        suffix += 1
    path.write_text(json.dumps(snapshot.to_json(), ensure_ascii=False), encoding="utf-8")
    snapshot.path = path
    return path


def list_snapshots(root: Path | None = None) -> list[Snapshot]:
    """Snapshots without file sections loaded are not supported; files are small enough to load."""
    root = root or get_snapshot_root()
    snapshots: list[Snapshot] = []
    if not root.is_dir():
        return snapshots
    for path in root.glob("snapshot_*.json"):
        try:
            snapshots.append(Snapshot.from_json(json.loads(path.read_text(encoding="utf-8")), path))
        except Exception:
            logger.exception("Invalid snapshot file: %s", path)
    return sorted(snapshots, key=lambda s: s.created, reverse=True)


def latest_snapshot(paths: WinkfpPaths, root: Path | None = None) -> Snapshot | None:
    """Latest snapshot taken for the same WinKFP folder."""
    for snapshot in list_snapshots(root):
        if Path(snapshot.nfs_root) == paths.nfs_root:
            return snapshot
    return None


# ---------------------------------------------------------------------------
# Comparison


@dataclass
class SectionDiff:
    section: str
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    changed: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.added) + len(self.removed) + len(self.changed)


@dataclass
class FamilyDiff:
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    changed: dict[str, int] = field(default_factory=dict)  # family -> number of changed files


@dataclass
class ComparisonResult:
    old_title: str
    new_title: str
    sections: dict[str, SectionDiff] = field(default_factory=dict)
    families: FamilyDiff = field(default_factory=FamilyDiff)
    new_backups: list[str] = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        return any(d.total for d in self.sections.values()) or bool(self.new_backups)

    @property
    def gdaten_changed(self) -> list[str]:
        diff = self.sections.get(SECTION_DATA)
        if diff is None:
            return []
        return [p for p in diff.added + diff.removed + diff.changed if p.lower().startswith("gdaten/")]


def _file_changed(old: list, new: list) -> bool:
    old_sha, new_sha = (old[3] if len(old) > 3 else ""), (new[3] if len(new) > 3 else "")
    if old_sha and new_sha:
        return old_sha != new_sha
    return old[1] != new[1] or old[2] != new[2]


def compare_sections(section: str, old: dict[str, list], new: dict[str, list]) -> SectionDiff:
    diff = SectionDiff(section=section)
    for key, value in new.items():
        if key not in old:
            diff.added.append(value[0])
        elif _file_changed(old[key], value):
            diff.changed.append(value[0])
    for key, value in old.items():
        if key not in new:
            diff.removed.append(value[0])
    for items in (diff.added, diff.removed, diff.changed):
        items.sort(key=str.lower)
    return diff


def _family_of(rel: str) -> str:
    if "/" not in rel:
        return ""
    top = rel.split("/", 1)[0].upper()
    return "" if top in NON_FAMILY_DIRS else top


def _families_in(files: dict[str, list]) -> set[str]:
    return {fam for fam in (_family_of(v[0]) for v in files.values()) if fam}


def compare_snapshots(old: Snapshot, new: Snapshot) -> ComparisonResult:
    result = ComparisonResult(old_title=old.title, new_title=new.title)
    for section in (SECTION_DATA, SECTION_SGDAT, SECTION_ECU, SECTION_CONFIG):
        if section not in old.sections and section not in new.sections:
            continue
        result.sections[section] = compare_sections(
            section, old.sections.get(section, {}), new.sections.get(section, {})
        )

    old_data = old.sections.get(SECTION_DATA, {})
    new_data = new.sections.get(SECTION_DATA, {})
    old_fams, new_fams = _families_in(old_data), _families_in(new_data)
    result.families.added = sorted(new_fams - old_fams)
    result.families.removed = sorted(old_fams - new_fams)
    data_diff = result.sections.get(SECTION_DATA)
    if data_diff is not None:
        counts: dict[str, int] = {}
        for rel in data_diff.added + data_diff.removed + data_diff.changed:
            fam = _family_of(rel)
            if fam and fam in old_fams and fam in new_fams:
                counts[fam] = counts.get(fam, 0) + 1
        result.families.changed = dict(sorted(counts.items()))

    result.new_backups = sorted(set(new.backups) - set(old.backups))
    return result


def folder_snapshot(folder: Path, section: str, label: str) -> Snapshot:
    """Snapshot of a single folder (e.g. a backup like DATA_20260509_004334) as one section."""
    if section == SECTION_SGDAT:
        files = scan_folder(folder, hash_all=True)
    elif section == SECTION_DATA:
        files = scan_folder(folder, hash_subdirs=HASH_DATA_SUBDIRS, skip_subdirs=SKIP_DATA_SUBDIRS)
    else:
        files = scan_folder(folder)
    try:
        created = datetime.fromtimestamp(folder.stat().st_mtime).isoformat(timespec="seconds")
    except OSError:
        created = ""
    return Snapshot(created=created, nfs_root="", ecu_dir="", sections={section: files}, label=label)


@dataclass
class BackupTarget:
    """A backup folder that can be compared with its current counterpart."""

    section: str
    backup_dir: Path
    current_dir: Path

    @property
    def title(self) -> str:
        return f"{self.backup_dir.name} ↔ current {self.current_dir.name}"


def list_backup_targets(paths: WinkfpPaths) -> list[BackupTarget]:
    targets: list[BackupTarget] = []
    for backup in find_backup_dirs(paths.nfs_root):
        base = backup.base.upper()
        if base == "DATA":
            targets.append(BackupTarget(SECTION_DATA, backup.path, paths.data_dir))
        elif base == "SGDAT":
            targets.append(BackupTarget(SECTION_SGDAT, backup.path, paths.sgdat_dir))
    ecu_parent = paths.ecu_dir.parent
    for backup in find_backup_dirs(ecu_parent):
        if backup.base.upper() == paths.ecu_dir.name.upper():
            targets.append(BackupTarget(SECTION_ECU, backup.path, paths.ecu_dir))
    return targets


def _verify_changed_by_content(diff: SectionDiff, old_files: dict[str, list], new_files: dict[str, list],
                               old_dir: Path, new_dir: Path) -> None:
    """Drop files that only differ in modification time (same size, same content)."""
    confirmed: list[str] = []
    for rel in diff.changed:
        key = rel.lower()
        old_entry, new_entry = old_files.get(key), new_files.get(key)
        if old_entry and new_entry and old_entry[1] == new_entry[1] and not (old_entry[3] and new_entry[3]):
            try:
                if _sha1(old_dir / old_entry[0]) == _sha1(new_dir / new_entry[0]):
                    continue
            except OSError:
                logger.exception("Cannot compare file content: %s", rel)
        confirmed.append(rel)
    diff.changed = confirmed


def compare_backup(target: BackupTarget) -> ComparisonResult:
    old = folder_snapshot(target.backup_dir, target.section, target.backup_dir.name)
    new = folder_snapshot(target.current_dir, target.section, f"current {target.current_dir.name}")
    result = compare_snapshots(old, new)
    section_diff = result.sections.get(target.section)
    if section_diff is not None and section_diff.changed:
        _verify_changed_by_content(
            section_diff, old.sections[target.section], new.sections[target.section],
            target.backup_dir, target.current_dir,
        )
        if target.section == SECTION_DATA:
            result.families.changed = {
                fam: count for fam, count in (
                    (fam, sum(1 for rel in section_diff.added + section_diff.removed + section_diff.changed
                              if _family_of(rel) == fam))
                    for fam in result.families.changed
                ) if count
            }
    result.old_title = target.backup_dir.name
    result.new_title = f"current {target.current_dir.name}"
    return result
