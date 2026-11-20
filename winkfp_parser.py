"""
winkfp_parser.py
Read-only parsers for BMW WinKFP (NFS) installation files.

Covers:
- configuration: WINKFPT.INI, COAPI.INI, NFS.INI, VERSION.TXT
- global logistics (DATA\\gdaten): KFCONF??.DA2, INFO.<lang>, HWNR.DA2
- ECU family logistics (DATA\\<family>): <family>.DAT, .HIS, .HWH
- flash data sets (*.0PA / *.0DA / *.0BA) - text header only
- PABD / CABD object files (SGDAT\\*.ipo) - heuristic classification
- WinKFP error logs (ERROR_<IF>_<unit>.LOG) and COAPI/EDIABAS error texts

Nothing in this module writes to the WinKFP installation.
"""
from __future__ import annotations

import configparser
import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("bimmerdaten.winkfp_parser")

ENCODING = "latin-1"

DEFAULT_NFS_ROOT = Path(r"C:\EC-APPS\NFS")
DEFAULT_ECU_DIR = Path(r"C:\EDIABAS\Ecu")

# Folders in DATA that are not ECU families.
NON_FAMILY_DIRS = {"GDATEN", "DEVELOP", "KONV", "KONV.TMP"}

# Backup folders created by update tools, e.g. SGDAT_20260509_002519.
BACKUP_DIR_RE = re.compile(r"^(?P<base>.+)_(?P<date>\d{8})_(?P<time>\d{6})$")


# ---------------------------------------------------------------------------
# Paths and config


def _normalize_profile_name(raw_value: str) -> str:
    profile = (raw_value or "").strip().lower()
    if profile in {"dev", "development"}:
        return "Dev"
    return ""


def get_config_path() -> Path:
    appdata = os.environ.get("LOCALAPPDATA")
    base = Path(appdata) if appdata else (Path.home() / "AppData" / "Local")
    profile = _normalize_profile_name(os.environ.get("BIMMERDATEN_PROFILE", ""))
    suffix = f"-{profile}" if profile else ""
    return base / f"BimmerDaten{suffix}" / "winkfp_paths.json"


@dataclass
class WinkfpPaths:
    nfs_root: Path = DEFAULT_NFS_ROOT
    ecu_dir: Path = DEFAULT_ECU_DIR

    @property
    def bin_dir(self) -> Path:
        return self.nfs_root / "BIN"

    @property
    def cfgdat_dir(self) -> Path:
        return self.nfs_root / "CFGDAT"

    @property
    def data_dir(self) -> Path:
        return self.nfs_root / "DATA"

    @property
    def gdaten_dir(self) -> Path:
        return find_child_dir(self.data_dir, "gdaten") or (self.data_dir / "gdaten")

    @property
    def sgdat_dir(self) -> Path:
        return self.nfs_root / "SGDAT"

    @property
    def work_dir(self) -> Path:
        return self.nfs_root / "WORK"

    @property
    def trace_dir(self) -> Path:
        return self.nfs_root / "TRACE"

    def is_valid(self) -> bool:
        return (self.bin_dir / "winkfpt.exe").exists() or (self.data_dir.exists() and self.sgdat_dir.exists())


def load_paths() -> WinkfpPaths:
    config_path = get_config_path()
    if not config_path.exists():
        return WinkfpPaths()
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        logger.exception("Failed to read WinKFP paths config: %s", config_path)
        return WinkfpPaths()
    return WinkfpPaths(
        nfs_root=Path(payload.get("nfs_root") or DEFAULT_NFS_ROOT),
        ecu_dir=Path(payload.get("ecu_dir") or DEFAULT_ECU_DIR),
    )


def save_paths(paths: WinkfpPaths) -> None:
    config_path = get_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"nfs_root": str(paths.nfs_root), "ecu_dir": str(paths.ecu_dir)}
    config_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Generic helpers


def read_lines(path: Path) -> list[str]:
    """Read a WinKFP text file (latin-1, CRLF) and return lines without line endings."""
    return path.read_text(encoding=ENCODING, errors="replace").splitlines()


def find_child_dir(parent: Path, name: str) -> Path | None:
    """Case-insensitive lookup of a sub-directory."""
    if not parent.is_dir():
        return None
    direct = parent / name
    if direct.is_dir():
        return direct
    lowered = name.lower()
    for child in parent.iterdir():
        if child.is_dir() and child.name.lower() == lowered:
            return child
    return None


