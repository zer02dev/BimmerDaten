"""
winkfp_errors.py
Explanations for WinKFP / COAPI / EDIABAS error codes and grouping of log entries
into error events.

Tips are based on the "Description and Elimination of Frequently Occurring Errors"
chapter of the WinKFPT online help, plus findings from real installations.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime

from winkfp_parser import LogEntry


@dataclass(frozen=True)
class ErrorTip:
    title: str
    cause: str
    fix: str


# COAPI error code -> tip (generic, independent of the concrete log entry).
ERROR_TIPS: dict[int, ErrorTip] = {
    1000: ErrorTip(
        "General COAPI error",
        "Usually reported together with a more specific code (e.g. 1065 — PABD missing).",
        "Look at the other entries of the same event.",
    ),
    1020: ErrorTip(
        "File could not be opened",
        "A logistics file is missing: at start-up a file in DATA\\gdaten (e.g. INFO.ENG), "
        "on [Program] in Comfort mode the family HWH or HIS file.",
        "The file name is shown in the message. Run the 🩺 Health check — missing INFO.<lang> "
        "can be fixed automatically; family files come from the SP-Daten package.",
    ),
    1040: ErrorTip(
        "Error in file processing",
        "A logistics or flash file is faulty. Reported together with 4204/4206/4209/4211/4220/4221.",
        "See the other entries of the event for the file name and line.",
    ),
    1060: ErrorTip(
        "Coding sequence (CABD/PABD) error when starting programming",
        "Wrong HW interface selected, interface not installed / not connected, or ECU not connected.",
        "Check Communication → HW interface in WinKFP, the cable and ignition.",
    ),
    1063: ErrorTip(
        "CABD parameter error — the PABD does not know this job",
        "WinKFP called a job (e.g. SET_ECU_ADDRESS, GET_DIAG_PROT, SG_AIF_LESEN) that the selected "
        "PABD does not contain. Typical cause: a coding file (CABD, A_*.ipo) was selected as PABD.",
        "Select a flash PABD (🔧 in the 🗂 SGDAT tab) for this ECU. Coding files are for NCS Expert only.",
    ),
    1065: ErrorTip(
        "PABD not found or faulty",
        "The PABD from KFCONF / the configuration does not exist in SGDAT.",
        "Run the 🩺 Health check — wrong PABD names in KFCONF can be fixed automatically. "
        "Otherwise copy the PABD from the SP-Daten package.",
    ),
    2000: ErrorTip(
        "SGBD not found",
        "The P-SGBD from the configuration does not exist in EDIABAS\\Ecu.",
        "Copy the P-SGBD (*.prg) from the SP-Daten package to EDIABAS\\Ecu.",
    ),
    2020: ErrorTip(
        "No communication with the ECU",
        "Wrong ECU address, ECU not connected, or communication disrupted.",
        "Check the ECU address (integration position), ignition, battery voltage, cable and interface.",
    ),
    2021: ErrorTip(
        "No communication with the ECU / interface",
        "ECU or interface not connected, or interface not fully installed.",
        "Check the cable and the interface; test it with Tool32 / INPA.",
    ),
    2064: ErrorTip(
        "Delete error in coding data",
        "The previous programming session was not completed.",
        "Flash the program data set again in Expert mode (PABD, P-SGBD, program file → Prog. Program).",
    ),
    3000: ErrorTip(
        "ZB number not found in the logistics",
        "No <family>.DAT contains the entered ZB number.",
        "Check the ZB number or install the data set of the ECU family it belongs to.",
    ),
    4204: ErrorTip(
        "File to be flashed does not exist",
        "A 0PA/0DA file referenced in <family>.DAT is missing in DATA\\<family>.",
        "The file name is in the message. Install the complete data set (see 🩺 Health).",
    ),
    4206: ErrorTip(
        "Faulty logistics file",
        "DAT, HWH or HIS of the family (or a gdaten file) contains an error; the message names file and line.",
        "Replace the file with an intact copy from the SP-Daten package.",
    ),
    4209: ErrorTip(
        "Faulty logistics / flash file",
        "Reported together with 4206/4211 or 4220/4221.",
        "See the other entries of the event.",
    ),
    4211: ErrorTip(
        "Faulty logistics file",
        "A logistics file (DAT, HWH, HIS, gdaten) cannot be converted.",
        "Replace the file with an intact copy from the SP-Daten package.",
    ),
    4220: ErrorTip(
        "Faulty flash file",
        "The 0PA/0DA file is damaged.",
        "Replace the file with an intact copy from the SP-Daten package.",
    ),
    4221: ErrorTip(
        "Faulty flash file",
        "The 0PA/0DA file is damaged; the message names file and line.",
        "Replace the file with an intact copy from the SP-Daten package.",
    ),
}

# EDIABAS interface handler errors (IFH-xxxx) that appear inside COAPI 2000 messages.
IFH_TIPS: dict[str, ErrorTip] = {
    "0018": ErrorTip(
        "Interface could not be initialised (IFH-0018)",
        "EDIABAS could not open the diagnostic interface (e.g. STD:OBD): no cable connected, cable driver / "
        "COM port not set up, or another program is using the interface. Nothing was sent to the ECU.",
        "Connect the cable to the PC and the car (ignition on), check the COM port of the K+DCAN cable "
        "(usually COM1, latency 1 ms) and close INPA / Tool32 / NCS Expert. Test the connection in INPA first.",
    ),
    "0009": ErrorTip(
        "No response from the ECU (IFH-0009)",
        "The interface works, but the ECU does not answer: ignition off, wrong ECU address, or the ECU is not "
        "on this bus.",
        "Switch the ignition on, check the ECU address (integration position) and the battery voltage.",
    ),
    "0003": ErrorTip(
        "Data transmission to the interface disturbed (IFH-0003)",
        "Unstable connection between PC and cable.",
        "Use a short USB cable, set the COM port latency to 1 ms, connect a battery charger.",
    ),
    "0010": ErrorTip(
        "Data transmission to the ECU disturbed (IFH-0010)",
        "Unstable connection between cable and ECU.",
        "Check the OBD plug and battery voltage; connect a battery charger during flashing.",
    ),
}

# Interpreted errors (FciConfig.csv) start at 900000.
INTERPRETED_TIP = ErrorTip(
    "Interpreted error (summary)",
    "WinKFP's own summary of the previous entries of this event.",
    "Use the tip of the first entry of the event.",
)


def tip_for(entry: LogEntry) -> ErrorTip | None:
    """Tip for one log entry, refined with the context of the entry where possible."""
    message = entry.message.lower()
    if entry.code == 1020 and "info." in message:
        return ErrorTip(
            "INFO.<language> file missing",
            f"WinKFP runs with the language set in WINKFPT.INI and looks for {entry.message_arg or 'INFO.<lang>'} "
            "in DATA\\gdaten. Without it Comfort mode shows no integration positions.",
            "Run the 🩺 Health check — it creates the file from INFO.GER (fix available).",
        )
    if entry.code == 1063 and entry.source.upper().startswith("A_"):
        return ErrorTip(
            "A coding file (CABD) was used as PABD",
            f"{entry.source} is an NCS Expert coding sequence; it has no flash jobs, so WinKFP's call of "
            f"{entry.message_arg or 'a flash job'} fails. Nothing was sent to the ECU.",
            "In Expert mode select a flash PABD (🔧 in the 🗂 SGDAT tab) for this ECU. "
            "If there is none, the flash data for this ECU is not installed.",
        )
    ifh = re.search(r"IFH-(\d{4})", entry.message)
    if ifh:
        tip = IFH_TIPS.get(ifh.group(1))
        if tip is not None:
            return tip
        return ErrorTip(
            f"Interface error (IFH-{ifh.group(1)})",
            "EDIABAS could not talk to the diagnostic interface or the ECU.",
            "Check the cable, interface driver / COM port, ignition and battery voltage; test with Tool32 or INPA.",
        )
    if entry.code >= 900000:
        return INTERPRETED_TIP
    return ERROR_TIPS.get(entry.code)


@dataclass
class LogEvent:
    """One error event: the entries between two ==== separators."""

    entries: list[LogEntry]
    count: int = 1                      # number of identical events (when grouped)
    last_timestamp: datetime | None = None

    @property
    def primary(self) -> LogEntry:
        return self.entries[0]

    @property
    def timestamp(self) -> datetime | None:
        return self.primary.timestamp

    @property
    def codes(self) -> list[int]:
        seen: list[int] = []
        for entry in self.entries:
            if entry.code not in seen:
                seen.append(entry.code)
        return seen

    @property
    def where(self) -> str:
        """PABD/CABD name or source module of the first entry."""
        return self.primary.source

    def signature(self) -> tuple:
        return tuple((e.code, e.source, e.function, e.message) for e in self.entries)

    @property
    def tip(self) -> ErrorTip | None:
        for entry in self.entries:
            tip = tip_for(entry)
            if tip is not None and tip is not INTERPRETED_TIP:
                return tip
        return tip_for(self.primary)


def group_events(entries: list[LogEntry]) -> list[LogEvent]:
    events: list[LogEvent] = []
    current_block = None
    for entry in entries:
        if current_block != entry.block or not events:
            events.append(LogEvent(entries=[entry], last_timestamp=entry.timestamp))
            current_block = entry.block
        else:
            events[-1].entries.append(entry)
    return events


def collapse_repeated(events: list[LogEvent]) -> list[LogEvent]:
    """Merge identical events (same codes, sources, functions and messages)."""
    merged: dict[tuple, LogEvent] = {}
    order: list[tuple] = []
    for event in events:
        key = event.signature()
        if key in merged:
            target = merged[key]
            target.count += 1
            if event.timestamp and (target.last_timestamp is None or event.timestamp > target.last_timestamp):
                target.last_timestamp = event.timestamp
        else:
            merged[key] = LogEvent(entries=event.entries, count=1, last_timestamp=event.timestamp)
            order.append(key)
    return [merged[key] for key in order]
