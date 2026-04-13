from __future__ import annotations

from pathlib import Path
import re
import logging


logger = logging.getLogger("bimmerdaten.daten_parser")


def parse_swt_dat(filepath: str) -> dict[int, str]:
    """Parse SWTFSW??.dat or SWTPSW??.dat binary file.
    Returns dict: {key_id: keyword}"""
    data = Path(filepath).read_bytes()
    result: dict[int, str] = {}
    pos = 0
    while pos < len(data) - 6:
        if data[pos + 2] == 0x01 and data[pos + 3] == 0x00:
            key_id = int.from_bytes(data[pos + 4 : pos + 6], "little")
            str_start = pos + 6
            if str_start < len(data) and (data[str_start] >= 0x30):
                try:
                    str_end = data.index(0x00, str_start)
                    if str_end - str_start < 40:
                        keyword = data[str_start:str_end].decode("latin-1")
                        if all(c.isalnum() or c in "_/.-&%[]" for c in keyword):
                            result[key_id] = keyword
                    pos = str_end + 1
                    continue
                except Exception:
                    logger.exception("Failed parsing SWT entry at offset %s in %s", pos, filepath)
                    pass
        pos += 1
    return result


def parse_cxx(filepath: str, fsw_dict: dict, psw_dict: dict) -> list[dict]:
    """Parse binary .Cxx module description file.
    Returns list of options:
    [{'name': str, 'fsw_id': int, 'wortadr': int,
      'byteadr': int, 'maska': int,
      'params': [{'name': str, 'data': int}], 'group': str}]
    Filter out options with no params."""
    data = Path(filepath).read_bytes()
    options: list[dict] = []
    pos = 0
    current_group = ""

    def _looks_like_group_name(value: str) -> bool:
        return len(value) > 2 and all(32 <= ord(char) <= 126 for char in value)

    while pos < len(data) - 20:
        if data[pos + 2] == 0x06 and data[pos + 3] == 0x00:
            try:
                str_start = pos + 15
                str_end = data.index(0x00, str_start)
                group_name = data[str_start:str_end].decode("latin-1")
                if _looks_like_group_name(group_name):
                    current_group = group_name
            except Exception:
                logger.exception("Failed parsing CXX group name at offset %s in %s", pos, filepath)
                pass
        elif data[pos + 2] == 0x12 and data[pos + 3] == 0x00:
            try:
                p = pos + 4
                block_count = data[p]
                p += 1
                p += block_count * 4
                wortadr = int.from_bytes(data[p : p + 4], "little")
                p += 4
                byteadr = int.from_bytes(data[p : p + 2], "little")
                p += 2
                fsw_id = int.from_bytes(data[p : p + 2], "little")
                p += 2
                idx_count = data[p]
                p += 1
                p += idx_count
                p += 1  # maska present
                p += 1  # padding
                maska = data[p]
                p += 1
                ein_count = data[p]
                p += 1
                p += ein_count
                ind_count = data[p]
                p += 1
                p += ind_count
                fsw_name = fsw_dict.get(fsw_id, f"FSW_{fsw_id:04X}")
                params = []
                while p < len(data) - 6:
                    if data[p + 2] == 0x10 and data[p + 3] == 0x00:
                        p += 4
                        psw_id = int.from_bytes(data[p : p + 2], "little")
                        p += 2
                        datum_present = data[p]
                        p += 1
                        if datum_present:
                            p += 1
                            datum = data[p]
                            p += 1
                        else:
                            datum = 0
                        psw_name = psw_dict.get(psw_id, f"PSW_{psw_id:04X}")
                        params.append({"name": psw_name, "data": datum})
                    else:
                        break
                if params:
                    options.append(
                        {
                            "name": fsw_name,
                            "fsw_id": fsw_id,
                            "wortadr": wortadr,
                            "byteadr": byteadr,
                            "maska": maska,
                            "params": params,
                            "group": current_group,
                        }
                    )
            except Exception:
                logger.exception("Failed parsing CXX option block at offset %s in %s", pos, filepath)
                pass
        pos += 1
    return options


def _find_chassis_folder(daten_folder: str, chassis: str) -> Path | None:
    root = Path(daten_folder)
    if not root.exists():
        return None

    direct = root / chassis
    if direct.exists() and direct.is_dir():
        return direct

    target = (chassis or "").strip().casefold()
    for entry in root.iterdir():
        if entry.is_dir() and entry.name.casefold() == target:
            return entry
    return None