def find_child_file(parent: Path, name: str) -> Path | None:
    """Case-insensitive lookup of a file."""
    if not parent.is_dir():
        return None
    direct = parent / name
    if direct.is_file():
        return direct
    lowered = name.lower()
    for child in parent.iterdir():
        if child.is_file() and child.name.lower() == lowered:
            return child
    return None


def list_files_ci(folder: Path) -> dict[str, Path]:
    """Map lower-case file name -> path for all files in a folder."""
    if not folder.is_dir():
        return {}
    return {p.name.lower(): p for p in folder.iterdir() if p.is_file()}


def read_ini(path: Path) -> dict[str, dict[str, str]]:
    """Read a Windows INI file into {section: {key: value}} keeping key case."""
    parser = configparser.ConfigParser(
        strict=False,
        interpolation=None,
        comment_prefixes=(";", "#"),
        inline_comment_prefixes=(";",),
        delimiters=("=",),
    )
    parser.optionxform = str  # keep key case
    try:
        parser.read_string(path.read_text(encoding=ENCODING, errors="replace"))
    except configparser.Error:
        logger.exception("Failed to parse INI file: %s", path)
        return {}
    return {section: dict(parser.items(section)) for section in parser.sections()}


# ---------------------------------------------------------------------------
# Installation info


@dataclass
class WinkfpInstallInfo:
    version_line: str = ""
    nfs_version: str = ""
    winkfp_version: str = ""
    kmm_version: str = ""
    language: str = ""
    cabd_format: str = ""
    winkfpt_ini: dict[str, dict[str, str]] = field(default_factory=dict)
    coapi_ini: dict[str, dict[str, str]] = field(default_factory=dict)
    nfs_ini: dict[str, dict[str, str]] = field(default_factory=dict)

    @property
    def expert_config(self) -> dict[str, str]:
        for name, values in self.winkfpt_ini.items():
            if name.lower() == "expert-modus-konfiguration":
                return values
        return {}


def read_install_info(paths: WinkfpPaths) -> WinkfpInstallInfo:
    info = WinkfpInstallInfo()

    version_file = find_child_file(paths.nfs_root, "VERSION.TXT")
    if version_file:
        lines = [line.strip() for line in read_lines(version_file) if line.strip()]
        if lines:
            info.version_line = lines[0]
            parts = lines[0].split("/")
            names = lines[1].split("/") if len(lines) > 1 else []
            for idx, value in enumerate(parts):
                name = names[idx].lower() if idx < len(names) else ""
                if name == "nfs":
                    info.nfs_version = value
                elif name.startswith("winkfp"):
                    info.winkfp_version = value
                elif name == "kmm":
                    info.kmm_version = value

    winkfpt_ini = find_child_file(paths.bin_dir, "Winkfpt.ini")
    if winkfpt_ini:
        info.winkfpt_ini = read_ini(winkfpt_ini)
        settings = next((v for k, v in info.winkfpt_ini.items() if k.lower() == "einstellungen"), {})
        info.language = settings.get("SPRACHE", "").strip().lower()
        info.cabd_format = settings.get("CabdFormat", "").strip().upper()

    coapi_ini = find_child_file(paths.cfgdat_dir, "COAPI.INI")
    if coapi_ini:
        info.coapi_ini = read_ini(coapi_ini)

    nfs_ini = find_child_file(paths.bin_dir, "NFS.INI")
    if nfs_ini:
        info.nfs_ini = read_ini(nfs_ini)

    return info


# ---------------------------------------------------------------------------
# Global logistics: KFCONF, INFO, HWNR


@dataclass
class KfconfEntry:
    ecu_index: str      # 2-char family index, e.g. "WB"
    address: str        # diagnostic address (hex), e.g. "12"
    prio: str           # "01"
    family: str         # ECU family, e.g. "DDE71"
    pabd: str           # flash sequence description, e.g. "03DDE71.IPO"
    psgbd: str          # programming SGBD, e.g. "00DDE71.PRG"
    flash_type: str     # e.g. "XXFLKP", "RBFLD2"
    his_file: str
    dat_file: str
    data_prefix: str    # prefix letter of data set files (*.0DA)
    dir_file: str
    hwh_file: str
    line_no: int = 0
    source_file: str = ""

    @property
    def address_int(self) -> int | None:
        try:
            return int(self.address, 16)
        except ValueError:
            return None


