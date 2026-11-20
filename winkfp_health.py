"""
winkfp_health.py
Health check of a WinKFP (NFS) installation and safe fixes with backup/restore.

All fixes are explicit, previewed in the UI and backed up before any file
is touched. Backups live in %LOCALAPPDATA%\\BimmerDaten\\WinKFP_backups and are
never written into the WinKFP folder itself.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from winkfp_parser import (
    IPO_KIND_PABD,
    KfconfEntry,
    WinkfpPaths,
    classify_ipo,
    find_backup_dirs,
    find_child_dir,
    find_info_file,
    find_kfconf_files,
    ipo_family_stem,
    ipo_version,
    list_family_folders,
    list_files_ci,
    load_kfconf,
    parse_dat,
    parse_info,
    read_install_info,
)

logger = logging.getLogger("bimmerdaten.winkfp_health")

SEVERITY_ERROR = "error"
SEVERITY_WARNING = "warning"
SEVERITY_INFO = "info"
SEVERITY_OK = "ok"
SEVERITY_ORDER = {SEVERITY_ERROR: 0, SEVERITY_WARNING: 1, SEVERITY_INFO: 2, SEVERITY_OK: 3}


# ---------------------------------------------------------------------------
# Fixes


@dataclass
class Fix:
    """Base class for an automatic fix."""

    description: str

    def target_files(self) -> list[Path]:
        raise NotImplementedError

    def preview(self) -> str:
        raise NotImplementedError

    def validate(self) -> str | None:
        """Return an error message if the fix can no longer be applied."""
        return None


@dataclass
class CopyFileFix(Fix):
    source: Path = Path()
    destination: Path = Path()

    def target_files(self) -> list[Path]:
        return [self.destination]

    def preview(self) -> str:
        return f"Copy {self.source.name} → {self.destination.name}\n  in {self.destination.parent}"

    def validate(self) -> str | None:
        if not self.source.is_file():
            return f"Source file not found: {self.source}"
        if self.destination.exists():
            return f"Destination already exists: {self.destination}"
        return None


@dataclass
class CopyFolderFix(Fix):
    """Copy a whole folder (e.g. an ECU family from a backup) to a destination that does not exist yet."""

    source: Path = Path()
    destination: Path = Path()

    def _source_files(self) -> list[Path]:
        if not self.source.is_dir():
            return []
        return sorted(p for p in self.source.rglob("*") if p.is_file())

    def target_files(self) -> list[Path]:
        return [self.destination / p.relative_to(self.source) for p in self._source_files()]

    def preview(self) -> str:
        files = self._source_files()
        size_mb = sum(p.stat().st_size for p in files) / (1024 * 1024)
        return (
            f"Copy folder {self.source.name} ({len(files)} files, {size_mb:.1f} MB)\n"
            f"  from {self.source.parent}\n  to   {self.destination.parent}"
        )

    def validate(self) -> str | None:
        if not self.source.is_dir():
            return f"Source folder not found: {self.source}"
        if self.destination.exists():
            return f"Destination already exists: {self.destination}"
        return None


@dataclass
class KfconfPabdFix(Fix):
    kfconf_path: Path = Path()
    line_no: int = 0
    family: str = ""
    old_pabd: str = ""
    new_pabd: str = ""

    def target_files(self) -> list[Path]:
        return [self.kfconf_path]

    def preview(self) -> str:
        return (
            f"{self.kfconf_path.name}, line {self.line_no} ({self.family}):\n"
            f"  PABD {self.old_pabd} → {self.new_pabd}"
        )

    def validate(self) -> str | None:
        if not self.kfconf_path.is_file():
            return f"File not found: {self.kfconf_path}"
        lines = self.kfconf_path.read_bytes().split(b"\n")
        if self.line_no < 1 or self.line_no > len(lines):
            return f"Line {self.line_no} not found in {self.kfconf_path.name}"
        fields = lines[self.line_no - 1].split()
        if len(fields) < 6 or fields[4].decode("latin-1") != self.family or fields[5].decode("latin-1") != self.old_pabd:
            return f"{self.kfconf_path.name} line {self.line_no} changed since the check — run the check again"
        return None


def _replace_field_keep_columns(line: bytes, old: bytes, new: bytes, field_index: int) -> bytes:
    """Replace a whitespace-separated field keeping the start column of the next field."""
    pos = 0
    for idx in range(field_index + 1):
        while pos < len(line) and line[pos:pos + 1].isspace():
            pos += 1
        start = pos
        while pos < len(line) and not line[pos:pos + 1].isspace():
            pos += 1
        if idx == field_index:
            if line[start:pos] != old:
                raise ValueError("field content does not match")
            end = pos
            next_start = end
            while next_start < len(line) and line[next_start:next_start + 1] in (b" ", b"\t"):
                next_start += 1
            available = next_start - start
            if len(new) < available:
                replacement = new + b" " * (available - len(new))
            else:
                replacement = new + b" "
            return line[:start] + replacement + line[next_start:]
    raise ValueError("field not found")


def _apply_kfconf_fix(fix: KfconfPabdFix) -> None:
    data = fix.kfconf_path.read_bytes()
    lines = data.split(b"\n")
    line = lines[fix.line_no - 1]
    has_cr = line.endswith(b"\r")
    body = line[:-1] if has_cr else line
    body = _replace_field_keep_columns(body, fix.old_pabd.encode("latin-1"), fix.new_pabd.encode("latin-1"), 5)
    lines[fix.line_no - 1] = body + (b"\r" if has_cr else b"")
    fix.kfconf_path.write_bytes(b"\n".join(lines))


# ---------------------------------------------------------------------------
# Backups


def get_backup_root() -> Path:
    appdata = os.environ.get("LOCALAPPDATA")
    base = Path(appdata) if appdata else (Path.home() / "AppData" / "Local")
    profile = (os.environ.get("BIMMERDATEN_PROFILE", "") or "").strip().lower()
    suffix = "-Dev" if profile in {"dev", "development"} else ""
    return base / f"BimmerDaten{suffix}" / "WinKFP_backups"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass
class BackupRecord:
    path: Path
    created: str
    description: str
    nfs_root: str
    files: list[dict] = field(default_factory=list)
    restored: bool = False

    @property
    def manifest_path(self) -> Path:
        return self.path / "manifest.json"

    def save(self) -> None:
        payload = {
            "created": self.created,
            "description": self.description,
            "nfs_root": self.nfs_root,
            "files": self.files,
            "restored": self.restored,
        }
        self.manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def list_backups(root: Path | None = None) -> list[BackupRecord]:
    root = root or get_backup_root()
    records: list[BackupRecord] = []
    if not root.is_dir():
        return records
    for child in root.iterdir():
        manifest = child / "manifest.json"
        if not manifest.is_file():
            continue
        try:
            payload = json.loads(manifest.read_text(encoding="utf-8"))
        except Exception:
            logger.exception("Invalid backup manifest: %s", manifest)
            continue
        records.append(BackupRecord(
            path=child,
            created=payload.get("created", ""),
            description=payload.get("description", ""),
            nfs_root=payload.get("nfs_root", ""),
            files=payload.get("files", []),
            restored=bool(payload.get("restored", False)),
        ))
    return sorted(records, key=lambda r: (r.created, r.path.name), reverse=True)


def is_winkfp_running() -> bool:
    try:
        output = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq winkfpt.exe", "/NH"],
            capture_output=True, text=True, timeout=10,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        ).stdout
    except Exception:
        logger.exception("tasklist failed")
        return False
    return "winkfpt.exe" in output.lower()


def apply_fixes(fixes: list[Fix], paths: WinkfpPaths, backup_root: Path | None = None) -> BackupRecord:
    """Back up every target file, then apply the fixes. Raises on validation errors."""
    problems = [msg for msg in (fix.validate() for fix in fixes) if msg]
    if problems:
        raise ValueError("\n".join(problems))

    root = backup_root or get_backup_root()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = root / stamp
    suffix = 1
    while backup_dir.exists():
        backup_dir = root / f"{stamp}_{suffix}"
        suffix += 1
    (backup_dir / "files").mkdir(parents=True)

    record = BackupRecord(
        path=backup_dir,
        created=datetime.now().isoformat(timespec="seconds"),
        description="; ".join(fix.description for fix in fixes),
        nfs_root=str(paths.nfs_root),
    )

    backed_up: dict[Path, dict] = {}
    for fix in fixes:
        for target in fix.target_files():
            if target in backed_up:
                continue
            try:
                rel = target.relative_to(paths.nfs_root)
            except ValueError:
                rel = Path(target.name)
            entry = {"path": str(target), "rel": str(rel)}
            if target.exists():
                dest = backup_dir / "files" / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, dest)
                entry["action"] = "modified"
                entry["sha_before"] = _sha256(target)
            else:
                entry["action"] = "created"
                # Remember folders that do not exist yet, so an undo removes only those.
                missing_dirs: list[str] = []
                folder = target.parent
                while not folder.exists() and folder != folder.parent:
                    missing_dirs.append(str(folder))
                    folder = folder.parent
                entry["created_dirs"] = missing_dirs
            backed_up[target] = entry
    record.files = list(backed_up.values())
    record.save()

    for fix in fixes:
        if isinstance(fix, CopyFileFix):
            shutil.copy2(fix.source, fix.destination)
        elif isinstance(fix, CopyFolderFix):
            shutil.copytree(fix.source, fix.destination)
        elif isinstance(fix, KfconfPabdFix):
            _apply_kfconf_fix(fix)
        elif callable(getattr(fix, "apply", None)):
            fix.apply()
        else:
            raise TypeError(f"Unknown fix type: {type(fix).__name__}")
        logger.info("Applied WinKFP fix: %s", fix.description)

    for entry in record.files:
        target = Path(entry["path"])
        if target.exists():
            entry["sha_after"] = _sha256(target)
    record.save()
    return record


def restore_backup(record: BackupRecord, force: bool = False) -> list[str]:
    """Restore files from a backup. Returns a list of messages (skipped files etc.)."""
    messages: list[str] = []
    for entry in record.files:
        target = Path(entry["path"])
        sha_after = entry.get("sha_after")
        if not force and target.exists() and sha_after and _sha256(target) != sha_after:
            messages.append(f"Skipped (changed since the fix): {target}")
            continue
        if entry.get("action") == "modified":
            source = record.path / "files" / entry["rel"]
            if not source.is_file():
                messages.append(f"Backup copy missing: {source}")
                continue
            shutil.copy2(source, target)
            messages.append(f"Restored: {target}")
        elif entry.get("action") == "created":
            if target.exists():
                target.unlink()
                messages.append(f"Removed: {target}")
    # Remove only folders that the fix itself created (and that are empty now).
    created_dirs = sorted(
        {Path(d) for e in record.files if e.get("action") == "created" for d in e.get("created_dirs", [])},
        key=lambda p: len(p.parts), reverse=True,
    )
    for folder in created_dirs:
        try:
            folder.rmdir()
        except OSError:
            pass
    record.restored = True
    record.save()
    return messages


# ---------------------------------------------------------------------------
# Health check


@dataclass
class Issue:
    severity: str
    category: str
    title: str
    details: str = ""
    family: str = ""
    fix: Fix | None = None


@dataclass
class HealthReport:
    paths: WinkfpPaths
    issues: list[Issue] = field(default_factory=list)
    checked_at: datetime = field(default_factory=datetime.now)

    def count(self, severity: str) -> int:
        return sum(1 for issue in self.issues if issue.severity == severity)

    @property
    def fixable(self) -> list[Issue]:
        return [issue for issue in self.issues if issue.fix is not None]


def _find_pabd_candidate(entry: KfconfEntry, sgdat_files: dict[str, Path], ipo_cache: dict[str, object]) -> Path | None:
    """Newest PABD in SGDAT with the same family stem as the configured one."""
    wanted_stems = {ipo_family_stem(entry.pabd), entry.family.upper()}
    candidates: list[Path] = []
    for name, path in sgdat_files.items():
        if not name.endswith(".ipo") or name.startswith("a_"):
            continue
        if ipo_family_stem(name) not in wanted_stems:
            continue
        info = ipo_cache.get(name)
        if info is None:
            info = classify_ipo(path)
            ipo_cache[name] = info
        if info.kind == IPO_KIND_PABD:
            candidates.append(path)
    if not candidates:
        return None
    return max(candidates, key=lambda p: ipo_version(p.name))


def run_health_check(paths: WinkfpPaths) -> HealthReport:
    report = HealthReport(paths=paths)
    issues = report.issues

    if not paths.nfs_root.is_dir():
        issues.append(Issue(
            SEVERITY_ERROR, "Installation", "WinKFP folder not found",
            f"{paths.nfs_root}\n\nSet the correct folder in the ⚙️ Installation tab.",
        ))
        return report
    if not (paths.bin_dir / "winkfpt.exe").exists():
        issues.append(Issue(SEVERITY_ERROR, "Installation", "winkfpt.exe not found", str(paths.bin_dir)))
    if not paths.ecu_dir.is_dir():
        issues.append(Issue(SEVERITY_ERROR, "Installation", "EDIABAS Ecu folder not found", str(paths.ecu_dir)))

    info = read_install_info(paths)

    # --- configuration -----------------------------------------------------
    coapi_setup = next((v for k, v in info.coapi_ini.items() if k.lower() == "setup"), {})
    coapi_format = coapi_setup.get("CabdFormat", "").strip().upper()
    if info.cabd_format and coapi_format and info.cabd_format != coapi_format:
        issues.append(Issue(
            SEVERITY_WARNING, "Configuration", "CabdFormat differs between WINKFPT.INI and COAPI.INI",
            f"WINKFPT.INI: {info.cabd_format}, COAPI.INI: {coapi_format}. "
            "The WinKFP manual requires both to be identical.",
        ))

    # --- INFO.<language> ---------------------------------------------------
    language = info.language or "ger"
    gdaten = paths.gdaten_dir
    info_path = find_info_file(gdaten, language)
    expected_info = f"INFO.{'ENG' if language == 'eng' else 'GER'}"
    info_families: set[str] = set()
    if info_path is None:
        source = find_info_file(gdaten, "ger") or find_info_file(gdaten, "eng")
        details = (
            f"WINKFPT.INI uses SPRACHE={language}, so WinKFP reads {expected_info} from {gdaten}. "
            "The file is missing: WinKFP logs COAPI error 1020 at start-up and Comfort mode "
            "(Choose ZUSB / Update ZUSB) shows no integration positions."
        )
        fix = None
        if source is not None:
            details += f"\n\nFix: copy {source.name} as {expected_info}. The WinKFP user interface stays in English."
            fix = CopyFileFix(
                description=f"Create {expected_info} from {source.name}",
                source=source, destination=gdaten / expected_info,
            )
            info_families = {e.family.upper() for e in parse_info(source).entries}
        issues.append(Issue(SEVERITY_ERROR, "gdaten", f"{expected_info} missing", details, fix=fix))
    else:
        info_families = {e.family.upper() for e in parse_info(info_path).entries}

    # --- KFCONF vs DATA / SGDAT / Ecu ---------------------------------------
    kfconf_files = find_kfconf_files(gdaten)
    if not kfconf_files:
        issues.append(Issue(SEVERITY_ERROR, "gdaten", "KFCONF??.DA2 missing", f"No kfconf??.da2 in {gdaten}"))
    kfconf_by_family: dict[str, KfconfEntry] = {}
    for entry in load_kfconf(gdaten):
        kfconf_by_family.setdefault(entry.family.upper(), entry)
    kfconf_paths = {p.name: p for p in kfconf_files}

    sgdat_files = list_files_ci(paths.sgdat_dir)
    ecu_files = list_files_ci(paths.ecu_dir)
    ipo_cache: dict[str, object] = {}

    families = list_family_folders(paths.data_dir)
    family_names = {f.name for f in families}
    ok_families: list[str] = []

    for family in families:
        name = family.name
        family_ok = True
        entry = kfconf_by_family.get(name)

        missing = [label for label, value in (("DAT", family.dat_file), ("HIS", family.his_file), ("HWH", family.hwh_file)) if value is None]
        if missing:
            family_ok = False
            issues.append(Issue(
                SEVERITY_ERROR, "Family data", f"{name}: logistics file(s) missing: {', '.join(missing)}",
                f"Folder {family.path} has no {', '.join(name + '.' + m for m in missing)}. "
                "Comfort mode needs DAT, HIS and HWH (COAPI error 1020 on [Program]).",
                family=name,
            ))

        if entry is None:
            family_ok = False
            issues.append(Issue(
                SEVERITY_WARNING, "KFCONF", f"{name}: no KFCONF entry",
                "The family folder exists in DATA but KFCONF has no line for it. "
                "Comfort mode will not offer it; Expert mode still works with manual selection.",
                family=name,
            ))
        else:
            if entry.pabd.lower() not in sgdat_files:
                family_ok = False
                candidate = _find_pabd_candidate(entry, sgdat_files, ipo_cache)
                details = (
                    f"KFCONF ({entry.source_file}, line {entry.line_no}) points to PABD {entry.pabd}, "
                    f"which is not in {paths.sgdat_dir}. WinKFP shows COAPI error 1065/1000 and "
                    "WinKFP error 106 when this family is selected in Comfort mode."
                )
                fix = None
                if candidate is not None:
                    cand_info = ipo_cache.get(candidate.name.lower())
                    details += (
                        f"\n\nAvailable flash PABD for this family: {candidate.name}"
                        f" (version {ipo_version(candidate.name)} instead of {ipo_version(entry.pabd)})."
                    )
                    refs = sorted(
                        ident for ident in getattr(cand_info, "identifiers", set())
                        if re.fullmatch(r"\d{2}[A-Za-z0-9_]+", ident)
                        and f"{ident.lower()}.prg" in ecu_files
                        and ident.upper() != Path(entry.psgbd).stem.upper()
                        and ident.upper() != Path(candidate.name).stem.upper()
                    )
                    if refs:
                        details += (
                            f"\nNote: {candidate.name} also mentions SGBD {', '.join(refs)} "
                            f"(KFCONF uses {entry.psgbd}). If flashing fails with SGBD errors, "
                            "use Expert mode with that P-SGBD."
                        )
                    fix = KfconfPabdFix(
                        description=f"KFCONF {name}: PABD {entry.pabd} → {candidate.name}",
                        kfconf_path=kfconf_paths.get(entry.source_file, gdaten / entry.source_file),
                        line_no=entry.line_no, family=entry.family,
                        old_pabd=entry.pabd, new_pabd=candidate.name,
                    )
                else:
                    details += "\n\nNo flash PABD for this family exists in SGDAT — it has to come from an SP-Daten package."
                issues.append(Issue(SEVERITY_ERROR, "KFCONF", f"{name}: PABD {entry.pabd} missing", details, family=name, fix=fix))

            if entry.psgbd.lower() not in ecu_files:
                family_ok = False
                issues.append(Issue(
                    SEVERITY_ERROR, "KFCONF", f"{name}: P-SGBD {entry.psgbd} missing",
                    f"KFCONF points to {entry.psgbd}, which is not in {paths.ecu_dir}. "
                    "WinKFP shows COAPI error 2000 / WinKFP error 106.",
                    family=name,
                ))

            if name not in info_families:
                family_ok = False
                issues.append(Issue(
                    SEVERITY_WARNING, "gdaten", f"{name}: no INFO entry",
                    "Comfort mode cannot offer an integration position (ECU address) for this family.",
                    family=name,
                ))

        if family.dat_file is not None:
            dat = parse_dat(family.dat_file)
            files = list_files_ci(family.path)
            prefix = entry.data_prefix if entry else ""
            missing_prog = sorted({d.program_file_name() for d in dat.entries if d.program_file_name().lower() not in files})
            missing_data = sorted({
                d.data_file_name(prefix) for d in dat.entries
                if prefix and d.has_data_file and d.data_file_name(prefix).lower() not in files
            })
            if missing_prog or missing_data:
                family_ok = False
                sample = ", ".join((missing_prog + missing_data)[:8])
                issues.append(Issue(
                    SEVERITY_WARNING, "Family data",
                    f"{name}: {len(missing_prog) + len(missing_data)} flash file(s) referenced in {name}.DAT missing",
                    f"Program files missing: {len(missing_prog)}, data files missing: {len(missing_data)}.\n"
                    f"Examples: {sample}\nZB numbers using these files cannot be flashed (COAPI error 4204).",
                    family=name,
                ))

        if family_ok:
            ok_families.append(name)

    if ok_families:
        issues.append(Issue(
            SEVERITY_OK, "Family data", f"{len(ok_families)} famil{'y' if len(ok_families) == 1 else 'ies'} complete",
            ", ".join(ok_families),
        ))

    # --- KFCONF entries without data ----------------------------------------
    without_data = [e for fam, e in kfconf_by_family.items() if fam not in family_names]
    if without_data:
        issues.append(Issue(
            SEVERITY_INFO, "KFCONF",
            f"{len(without_data)} KFCONF families have no data in DATA",
            "These ECU families are known to WinKFP but no data set is installed, so they cannot be flashed. "
            "This is normal — only families from installed SP-Daten packages can be used.",
        ))

    # --- families only present in backups ------------------------------------
    backup_only: dict[str, list[str]] = {}
    for backup in find_backup_dirs(paths.nfs_root):
        if backup.base.upper() != "DATA":
            continue
        for fam in list_family_folders(backup.path):
            if fam.name not in family_names and fam.dat_file is not None:
                backup_only.setdefault(fam.name, []).append(backup.path.name)
    if backup_only:
        lines = [f"{fam}: {', '.join(dirs)}" for fam, dirs in sorted(backup_only.items())]
        issues.append(Issue(
            SEVERITY_WARNING, "Backups",
            f"{len(backup_only)} families exist only in backup folders",
            "These families were in DATA before an update and are now missing:\n"
            + "\n".join(lines)
            + "\n\nThey can be restored in the Families tab (stage E5).",
        ))

    issues.sort(key=lambda i: (SEVERITY_ORDER.get(i.severity, 9), i.category, i.family, i.title))
    return report
