"""
winkfp_assistant.py
"What to flash" assistant: from an ECU's HW number or ZB number to the matching
ZB numbers, the newest ZB and the exact values for WinKFP Expert / Comfort mode.

Relations used (all read from the installed WinKFP data):
- <family>.HWH  groups of mutually compatible hardware numbers
- <family>.DAT  ZB number -> program HW (0PA file), SW number (0DA file)
- <family>.HIS  ZB history: old ZB -> new ZB (also for ZB numbers no longer in DAT)
- gdaten\\HWNR.DA2 HW number -> family (older global list, used as a fallback)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from winkfp_families import (
    STATUS_BACKUP_ONLY,
    FamilyRecord,
    HeaderCache,
    ZbRow,
    load_zb_rows,
)
from winkfp_parser import HisFile, HwhFile, WinkfpPaths, parse_his, parse_hwh, parse_hwnr

_NUMBER_RE = re.compile(r"^\s*(\d{7})\s*([A-Za-z]?)\s*$")


@dataclass
class FamilyData:
    record: FamilyRecord
    rows: list[ZbRow]
    his: HisFile | None
    hwh: HwhFile | None

    @property
    def successors(self) -> dict[str, str]:
        return self.his.successors() if self.his else {}

    def is_latest(self, zb_nr: str) -> bool:
        return zb_nr not in self.successors

    def chain(self, zb_nr: str) -> list[str]:
        return self.his.latest(zb_nr) if self.his else [zb_nr]

    def compatible_hw(self, hw_nr: str) -> set[str]:
        group = self.hwh.group_of(hw_nr) if self.hwh else []
        hws = {item.hw_nr for item in group}
        hws.add(hw_nr)
        return hws


@dataclass
class Candidate:
    family: FamilyData
    row: ZbRow
    latest: bool
    exact_hw: bool          # program HW equals the entered HW (not only the same HWH group)

    @property
    def record(self) -> FamilyRecord:
        return self.family.record


@dataclass
class AssistantResult:
    query: str
    kind: str                               # "hw", "zb" or "invalid"
    number: str = ""
    families: list[str] = field(default_factory=list)
    hwnr_families: list[str] = field(default_factory=list)  # from HWNR.DA2 only
    candidates: list[Candidate] = field(default_factory=list)
    current_zb: str = ""
    current_chain: list[str] = field(default_factory=list)
    recommended: Candidate | None = None
    messages: list[str] = field(default_factory=list)


class FlashAssistant:
    def __init__(self, paths: WinkfpPaths, records: list[FamilyRecord], cache: HeaderCache):
        self.paths = paths
        self.cache = cache
        self.families: list[FamilyData] = []
        for record in records:
            if record.folder is None or record.folder.dat_file is None:
                continue
            folder = record.folder
            self.families.append(FamilyData(
                record=record,
                rows=load_zb_rows(record, cache),
                his=parse_his(folder.his_file) if folder.his_file else None,
                hwh=parse_hwh(folder.hwh_file) if folder.hwh_file else None,
            ))
        self.hwnr: dict[str, set[str]] = {}
        hwnr_path = paths.gdaten_dir / "HWNR.DA2"
        if hwnr_path.is_file():
            for entry in parse_hwnr(hwnr_path):
                self.hwnr.setdefault(entry.hw_nr, set()).add(entry.family.strip().upper())

    # --- queries ---------------------------------------------------------------

    def search(self, query: str, current_zb: str = "") -> AssistantResult:
        match = _NUMBER_RE.match(query or "")
        result = AssistantResult(query=query, kind="invalid")
        if not match:
            result.messages.append("Enter a 7-digit HW number (e.g. 7806897 or 7806897A) or ZB number.")
            return result
        number = match.group(1)
        result.number = number

        zb_hits = self._search_zb(number)
        hw_hits = self._search_hw(number)
        if zb_hits and not hw_hits:
            result.kind = "zb"
            result.candidates = zb_hits
        else:
            result.kind = "hw"
            result.candidates = hw_hits
            if zb_hits:
                result.messages.append(f"{number} is also a ZB number — showing it as HW number.")
        result.families = sorted({c.record.name for c in result.candidates})
        result.hwnr_families = sorted(self.hwnr.get(number, set()))

        current_zb = (current_zb or "").strip()
        if result.kind == "zb" and not current_zb:
            current_zb = number
        if current_zb:
            result.current_zb = current_zb
            self._apply_current_zb(result, current_zb)
        if result.recommended is None:
            self._recommend_without_current(result)

        if not result.candidates:
            if result.hwnr_families:
                names = ", ".join(result.hwnr_families)
                result.messages.append(
                    f"HWNR.DA2 knows {number} as family {names}, but no flash data for it is installed."
                )
            else:
                result.messages.append(
                    f"{number} was not found in the installed flash data (DAT / HWH / HIS) or in HWNR.DA2."
                )
        result.candidates.sort(key=lambda c: (c.record.name, not c.latest, not c.exact_hw, c.row.entry.zb_nr))
        return result

    def _search_hw(self, hw_nr: str) -> list[Candidate]:
        candidates: list[Candidate] = []
        for family in self.families:
            compatible = family.compatible_hw(hw_nr)
            for row in family.rows:
                if row.entry.hw_nr in compatible:
                    candidates.append(Candidate(
                        family=family, row=row,
                        latest=family.is_latest(row.entry.zb_nr),
                        exact_hw=row.entry.hw_nr == hw_nr,
                    ))
        return candidates

    def _search_zb(self, zb_nr: str) -> list[Candidate]:
        candidates: list[Candidate] = []
        for family in self.families:
            in_history = zb_nr in family.successors
            for row in family.rows:
                if row.entry.zb_nr == zb_nr:
                    candidates.append(Candidate(family, row, family.is_latest(zb_nr), True))
            if in_history and not any(c.family is family for c in candidates):
                # ZB only known from the history: show where it leads.
                latest = family.chain(zb_nr)[-1]
                for row in family.rows:
                    if row.entry.zb_nr == latest:
                        candidates.append(Candidate(family, row, True, False))
        return candidates

    def _apply_current_zb(self, result: AssistantResult, current_zb: str) -> None:
        for family in self.families:
            known = current_zb in family.successors or any(r.entry.zb_nr == current_zb for r in family.rows)
            if not known:
                continue
            chain = family.chain(current_zb)
            result.current_chain = chain
            latest = chain[-1]
            target = next((c for c in result.candidates if c.family is family and c.row.entry.zb_nr == latest), None)
            if target is None:
                row = next((r for r in family.rows if r.entry.zb_nr == latest), None)
                if row is not None:
                    target = Candidate(family, row, True, False)
                    result.candidates.append(target)
            if target is not None:
                result.recommended = target
                if len(chain) > 1:
                    result.messages.append(
                        f"ZB history: {' → '.join(chain)} — the newest ZB for this ECU is {latest}."
                    )
                else:
                    result.messages.append(f"ZB {current_zb} is already the newest in the history.")
                if result.kind == "hw" and target.row.entry.hw_nr not in family.compatible_hw(result.number):
                    result.messages.append(
                        f"⚠️ The newest ZB {latest} is for HW {target.row.entry.hw_nr}, which is not in the same HW group "
                        f"as {result.number}. WinKFP may need a boot sector update (BSU) — use Comfort mode "
                        "'Update ZUSB', which handles this."
                    )
            return
        result.messages.append(f"ZB {current_zb} was not found in any installed DAT or HIS file.")

    def _recommend_without_current(self, result: AssistantResult) -> None:
        latest = [c for c in result.candidates if c.latest]
        if not latest:
            return
        variants = {c.row.description for c in latest}
        if len(latest) == 1 or len(variants) == 1:
            result.recommended = sorted(latest, key=lambda c: (not c.exact_hw, c.row.entry.zb_nr))[-1]
        else:
            result.messages.append(
                f"{len(latest)} newest ZB numbers fit this hardware — they differ by vehicle / gearbox / power. "
                "Pick the line matching your car, or enter the current ZB (from 'Read UIF') to get an exact answer."
            )


# ---------------------------------------------------------------------------
# Output for WinKFP


@dataclass
class ExpertValues:
    family: str
    zb_nr: str
    pabd: str
    psgbd: str
    address: str
    program_file: str
    data_file: str
    warnings: list[str] = field(default_factory=list)

    def as_text(self) -> str:
        lines = [
            f"Family:        {self.family}",
            f"ZB number:     {self.zb_nr}",
            f"PABD:          {self.pabd}",
            f"P-SGBD:        {self.psgbd}",
            f"ECU address:   {self.address}",
            f"Program file:  {self.program_file}",
            f"Data file:     {self.data_file or '-'}",
        ]
        return "\n".join(lines)


def expert_values(candidate: Candidate) -> ExpertValues:
    record = candidate.record
    entry = record.kfconf
    row = candidate.row
    warnings: list[str] = []
    if record.status == STATUS_BACKUP_ONLY:
        warnings.append(
            f"Family {record.name} is only in the backup folder {record.backup_name} — restore it in "
            "📦 Families first, otherwise WinKFP cannot find the files."
        )
    if entry is None:
        warnings.append("No KFCONF entry for this family — PABD / P-SGBD have to be chosen manually.")
    else:
        if not record.pabd_ok:
            warnings.append(f"PABD {entry.pabd} is missing in SGDAT — run the 🩺 Health check.")
        if not record.psgbd_ok:
            warnings.append(f"P-SGBD {entry.psgbd} is missing in EDIABAS\\Ecu.")
    if not row.program_exists:
        warnings.append(f"Program file {row.program_file} is missing.")
    if not row.data_exists:
        warnings.append(f"Data file {row.data_file} is missing.")
    if not candidate.latest:
        newer = candidate.family.chain(row.entry.zb_nr)[-1]
        warnings.append(f"A newer ZB exists: {newer}.")
    return ExpertValues(
        family=record.name,
        zb_nr=row.entry.zb_nr,
        pabd=entry.pabd if entry else "",
        psgbd=entry.psgbd if entry else "",
        address=entry.address if entry else record.address,
        program_file=row.program_file,
        data_file=row.data_file,
        warnings=warnings,
    )