def find_kfconf_files(gdaten_dir: Path) -> list[Path]:
    """WinKFP reads every kfconf??.da2 in gdaten."""
    if not gdaten_dir.is_dir():
        return []
    pattern = re.compile(r"^kfconf\d\d\.da2$", re.IGNORECASE)
    return sorted(p for p in gdaten_dir.iterdir() if p.is_file() and pattern.match(p.name))


def parse_kfconf(path: Path) -> list[KfconfEntry]:
    entries: list[KfconfEntry] = []
    for line_no, line in enumerate(read_lines(path), start=1):
        if not line.startswith("ME"):
            continue
        parts = line.split()
        if len(parts) < 13:
            logger.warning("KFCONF %s line %d has %d fields", path.name, line_no, len(parts))
            continue
        entries.append(KfconfEntry(
            ecu_index=parts[1], address=parts[2], prio=parts[3], family=parts[4],
            pabd=parts[5], psgbd=parts[6], flash_type=parts[7], his_file=parts[8],
            dat_file=parts[9], data_prefix=parts[10], dir_file=parts[11], hwh_file=parts[12],
            line_no=line_no, source_file=path.name,
        ))
    return entries


def load_kfconf(gdaten_dir: Path) -> list[KfconfEntry]:
    entries: list[KfconfEntry] = []
    for path in find_kfconf_files(gdaten_dir):
        entries.extend(parse_kfconf(path))
    return entries


@dataclass
class InfoEntry:
    ecu_index: str
    address: str
    prio: str
    family: str
    description: str
    line_no: int = 0


@dataclass
class InfoFile:
    path: Path | None = None
    ecu_index_text: str = ""
    ecu_address_text: str = ""
    prio_default_text: str = ""
    entries: list[InfoEntry] = field(default_factory=list)


def find_info_file(gdaten_dir: Path, language: str) -> Path | None:
    suffix = {"eng": "ENG", "ger": "GER", "deu": "GER"}.get((language or "").lower(), language.upper() or "GER")
    return find_child_file(gdaten_dir, f"INFO.{suffix}")


def parse_info(path: Path) -> InfoFile:
    result = InfoFile(path=path)
    for line_no, line in enumerate(read_lines(path), start=1):
        if line.startswith("$ECUINDEXTEXT"):
            result.ecu_index_text = line[len("$ECUINDEXTEXT"):].strip()
        elif line.startswith("$ECUADDRTEXT"):
            result.ecu_address_text = line[len("$ECUADDRTEXT"):].strip()
        elif line.startswith("$PRIODEFAULTTEXT"):
            result.prio_default_text = line[len("$PRIODEFAULTTEXT"):].strip()
        elif line.startswith("$AA"):
            parts = line.split(None, 5)
            if len(parts) < 5:
                continue
            description = parts[5].strip() if len(parts) > 5 else ""
            if description == "-":
                description = ""
            result.entries.append(InfoEntry(
                ecu_index=parts[1], address=parts[2], prio=parts[3], family=parts[4],
                description=description, line_no=line_no,
            ))
    return result


@dataclass
class HwnrEntry:
    hw_nr: str
    at_hw_nr: str       # exchange part HW number
    ep_ts_nr: str
    family: str


def parse_hwnr(path: Path) -> list[HwnrEntry]:
    entries: list[HwnrEntry] = []
    for line in read_lines(path):
        if not line or line.startswith(";"):
            continue
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 4:
            continue
        entries.append(HwnrEntry(hw_nr=parts[0], at_hw_nr=parts[1], ep_ts_nr=parts[2], family=parts[3]))
    return entries


# ---------------------------------------------------------------------------
# ECU family logistics: DAT, HIS, HWH