def _find_first_file(folder: Path, prefix: str) -> Path | None:
    for entry in sorted(folder.iterdir(), key=lambda p: p.name.upper()):
        upper = entry.name.upper()
        if not entry.is_file():
            continue
        if not upper.endswith(".DAT"):
            continue
        if upper.startswith(prefix.upper()):
            return entry
    return None


def _list_cxx_files(folder: Path) -> list[Path]:
    pattern = re.compile(r"^.+\.C\d\d$", re.IGNORECASE)
    result: list[Path] = []
    for entry in folder.iterdir():
        if entry.is_file() and pattern.match(entry.name):
            result.append(entry)
    return sorted(result, key=lambda p: p.name.upper())


def find_swt_files(daten_folder: str, chassis: str) -> tuple[str | None, str | None]:
    """Find SWTFSW and SWTPSW files for given chassis.
    Look in chassis subfolder first, then parent DATEN folder.
    Returns (fsw_path, psw_path) or (None, None)"""
    root = Path(daten_folder)
    if not root.exists():
        return (None, None)

    candidates: list[Path] = []
    chassis_folder = _find_chassis_folder(daten_folder, chassis)
    if chassis_folder:
        candidates.append(chassis_folder)
    candidates.append(root)

    for folder in candidates:
        fsw = _find_first_file(folder, "SWTFSW")
        psw = _find_first_file(folder, "SWTPSW")
        if fsw and psw:
            return (str(fsw), str(psw))

    return (None, None)


def load_module(daten_folder: str, chassis: str, cxx_filename: str) -> list[dict]:
    """Load a module: find SWT files, parse CXX, return options list."""
    fsw_path, psw_path = find_swt_files(daten_folder, chassis)
    if not fsw_path or not psw_path:
        return []

    fsw_dict = parse_swt_dat(fsw_path)
    psw_dict = parse_swt_dat(psw_path)

    root = Path(daten_folder)
    chassis_folder = _find_chassis_folder(daten_folder, chassis)
    cxx_path: Path | None = None

    if chassis_folder:
        candidate = chassis_folder / cxx_filename
        if candidate.exists():
            cxx_path = candidate
        else:
            for entry in _list_cxx_files(chassis_folder):
                if entry.name.casefold() == cxx_filename.casefold():
                    cxx_path = entry
                    break

    if cxx_path is None:
        candidate = root / cxx_filename
        if candidate.exists():
            cxx_path = candidate

    if cxx_path is None or not cxx_path.exists():
        return []

    return parse_cxx(str(cxx_path), fsw_dict, psw_dict)


def detect_module_from_trc(
    trc_options: set[str],
    daten_folder: str,
    chassis: str,
) -> list[tuple[str, float]]:
    """Compare TRC options against all .Cxx files for chassis.
    Returns list of (cxx_filename, match_percentage) sorted descending.
    Only return candidates with match > 0.3 (30%)"""
    if not trc_options:
        return []

    chassis_folder = _find_chassis_folder(daten_folder, chassis)
    if not chassis_folder:
        return []

    trc_upper = {name.strip().upper() for name in trc_options if name.strip()}
    if not trc_upper:
        return []

    candidates: list[tuple[str, float]] = []
    for cxx_file in _list_cxx_files(chassis_folder):
        options = load_module(daten_folder, chassis, cxx_file.name)
        if not options:
            continue

        module_names = {
            str(option.get("name", "")).strip().upper()
            for option in options
            if str(option.get("name", "")).strip()
        }
        if not module_names:
            continue

        matched = len(module_names.intersection(trc_upper))
        ratio = matched / len(trc_upper)
        if ratio > 0.3:
            candidates.append((cxx_file.name, ratio))

    candidates.sort(key=lambda item: item[1], reverse=True)
    return candidates


def parse_trc(filepath: str) -> dict[str, str]:
    """Parse FSW_PSW.TRC file.
    Returns dict: {option_name: current_value}
    Format: OPTION_NAME\n\t\tvalue\n"""
    path = Path(filepath)
    if not path.exists():
        return {}

    text = ""
    for encoding in ("utf-8-sig", "cp1250", "latin1", "mbcs"):
        try:
            text = path.read_text(encoding=encoding)
            break
        except Exception:
            continue

    if not text:
        return {}

    lines = text.splitlines()
    result: dict[str, str] = {}
    idx = 0
    while idx < len(lines):
        option = lines[idx].strip()
        if option and idx + 1 < len(lines):
            value_line = lines[idx + 1]
            if value_line.startswith(("\t", " ")):
                result[option] = value_line.strip()
                idx += 2
                continue
        idx += 1

    return result