@dataclass
class DatEntry:
    zb_nr: str          # assembly number (ZUSB)
    typ_nr: str
    hw_nr: str
    index: str          # HW index letter
    sw_nr: str          # e.g. "8509538DA"
    am: str
    pin: str
    s: str
    checksum: str
    line_no: int = 0

    @property
    def sw_number(self) -> str:
        return re.sub(r"[A-Za-z]+$", "", self.sw_nr)

    @property
    def sw_kind(self) -> str:
        """Two-letter suffix of the SW number: DA = data, PA = program, BA = NAAB."""
        match = re.search(r"([A-Za-z]+)$", self.sw_nr)
        return match.group(1).upper() if match else ""

    @property
    def has_data_file(self) -> bool:
        """SW-NR 0000000 means: program only, no data data set."""
        number = self.sw_number
        return bool(number) and set(number) != {"0"}

    def program_file_name(self) -> str:
        """Program data set: <HW-NR><index>.0PA"""
        return f"{self.hw_nr}{self.index}.0PA"

    def data_file_name(self, data_prefix: str) -> str:
        """Data data set: <prefix><SW-NR>.0DA (prefix letter from KFCONF)."""
        ext = f"0{self.sw_kind}" if self.sw_kind else "0DA"
        return f"{data_prefix}{self.sw_number}.{ext}"


@dataclass
class DatFile:
    path: Path
    created: str = ""
    family: str = ""
    header_lines: list[str] = field(default_factory=list)
    entries: list[DatEntry] = field(default_factory=list)


def parse_dat(path: Path) -> DatFile:
    result = DatFile(path=path)
    for line_no, line in enumerate(read_lines(path), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("$"):
            result.header_lines.append(stripped)
            continue
        if stripped.startswith(";"):
            match = re.search(r"vom\s+(.+)$", stripped)
            if match and not result.created:
                result.created = match.group(1).strip()
            match = re.match(r";SG-TYP:\s*(\S+)", stripped)
            if match:
                result.family = match.group(1)
            continue
        parts = [p.strip() for p in stripped.split(",")]
        if len(parts) < 8:
            continue
        tail = parts[7].split()
        result.entries.append(DatEntry(
            zb_nr=parts[0], typ_nr=parts[1], hw_nr=parts[2], index=parts[3], sw_nr=parts[4],
            am=parts[5], pin=parts[6], s=tail[0] if tail else "",
            checksum=tail[1] if len(tail) > 1 else "", line_no=line_no,
        ))
    return result


@dataclass
class HisEntry:
    zb_old: str
    zb_new: str
    release: str        # FREIKENNUNG
    code: str


@dataclass
class HisFile:
    path: Path
    created: str = ""
    entries: list[HisEntry] = field(default_factory=list)

    def successors(self) -> dict[str, str]:
        return {e.zb_old: e.zb_new for e in self.entries}

    def latest(self, zb_nr: str, max_steps: int = 200) -> list[str]:
        """Follow the history chain from zb_nr; returns [zb_nr, ..., latest]."""
        chain = [zb_nr]
        nxt = self.successors()
        seen = {zb_nr}
        while chain[-1] in nxt and len(chain) <= max_steps:
            new = nxt[chain[-1]]
            if new in seen:
                break
            seen.add(new)
            chain.append(new)
        return chain


def parse_his(path: Path) -> HisFile:
    result = HisFile(path=path)
    for line in read_lines(path):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith(";"):
            match = re.search(r"vom\s+(.+)$", stripped)
            if match and not result.created:
                result.created = match.group(1).strip()
            continue
        parts = [p.strip() for p in stripped.split(",")]
        if len(parts) < 2:
            continue
        result.entries.append(HisEntry(
            zb_old=parts[0], zb_new=parts[1],
            release=parts[2] if len(parts) > 2 else "",
            code=parts[3] if len(parts) > 3 else "",
        ))
    return result


@dataclass
class HwhItem:
    hw_nr: str
    index: str
    status: str


@dataclass
class HwhFile:
    path: Path
    created: str = ""
    groups: list[list[HwhItem]] = field(default_factory=list)

    def group_of(self, hw_nr: str) -> list[HwhItem]:
        for group in self.groups:
            if any(item.hw_nr == hw_nr for item in group):
                return group
        return []


def parse_hwh(path: Path) -> HwhFile:
    result = HwhFile(path=path)
    current: list[HwhItem] = []
    for line in read_lines(path):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith(";"):
            match = re.search(r"vom\s+(.+)$", stripped)
            if match and not result.created:
                result.created = match.group(1).strip()
            continue
        ends_group = stripped.endswith(";")
        for chunk in stripped.rstrip(";").split(","):
            match = re.match(r"\s*(\d+)([A-Za-z]?)\s+(\S+)", chunk)
            if match:
                current.append(HwhItem(hw_nr=match.group(1), index=match.group(2), status=match.group(3)))
        if ends_group and current:
            result.groups.append(current)
            current = []
    if current:
        result.groups.append(current)
    return result


# ---------------------------------------------------------------------------
# Flash data sets (*.0PA / *.0DA / *.0BA)

FLASH_EXTENSIONS = {".0pa": "program", ".0da": "data", ".0ba": "naab"}


@dataclass
class FlashFileHeader:
    path: Path
    kind: str
    fields: dict[str, str] = field(default_factory=dict)
    reference: str = ""

    def get(self, key: str) -> str:
        return self.fields.get(key, "")

    @property
    def system(self) -> str:
        return self.get("ZL_System")

    @property
    def project(self) -> str:
        return self.get("ZL_Projekt")

    @property
    def vehicle(self) -> str:
        """Human readable vehicle identification from K_F1..K_F4."""
        parts = [self.get(f"K_F{i}") for i in range(1, 5)]
        return " / ".join(p for p in parts if p)

    @property
    def usage(self) -> str:
        parts = [self.get("K_V1"), self.get("K_V2")]
        return " / ".join(p for p in parts if p)


def flash_kind(path: Path) -> str:
    return FLASH_EXTENSIONS.get(path.suffix.lower(), "")


def parse_flash_header(path: Path, max_bytes: int = 16384) -> FlashFileHeader:
    """Parse the ';;KEY: value' header of an exchange file; the Intel HEX body is skipped."""
    result = FlashFileHeader(path=path, kind=flash_kind(path))
    try:
        with open(path, "rb") as handle:
            raw = handle.read(max_bytes)
    except OSError:
        logger.exception("Failed to read flash file header: %s", path)
        return result
    for line in raw.decode(ENCODING, errors="replace").splitlines():
        if line.startswith(":"):
            break
        if line.startswith("$REFERENZ"):
            result.reference = line[len("$REFERENZ"):].strip()
            continue
        if not line.startswith(";;"):
            continue
        body = line[2:]
        match = re.match(r"([A-Za-z0-9_\-]+):?\s*(.*)$", body)
        if not match:
            continue
        key, value = match.group(1), match.group(2).strip()
        if key and key not in result.fields:
            result.fields[key] = value
    return result


def list_flash_files(folder: Path) -> list[Path]:
    if not folder.is_dir():
        return []
    return sorted(p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in FLASH_EXTENSIONS)


# ---------------------------------------------------------------------------
# SGDAT *.ipo (PABD / CABD)

PABD_MARKERS = {
    "SG_PROGRAMMIEREN", "FlashSchreiben", "FlashSchreibenEnde", "FLASH_PARAMETER_SETZEN",
    "LoescheFlash", "FlashStatusLesen", "SG_AIF_SCHREIBEN",
}
CABD_MARKERS = {"SG_CODIEREN", "CODIERDATEN_LESEN", "C_C_AUFTRAG", "C_C_LESEN", "CODIERINDEX_LESEN"}
IPO_KIND_PABD = "PABD"
IPO_KIND_CABD = "CABD"
IPO_KIND_UNKNOWN = "?"


@dataclass
class IpoInfo:
    path: Path
    kind: str = IPO_KIND_UNKNOWN
    jobs: list[str] = field(default_factory=list)
    author: str = ""
    source_name: str = ""
    size: int = 0
    identifiers: set[str] = field(default_factory=set)

    @property
    def name(self) -> str:
        return self.path.name


_IPO_STRING_RE = re.compile(rb"[\x20-\x7e]{4,}")
_IPO_JOB_RE = re.compile(r"^JOB\[\d+\]$")
_IPO_IDENT_RE = re.compile(r"^[A-Z][A-Z0-9_]{3,}$")


def classify_ipo(path: Path) -> IpoInfo:
    """Heuristic analysis of a compiled CABD/PABD (*.ipo) by its embedded strings."""
    info = IpoInfo(path=path)
    try:
        data = path.read_bytes()
    except OSError:
        logger.exception("Failed to read IPO file: %s", path)
        return info
    info.size = len(data)
    strings = [m.group().decode("ascii", errors="ignore") for m in _IPO_STRING_RE.finditer(data)]
    string_set = set(strings)

    if string_set & PABD_MARKERS:
        info.kind = IPO_KIND_PABD
    elif string_set & CABD_MARKERS:
        info.kind = IPO_KIND_CABD

    jobs: list[str] = []
    for idx, value in enumerate(strings):
        if _IPO_JOB_RE.match(value) and idx + 1 < len(strings):
            candidate = strings[idx + 1]
            if _IPO_IDENT_RE.match(candidate) and not _IPO_JOB_RE.match(candidate) and candidate not in jobs:
                jobs.append(candidate)
    info.jobs = jobs
    info.identifiers = {value for value in string_set if re.fullmatch(r"[0-9A-Za-z_]{4,}", value)}

    for value in strings:
        if value.upper().endswith(".IPS") and not info.source_name:
            info.source_name = value
        if not info.author and re.search(r"\bBMW\b", value) and len(value) < 80:
            info.author = value.strip()
    return info


def ipo_family_stem(file_name: str) -> str:
    """'07dde71.ipo' -> 'DDE71' (version prefix digits stripped)."""
    stem = Path(file_name).stem.upper()
    return re.sub(r"^\d+", "", stem)


def ipo_version(file_name: str) -> int:
    match = re.match(r"^(\d+)", Path(file_name).stem)
    return int(match.group(1)) if match else -1


# ---------------------------------------------------------------------------
# Logs and error texts

_LOG_LINE_RE = re.compile(r"^\[(?P<time>[\d:.]+)\]\s+\[(?P<date>[\d-]+)\]\s+\[(?P<app>[^\]]*)\]\s?(?P<rest>.*)$")
_LOG_HEAD_RE = re.compile(r"^\s*(?P<code>\d+)\s+(?P<category>\S+)\s+(?P<source>\S+)\s+(?P<function>\S+)\s+(?P<line>\d+)\s*$")


@dataclass
class LogEntry:
    timestamp: datetime | None
    app: str
    code: int
    category: str
    source: str
    function: str
    source_line: int
    message: str = ""


def parse_error_log(path: Path) -> list[LogEntry]:
    """Parse WinKFP ERROR_<IF>_<unit>.LOG: a header line followed by a message line."""
    entries: list[LogEntry] = []
    current: LogEntry | None = None
    for line in read_lines(path):
        match = _LOG_LINE_RE.match(line)
        if not match:
            continue
        rest = match.group("rest")
        head = _LOG_HEAD_RE.match(rest)
        if head:
            try:
                stamp = datetime.strptime(f"{match.group('date')} {match.group('time')}", "%Y-%m-%d %H:%M:%S.%f")
            except ValueError:
                stamp = None
            current = LogEntry(
                timestamp=stamp, app=match.group("app"), code=int(head.group("code")),
                category=head.group("category"), source=head.group("source"),
                function=head.group("function"), source_line=int(head.group("line")),
            )
            entries.append(current)
        elif current is not None and not current.message:
            current.message = rest.strip()
    return entries


def find_error_logs(paths: WinkfpPaths) -> list[Path]:
    logs: list[Path] = []
    for folder in (paths.bin_dir, paths.work_dir, paths.trace_dir):
        if not folder.is_dir():
            continue
        for p in folder.iterdir():
            if p.is_file() and p.suffix.lower() == ".log" and p.name.lower().startswith("error"):
                logs.append(p)
    return sorted(logs, key=lambda p: p.stat().st_mtime, reverse=True)


def find_out_files(paths: WinkfpPaths) -> list[Path]:
    """Result files of special functions (IDENT_*, AIF_*, REF_*, INNENTMP_*, CABDPAR_*)."""
    files: list[Path] = []
    for folder in (paths.bin_dir, paths.work_dir):
        if folder.is_dir():
            files.extend(p for p in folder.iterdir() if p.is_file() and p.suffix.lower() == ".out")
    return sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)


def parse_error_texts(paths: WinkfpPaths, language: str = "eng") -> dict[int, str]:
    """COAPI (Coapierr.<lang>) and EDIABAS (Edierror.<lang>) error texts."""
    suffix = "ger" if (language or "").lower() in {"ger", "deu"} else "eng"
    texts: dict[int, str] = {}
    for base in ("Edierror", "Coapierr"):
        path = find_child_file(paths.cfgdat_dir, f"{base}.{suffix}")
        if not path:
            continue
        for line in read_lines(path):
            match = re.match(r"^\s*(\d+)\s*=\s*(.*)$", line)
            if match:
                texts[int(match.group(1))] = match.group(2).strip()
    return texts


# ---------------------------------------------------------------------------
# Inventory


@dataclass
class FamilyFolder:
    name: str
    path: Path
    dat_file: Path | None = None
    his_file: Path | None = None
    hwh_file: Path | None = None
    program_files: int = 0
    data_files: int = 0
    naab_files: int = 0


def list_family_folders(data_dir: Path) -> list[FamilyFolder]:
    families: list[FamilyFolder] = []
    if not data_dir.is_dir():
        return families
    for child in sorted(data_dir.iterdir(), key=lambda p: p.name.upper()):
        if not child.is_dir() or child.name.upper() in NON_FAMILY_DIRS:
            continue
        files = list_files_ci(child)
        name = child.name.upper()
        family = FamilyFolder(
            name=name, path=child,
            dat_file=files.get(f"{name.lower()}.dat"),
            his_file=files.get(f"{name.lower()}.his"),
            hwh_file=files.get(f"{name.lower()}.hwh"),
        )
        for file_name in files:
            ext = os.path.splitext(file_name)[1]
            if ext == ".0pa":
                family.program_files += 1
            elif ext == ".0da":
                family.data_files += 1
            elif ext == ".0ba":
                family.naab_files += 1
        families.append(family)
    return families


@dataclass
class BackupDir:
    path: Path
    base: str
    created: datetime | None


def find_backup_dirs(folder: Path) -> list[BackupDir]:
    """Find update backups like SGDAT_20260509_002519 next to the original folders."""
    result: list[BackupDir] = []
    if not folder.is_dir():
        return result
    for child in folder.iterdir():
        if not child.is_dir():
            continue
        match = BACKUP_DIR_RE.match(child.name)
        if not match:
            continue
        try:
            created = datetime.strptime(match.group("date") + match.group("time"), "%Y%m%d%H%M%S")
        except ValueError:
            created = None
        result.append(BackupDir(path=child, base=match.group("base"), created=created))
    return sorted(result, key=lambda b: (b.base.upper(), b.created or datetime.min))


@dataclass
class InstallSummary:
    paths: WinkfpPaths
    info: WinkfpInstallInfo
    kfconf_entries: int = 0
    info_file: str = ""
    info_entries: int = 0
    families: int = 0
    ipo_files: int = 0
    prg_files: int = 0
    backups: list[BackupDir] = field(default_factory=list)


def build_install_summary(paths: WinkfpPaths) -> InstallSummary:
    """Quick overview: counts only, no deep parsing of data sets."""
    info = read_install_info(paths)
    summary = InstallSummary(paths=paths, info=info)
    summary.kfconf_entries = len(load_kfconf(paths.gdaten_dir))
    info_path = find_info_file(paths.gdaten_dir, info.language or "ger")
    if info_path:
        summary.info_file = info_path.name
        summary.info_entries = len(parse_info(info_path).entries)
    summary.families = len(list_family_folders(paths.data_dir))
    summary.ipo_files = sum(1 for name in list_files_ci(paths.sgdat_dir) if name.endswith(".ipo"))
    summary.prg_files = sum(1 for name in list_files_ci(paths.ecu_dir) if name.endswith(".prg"))
    summary.backups = find_backup_dirs(paths.nfs_root)
    return summary


if __name__ == "__main__":
    import sys

    root = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_NFS_ROOT
    p = WinkfpPaths(nfs_root=root)
    s = build_install_summary(p)
    print(f"WinKFP: {s.info.version_line} lang={s.info.language} cabd={s.info.cabd_format}")
    print(f"KFCONF entries: {s.kfconf_entries}, INFO: {s.info_file or '-'} ({s.info_entries})")
    print(f"Families: {s.families}, IPO: {s.ipo_files}, PRG: {s.prg_files}")
    for b in s.backups:
        print(f"Backup: {b.path.name} ({b.base}, {b.created})")
