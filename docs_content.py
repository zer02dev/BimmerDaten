"""
docs_content.py
Content of the Docs tab: plain-language explanations of the BMW Standard Tools
(EDIABAS, INPA, Tool32, NCS Expert, WinKFP), their files and BimmerDaten itself.

Each topic is a small HTML fragment (Qt rich text subset). Links inside the body:
    doc:<topic-id>          open another topic
    app:<tab>[/<sub-tab>]   switch to a BimmerDaten tab (diagnosis, coding, sa, winkfp)
Topics may list `locations` - (folder, glob) pairs with {ROOT} placeholders that the
Docs tab resolves on this PC (see ROOT_KEYS).
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from html import escape

from winkfp_widgets import COLOR_ERROR, COLOR_INFO, COLOR_MUTED, COLOR_OK, COLOR_WARNING

# Placeholders usable in DocTopic.locations; resolved by the Docs tab.
ROOT_KEYS = ("EDIABAS", "ECU", "INPA", "NCS", "NFS", "WINDOWS", "APPDATA")


@dataclass(frozen=True)
class DocTopic:
    id: str
    section: str
    title: str
    summary: str
    body: str
    keywords: tuple[str, ...] = ()
    locations: tuple[tuple[str, str], ...] = ()
    related: tuple[str, ...] = ()


# --------------------------------------------------------------------------- helpers

def c(text: str) -> str:
    """Inline code (escaped)."""
    return f"<code>{escape(text)}</code>"


def link(topic_id: str, text: str) -> str:
    return f'<a href="doc:{topic_id}">{text}</a>'


def app(target: str, text: str) -> str:
    return f'<a href="app:{target}">{text}</a>'


_CALLOUT = {
    "info": ("#e8f0fb", COLOR_INFO, "ℹ️"),
    "tip": ("#e7f4e8", COLOR_OK, "💡"),
    "warn": ("#fdf1e1", COLOR_WARNING, "⚠️"),
    "danger": ("#fbe6e9", COLOR_ERROR, "⛔"),
}


def note(html: str, kind: str = "info") -> str:
    bg, fg, icon = _CALLOUT[kind]
    return (
        f'<table width="100%" cellpadding="8" cellspacing="0" bgcolor="{bg}" '
        f'style="margin-top:6px; margin-bottom:8px; border-left: 4px solid {fg};">'
        f'<tr><td><span style="color:{fg}; font-weight:bold;">{icon}</span>&nbsp; {html}</td></tr></table>'
    )


def table(headers: list[str], rows: list[list[str]], widths: list[int] | None = None) -> str:
    head = "".join(
        f'<th align="left" bgcolor="#e2dfd8"{f" width={widths[i]}%" if widths else ""}>{h}</th>'
        for i, h in enumerate(headers)
    )
    body = ""
    for n, row in enumerate(rows):
        bg = "#ffffff" if n % 2 == 0 else "#eef2f8"
        body += f'<tr bgcolor="{bg}">' + "".join(f"<td valign=top>{cell}</td>" for cell in row) + "</tr>"
    return (
        '<table width="100%" border="1" cellspacing="0" cellpadding="5" '
        'style="border-collapse: collapse; border-color: #b8bcc4; margin-top:4px; margin-bottom:8px;">'
        f"<tr>{head}</tr>{body}</table>"
    )


def steps(items: list[str]) -> str:
    return "<ol>" + "".join(f"<li>{i}</li>" for i in items) + "</ol>"


def bullets(items: list[str]) -> str:
    return "<ul>" + "".join(f"<li>{i}</li>" for i in items) + "</ul>"


def muted(text: str) -> str:
    return f'<span style="color:{COLOR_MUTED};">{text}</span>'


FAM = "&lt;family&gt;"
LANG = "&lt;lang&gt;"

SECTIONS = [
    "Start here",
    "Programs",
    "EDIABAS & INPA files",
    "NCS Expert",
    "WinKFP: how it works",
    "WinKFP: files",
    "Errors & troubleshooting",
    "Using BimmerDaten",
    "Glossary",
]

TOPICS: list[DocTopic] = []


# Python < 3.12 does not allow backslashes inside f-string expressions, so paths in
# those expressions use BACKSLASH_MARK; topic() turns it back into "\\".
BACKSLASH_MARK = "⧵"


def topic(*args, **kwargs) -> DocTopic:
    t = DocTopic(*args, **kwargs)
    if BACKSLASH_MARK in t.body:
        t = replace(t, body=t.body.replace(BACKSLASH_MARK, "\\"))
    TOPICS.append(t)
    return t


# =========================================================================== Start here

topic(
    "overview",
    "Start here",
    "BMW Standard Tools at a glance",
    "Which program does what, and how they talk to the car.",
    f"""
<p><b>BMW Standard Tools</b> is a bundle of BMW's own workshop programs (2000s era, E-series cars and early
F-series). Each program has one job; they all share the same diagnostic layer, <b>EDIABAS</b>.</p>
{table(["Program", "What it is for", "Writes to the car?"], [
    [link("ediabas", "EDIABAS"), "The diagnostic engine every other tool uses. Loads an ECU description file (.prg) and talks to the ECU through the cable.", "Only when a program asks it to"],
    [link("tool32", "Tool32"), "Run single EDIABAS jobs by hand (read ident, faults, live values, …).", "Yes, if you run a writing job"],
    [link("inpa", "INPA"), "Ready-made diagnosis screens per car and ECU: faults, live data, tests, resets.", "Some functions (resets, adaptations)"],
    [link("ncs-expert", "NCS Expert"), "<b>Coding</b>: changing the configuration of an ECU (options, features, vehicle order).", "Yes — coding"],
    [link("winkfp", "WinKFP"), "<b>Flashing / programming</b>: replacing the software (program + data) of an ECU.", "Yes — flashing"],
    [link("bimmerdaten", "BimmerDaten"), "Reads all of the above files and explains them; edits NCS coding files offline.", "<b>Never</b>"],
], [18, 62, 20])}
<h4>How a program talks to an ECU</h4>
<table cellpadding="6" cellspacing="0" width="100%"><tr>
<td bgcolor="#e8f0fb" align="center"><b>INPA / NCS Expert /<br>WinKFP / Tool32</b></td><td align="center">→</td>
<td bgcolor="#e8f0fb" align="center"><b>EDIABAS</b><br>{muted("api32.dll + EDIABAS.INI")}</td><td align="center">→</td>
<td bgcolor="#e8f0fb" align="center"><b>SGBD</b><br>{muted("C:⧵EDIABAS⧵Ecu⧵*.prg")}</td><td align="center">→</td>
<td bgcolor="#e8f0fb" align="center"><b>Interface</b><br>{muted("STD:OBD = K+DCAN cable")}</td><td align="center">→</td>
<td bgcolor="#e8f0fb" align="center"><b>ECU</b><br>{muted("in the car")}</td>
</tr></table>
<p>Coding and flashing need extra BMW data that tells the tools what is valid for each car and ECU. That data
comes in <b>{link("sp-daten", "SP-Daten")}</b> packages and lives in the {link("folders", "data folders")} of each program.</p>
{note("New here? Read " + link("coding-vs-flashing", "Coding vs. flashing") + " first, then the page of the program you want to use.", "tip")}
""",
    keywords=("standard tools", "bmw tools", "introduction", "start"),
    related=("folders", "coding-vs-flashing", "sp-daten"),
)

topic(
    "coding-vs-flashing",
    "Start here",
    "Coding vs. flashing",
    "Coding changes settings; flashing replaces the software.",
    f"""
<p>These two words are often mixed up, but they are different operations done by different programs.</p>
{table(["", "Coding", "Flashing (programming)"], [
    ["What changes", "Configuration bytes of the ECU: which features are on, language, units, equipment.", "The ECU's whole <b>program</b> and <b>data</b> (maps, calibration)."],
    ["Program", link("ncs-expert", "NCS Expert"), link("winkfp", "WinKFP")],
    ["Files", f"{c('DATEN')} (.Cxx), CABD {c('A_*.ipo')}, {c('FSW_PSW.TRC/MAN')}", f"{c('DATA')} (0PA / 0DA), PABD {c('*.ipo')}, P-SGBD {c('*.prg')}"],
    ["Time", "Seconds", "Minutes (up to ~30 min for big ECUs)"],
    ["Risk", "Low — wrong coding can be redone.", "Higher — an interrupted flash can leave the ECU unusable until flashed again."],
    ["Typical use", "Retrofits, enabling / disabling features, after replacing an ECU.", "Software updates, fixes, replacing a used ECU with different software."],
])}
<p>After flashing an ECU it usually has to be <b>coded</b> again, because flashing resets the coding.</p>
{note("Both programs read their sequence files (.ipo) from the same <b>SGDAT</b> folder. That is why WinKFP lets you pick a coding file (CABD) as PABD — and then fails with error 1063. See " + link("ipo-files", ".ipo files: PABD, CABD, SWT") + ".", "warn")}
""",
    keywords=("coding", "flashing", "programming", "difference", "codieren", "programmieren"),
    related=("ncs-expert", "winkfp", "ipo-files"),
)

topic(
    "folders",
    "Start here",
    "Where everything lives",
    "The default folders of each program and what is inside.",
    table(["Folder", "Program", "Contents"], [
        [c("C:\\EDIABAS\\Bin"), "EDIABAS", f"Runtime, {c('EDIABAS.INI')}, Tool32 ({c('ToolSet32.exe')})"],
        [c("C:\\EDIABAS\\Ecu"), "EDIABAS", f"{link('sgbd', 'SGBD')} files {c('*.prg')} / {c('*.grp')} — shared by all programs"],
        [c("C:\\EDIABAS\\Trace"), "EDIABAS", "Trace files when tracing is switched on"],
        [c("C:\\EC-APPS\\INPA"), "INPA", f"{c('BIN')}, {c('CFGDAT')} (menus, INPA.INI), {c('SGDAT')} (compiled INPA scripts)"],
        [c("C:\\NCSEXPER\\BIN"), "NCS Expert", f"{c('NCSEXPER.exe')}, {c('NCSEXPER.INI')}"],
        [c("C:\\NCSEXPER\\CFGDAT"), "NCS Expert", f"{c('COAPI.INI')}, error texts, English UI texts ({c('NCSEXPER.TXT')})"],
        [c("C:\\NCSEXPER\\DATEN"), "NCS Expert", f"Coding data per chassis ({link('ncs-daten', 'DATEN')})"],
        [c("C:\\NCSEXPER\\PFL"), "NCS Expert", f"{link('ncs-profiles', 'Profiles')} (*.pfl)"],
        [c("C:\\NCSEXPER\\SGDAT"), "NCS Expert", f"Coding sequences (CABD {c('A_*.ipo')}) — identical to WinKFP's SGDAT"],
        [c("C:\\NCSEXPER\\WORK"), "NCS Expert", f"{link('ncs-work-files', 'Work files')}: FSW_PSW.TRC / .MAN, FA, SYSDATEN …"],
        [c("C:\\EC-APPS\\NFS\\BIN"), "WinKFP", f"{c('winkfpt.exe')}, {link('winkfpt-ini', 'Winkfpt.ini')}, error logs, .OUT result files"],
        [c("C:\\EC-APPS\\NFS\\CFGDAT"), "WinKFP", f"{c('COAPI.INI')}, error texts ({link('coapi-files', 'COAPI files')})"],
        [c("C:\\EC-APPS\\NFS\\DATA"), "WinKFP", f"{c('gdaten')} (global tables) + one folder per {link('ecu-family', 'ECU family')}"],
        [c("C:\\EC-APPS\\NFS\\SGDAT"), "WinKFP", "PABD / CABD / SWT sequence files (*.ipo)"],
        [c("%LOCALAPPDATA%\\BimmerDaten"), "BimmerDaten", link("bimmerdaten-data", "Database, backups, snapshots, logs")],
    ], [30, 15, 55]) + note(
        "Folders named like " + c("SGDAT_20260509_002519") + " or " + c("DATA_20260509_004334")
        + " are backups made by SP-Daten installers (e.g. BMW Coding Tool). Keep them — BimmerDaten can compare with and restore from them. See "
        + link("sp-daten", "SP-Daten updates") + ".", "tip"),
    keywords=("paths", "directories", "install", "location", "c:\\"),
    locations=(("{EDIABAS}", "*"), ("{NCS}", "*"), ("{NFS}", "*"), ("{INPA}", "*")),
    related=("overview", "sp-daten"),
)

topic(
    "sp-daten",
    "Start here",
    "SP-Daten updates",
    "The data packages that keep the tools up to date — and what they replace.",
    f"""
<p><b>SP-Daten</b> (Service-Programm-Daten) is BMW's data package for the Standard Tools, released per chassis
series (E46, E60, E9x, F-series …). Installing it updates the data folders of all programs:</p>
{table(["Folder", "Used by", "What the package brings"], [
    [c("EDIABAS⧵Ecu"), "all", "New / updated SGBD (*.prg) files"],
    [c("NCSEXPER⧵DATEN"), "NCS Expert", "Coding data per chassis"],
    [c("NCSEXPER⧵SGDAT"), "NCS Expert, WinKFP", "Coding sequences (CABD) and flash sequences (PABD)"],
    [c("NFS⧵DATA"), "WinKFP", "Flash files (0PA/0DA) and logistics per ECU family, plus gdaten"],
])}
<p>Tools like <i>BMW Coding Tool</i> copy the package into place and keep the previous state in folders named
{c('<folder>_YYYYMMDD_HHMMSS')}.</p>
{note("An SP-Daten install can <b>replace</b> the whole " + c("NFS⧵DATA") + " folder instead of adding to it. ECU families from the previous package then disappear (they are still in the " + c("DATA_…") + " backup). " + app("winkfp/families", "📦 Families") + " shows them as “Only in backup” and can restore them.", "warn")}
{note("Many packages do not contain a new " + c("DATA⧵gdaten") + ". Then " + link("kfconf", "KFCONF") + " still lists old PABD names that are no longer in SGDAT, and Comfort mode fails with error 1065 / 106. " + app("winkfp/health", "🩺 Health") + " finds and fixes this.", "info")}
<p>After an update, {app("winkfp/updates", "🔄 Updates")} shows exactly what changed compared with the last saved state.</p>
""",
    keywords=("sp-daten", "update", "data package", "bmw coding tool", "backup", "psdz"),
    related=("folders", "kfconf", "ecu-family"),
)

# =========================================================================== Programs

topic(
    "ediabas",
    "Programs",
    "EDIABAS",
    "The diagnostic engine under every BMW tool.",
    f"""
<p><b>EDIABAS</b> (Elektronik-Diagnose-Basissystem) is the layer between a program and the car. A program
(INPA, NCS Expert, WinKFP, Tool32) never builds telegrams itself — it asks EDIABAS to run a <b>{link("job", "job")}</b>
from an ECU description file:</p>
{steps([
    f"The program calls EDIABAS: <i>run job {c('IDENT')} from {c('D_MOTOR')}</i>.",
    f"EDIABAS loads the {link('sgbd', 'SGBD')} ({c('*.prg')} / {c('*.grp')}) from {c('EcuPath')}.",
    f"The job (compiled {link('g-best', 'BEST/1')} code) builds the request and sends it through the <b>interface</b> set in {link('ediabas-ini', 'EDIABAS.INI')}.",
    "The ECU answers; the job decodes the answer into named <b>results</b> (e.g. HW number, fault code text).",
])}
<p>Important settings are in {link("ediabas-ini", "EDIABAS.INI")}: the interface ({c("STD:OBD")} for a K+DCAN cable,
{c("ENET")} for F-series Ethernet), simulation mode and tracing.</p>
<p>In BimmerDaten, the {app("diagnosis", "🔧 Diagnosis")} tab opens any SGBD and shows its jobs, arguments,
results, tables and the disassembled code — without connecting to a car.</p>
""",
    keywords=("ediabas", "api", "runtime", "interface", "diagnose", "basissystem"),
    locations=(("{EDIABAS}\\Bin", "EDIABAS.INI"), ("{ECU}", "*.prg")),
    related=("sgbd", "job", "ediabas-ini", "tool32"),
)

topic(
    "tool32",
    "Programs",
    "Tool32",
    "Runs single EDIABAS jobs by hand.",
    f"""
<p><b>Tool32</b> ({c("C:⧵EDIABAS⧵Bin⧵ToolSet32.exe")}) is the engineer's tool: you open an SGBD, pick a
{link("job", "job")}, type the arguments and see the raw results. Everything INPA, NCS Expert and WinKFP do is built
from such jobs.</p>
<p>Typical read-only jobs: {c("IDENT")} (part numbers, HW / SW numbers), {c("FS_LESEN")} (read faults),
{c("STATUS_*")} (live values), {c("AIF_LESEN")} (last programming info).</p>
{note("Tool32 will also run writing jobs (" + c("FS_LOESCHEN") + ", " + c("*_SCHREIBEN") + ", " + c("STEUERN_*") + ") without asking. Check what a job does first — the " + app("diagnosis", "🔧 Diagnosis") + " tab shows its description, arguments and results.", "warn")}
""",
    keywords=("tool32", "toolset32", "toolset", "job runner"),
    locations=(("{EDIABAS}\\Bin", "ToolSet32.exe"),),
    related=("ediabas", "job", "sgbd"),
)

topic(
    "inpa",
    "Programs",
    "INPA",
    "Ready-made diagnosis screens for each car and ECU.",
    f"""
<p><b>INPA</b> (Interpreter für Prüfabläufe — interpreter for test procedures) runs scripts that show
diagnosis screens: fault memory, live values, component tests, service resets, adaptations.</p>
{bullets([
    f"Start menu per chassis: {c('CFGDAT⧵E46.ENG')} etc. list which script belongs to which ECU.",
    f"Scripts: {c('SGDAT⧵*.IPO')} (compiled) — sources are {c('*.IPS')}.",
    f"Settings: {c('CFGDAT⧵INPA.INI')}.",
    "Every screen calls EDIABAS jobs from the SGBD in the background.",
])}
<p>BimmerDaten's Diagnosis → {app("diagnosis", "🚗 Models")} sub-tab reads the INPA menus and shows which SGBD belongs to
which car and ECU.</p>
{note("INPA scripts, NCS coding sequences (CABD) and WinKFP flash sequences (PABD) are all compiled scripts with the extension " + c(".ipo") + ". They are different programs with the same file format — see " + link("ipo-files", ".ipo files") + ".", "info")}
""",
    keywords=("inpa", "ips", "ipo", "diagnosis screens", "interpreter"),
    locations=(("{INPA}\\CFGDAT", "*.ENG"), ("{INPA}\\SGDAT", "*.IPO")),
    related=("ediabas", "ipo-files"),
)

topic(
    "ncs-expert",
    "Programs",
    "NCS Expert",
    "BMW's coding tool: reads and writes ECU configuration.",
    f"""
<p><b>NCS Expert</b> (Network Coding System) codes ECUs: it decides, from the car's
{link("g-fa", "vehicle order (FA)")} or {link("g-zcs", "ZCS")}, which features each ECU should have and writes the
matching configuration.</p>
<h4>Two ways to code</h4>
{table(["Way", "How", "When"], [
    ["By vehicle order", f"Job {c('SG_CODIEREN')} without changes: NCS calculates the coding from FA / ZCS and the {link('ncs-daten', 'DATEN')} files.", "After replacing / flashing an ECU, after a retrofit with a changed FA."],
    ["Manual (FSW/PSW)", f"Read the coding ({c('FSW_PSW.TRC')}), change single options, write them via {c('FSW_PSW.MAN')}.", "Enabling or disabling single features."],
])}
<p>Step by step: {link("ncs-workflow", "NCS Expert coding workflow")}. Files: {link("ncs-work-files", "WORK folder")},
{link("ncs-daten", "DATEN folder")}, {link("ncs-profiles", "profiles")}.</p>
<p>BimmerDaten's {app("coding", "⚙️ Coding")} tab edits the TRC / MAN files with translations and validation, and
{app("sa", "🔧 SA Options")} decodes the vehicle order.</p>
""",
    keywords=("ncs", "ncs expert", "coding", "codieren", "network coding system"),
    locations=(("{NCS}\\BIN", "NCSEXPER.exe"),),
    related=("ncs-workflow", "ncs-work-files", "ncs-daten", "fsw-psw"),
)

topic(
    "winkfp",
    "Programs",
    "WinKFP",
    "BMW's flash tool, part of NFS.",
    f"""
<p><b>WinKFP</b> (Windows-Kundendienst-Flash-Programm, {c("winkfpt.exe")}) replaces the software of an ECU.
It is installed as part of <b>NFS</b> (Neues Flash-System) in {c("C:⧵EC-APPS⧵NFS")}.</p>
<p>To flash an ECU WinKFP needs four things:</p>
{table(["What", "File", "Where"], [
    [link("pabd", "PABD"), "Flash sequence (what to do, in which order)", c("NFS⧵SGDAT⧵*.ipo")],
    [link("pabd", "P-SGBD"), "SGBD with the flash jobs", c("EDIABAS⧵Ecu⧵*.prg")],
    [link("integration-position", "ECU address"), "Where the ECU is on the bus", f"{c('INFO.' + '<lang>')} or typed by you"],
    [link("flash-files", "Flash files"), "Program (0PA) and data (0DA)", c("NFS⧵DATA⧵<family>")],
])}
<h4>Two modes</h4>
<p><b>Comfort</b> — you enter a {link("zb-number", "ZB number")} and WinKFP finds everything else and checks
compatibility. <b>Expert</b> — you choose all four items yourself, nothing is checked.
Details: {link("comfort-expert", "Comfort vs. Expert mode")}.</p>
{note("Nothing is written to the ECU until you press a programming button (Prog. Program / Prog. Data / Program ZB). Reading ident, UIF and diagnosis functions are read-only.", "info")}
<p>BimmerDaten's {app("winkfp", "⚡ WinKFP")} tab checks the installation, shows ECU families and
tells you {app("winkfp/what to flash", "what to flash")}.</p>
""",
    keywords=("winkfp", "winkfpt", "nfs", "flash", "programming", "kundendienst"),
    locations=(("{NFS}\\BIN", "winkfpt.exe"),),
    related=("comfort-expert", "flash-workflow", "ecu-family", "pabd"),
)

topic(
    "bimmerdaten",
    "Programs",
    "BimmerDaten",
    "What this app does and what it never does.",
    f"""
<p><b>BimmerDaten</b> reads the files of the BMW Standard Tools and explains them in plain English.</p>
{table(["Tab", "What it does"], [
    [app("diagnosis", "🔧 Diagnosis"), "Opens SGBD (.prg) files: jobs, arguments, results, tables, disassembly; INPA models."],
    [app("coding", "⚙️ Coding"), "Edits NCS Expert FSW_PSW.TRC with translations, validation, presets; exports FSW_PSW.MAN."],
    [app("sa", "🔧 SA Options"), "Decodes the vehicle order (FA / SA codes) of the car."],
    [app("winkfp", "⚡ WinKFP"), "Checks and repairs the WinKFP installation, lists ECU families, finds what to flash, explains errors."],
    [app("docs", "📖 Docs"), "This page."],
])}
{note("BimmerDaten never connects to the car. Coding is written by NCS Expert, flashing is done by WinKFP. Every change BimmerDaten makes to WinKFP files is previewed, backed up and can be undone.", "info")}
""",
    keywords=("bimmerdaten", "app", "about"),
    related=("bimmerdaten-data", "overview"),
)

# =========================================================================== EDIABAS & INPA files

topic(
    "sgbd",
    "EDIABAS & INPA files",
    "SGBD files (.prg / .grp)",
    "ECU description files that contain the jobs EDIABAS runs.",
    f"""
<p>An <b>SGBD</b> (Steuergeräte-Beschreibungsdatei, ECU description file) describes how to talk to one ECU.
It contains compiled {link("job", "jobs")} and data tables (fault code texts, live value scaling …).</p>
{table(["Type", "Example", "Meaning"], [
    [c(".prg"), c("MS430DS0.prg"), "Variant SGBD for one ECU version."],
    [c(".grp"), c("D_MOTOR.grp"), "Group SGBD: first identifies which variant is fitted, then EDIABAS uses that variant's .prg."],
    [c(".prg"), c("22EK92.PRG"), "<b>P-SGBD</b>: SGBD with the flash jobs for an ECU family (used by WinKFP)."],
])}
<p>All SGBDs live in {c("EDIABAS⧵Ecu")} and are shared by Tool32, INPA, NCS Expert and WinKFP.</p>
<p>Open one in {app("diagnosis", "🔧 Diagnosis")} (File → Open .PRG) to see every job with its description.</p>
""",
    keywords=("sgbd", "prg", "grp", "ecu file", "p-sgbd", "steuergeraete beschreibungsdatei"),
    locations=(("{ECU}", "*.prg"), ("{ECU}", "*.grp")),
    related=("job", "ediabas", "pabd"),
)

topic(
    "job",
    "EDIABAS & INPA files",
    "Jobs, arguments, results and tables",
    "The building blocks inside an SGBD.",
    f"""
{table(["Term", "Meaning", "Example"], [
    ["<b>Job</b>", "A named procedure in an SGBD — one request to the ECU and the decoding of its answer.", c("IDENT, FS_LESEN, STATUS_MOTORDREHZAHL")],
    ["<b>Argument</b>", "Input value given to a job.", f"{c('STEUERN_DIGITAL')} with argument {c('ON')}"],
    ["<b>Result</b>", "Named output value of a job.", c("ID_BMW_NR, STAT_MOTORDREHZAHL_WERT")],
    ["<b>Table</b>", "Data inside the SGBD: fault texts, units, live value definitions.", c("FORTTEXTE, BETRIEBSWTAB")],
])}
<p>Job name prefixes tell you what a job does:</p>
{table(["Prefix", "Meaning", "Writes?"], [
    [c("IDENT, *_LESEN, STATUS_*"), "read (lesen = read)", f'<span style="color:{COLOR_OK};">no</span>'],
    [c("FS_LOESCHEN, IS_LOESCHEN"), "clear fault / info memory", f'<span style="color:{COLOR_WARNING};">yes</span>'],
    [c("STEUERN_*"), "drive an actuator (steuern = control)", f'<span style="color:{COLOR_WARNING};">yes</span>'],
    [c("*_SCHREIBEN, SG_CODIEREN"), "write / code (schreiben = write)", f'<span style="color:{COLOR_ERROR};">yes</span>'],
    [c("FLASH_*, *_PROGRAMMIEREN"), "flash / program", f'<span style="color:{COLOR_ERROR};">yes</span>'],
])}
""",
    keywords=("job", "argument", "result", "table", "betriebswtab", "lesen", "schreiben", "steuern"),
    related=("sgbd", "g-best"),
)

topic(
    "ediabas-ini",
    "EDIABAS & INPA files",
    "EDIABAS.INI and OBD.INI",
    "Interface, ECU path, simulation and trace settings.",
    f"""
{table(["Setting", "Meaning"], [
    [c("Interface = STD:OBD"), "Diagnostic interface. STD:OBD = OBD / K+DCAN cable on a COM port; ENET = Ethernet (F-series)."],
    [c("EcuPath = C:⧵EDIABAS⧵ECU"), "Where the SGBD files are."],
    [c("Simulation = 0"), "1 = answers come from files in SimulationPath instead of the car."],
    [c("ApiTrace / IfhTrace"), f"Trace levels (0 = off). Traces go to {c('TracePath')}; use only for troubleshooting, they get big."],
])}
<p><b>OBD.INI</b> (in {c("C:⧵Windows")} or {c("EDIABAS⧵Bin")}) sets the COM port of the K+DCAN cable,
e.g. {c("Port=Com1")}. The port in Device Manager must match; a latency of 1 ms is recommended.</p>
{note("Error IFH-0018 / IFH-0009 in any tool almost always means: wrong COM port, cable not plugged in, ignition off, or another program is using the interface.", "tip")}
""",
    keywords=("ediabas.ini", "obd.ini", "interface", "std:obd", "enet", "com port", "trace", "simulation"),
    locations=(("{EDIABAS}\\Bin", "EDIABAS.INI"), ("{WINDOWS}", "obd.ini"), ("{EDIABAS}\\Bin", "obd.ini")),
    related=("ediabas", "errors-ifh"),
)

topic(
    "ipo-files",
    "EDIABAS & INPA files",
    ".ipo files: PABD, CABD, SWT",
    "Compiled sequence scripts — three kinds share one folder.",
    f"""
<p>An {c(".ipo")} file is a compiled script ({c(".ips")} source). In {c("SGDAT")} there are three different kinds,
and WinKFP's Expert mode lists all of them without telling you which is which:</p>
{table(["Kind", "Used by", "Name pattern", "Typical jobs inside"], [
    ["🔧 <b>PABD</b><br>flash sequence", "WinKFP", f"version + family, e.g. {c('07dde71.ipo')}, {c('22EK924.IPO')}", c("SG_PROGRAMMIEREN, FlashSchreiben, SG_AIF_LESEN, SET_ECU_ADDRESS")],
    ["✏️ <b>CABD</b><br>coding sequence", "NCS Expert", f"{c('A_*.ipo')}, e.g. {c('A_ME9_4N.ipo')}", c("SG_CODIEREN, CODIERDATEN_LESEN, FGNR_SCHREIBEN")],
    ["🔑 <b>SWT</b><br>activation codes", "SWT / FSC tools", c("00swtkwp.ipo, 01swt.ipo"), c("STORE_FSC, CHECK_FSC, STORE_CERTIFICATE")],
])}
{note("Choosing a CABD (" + c("A_*.ipo") + ") as PABD in WinKFP fails with <b>error 1063</b> (“CABD parameter error”) because the file has no flash jobs. Nothing is sent to the ECU. Pick a 🔧 PABD instead — " + app("winkfp/sgdat", "🗂 SGDAT") + " labels every file.", "warn")}
<p>{c("A_EWSSYN.ipo")} is a special CABD: it synchronises the EWS immobiliser with the engine ECU.
INPA scripts in {c("INPA⧵SGDAT")} are a fourth use of the same format.</p>
""",
    keywords=("ipo", "ips", "pabd", "cabd", "swt", "fsc", "a_", "sgdat", "1063"),
    locations=(("{NFS}\\SGDAT", "*.ipo"), ("{NCS}\\SGDAT", "*.ipo")),
    related=("pabd", "g-swt-fsc", "errors-common"),
)

# =========================================================================== NCS Expert

topic(
    "ncs-workflow",
    "NCS Expert",
    "NCS Expert coding workflow",
    "Reading, changing and writing coding — step by step.",
    f"""
<p>The usual DIY workflow for changing single options (with an Expert-mode {link("ncs-profiles", "profile")}):</p>
{steps([
    "<b>File → Load profile</b> — choose an expert profile.",
    "<b>VIN/ZCS/FA</b> → <b>ZCS/FA f. ECU</b> → choose the chassis and an ECU that holds the vehicle order (e.g. KOMBI / CAS). NCS reads FA / ZCS from the car.",
    "<b>Process ECU</b> → select the ECU to code.",
    f"<b>Change job</b> → {c('CODIERDATEN_LESEN')} → <b>Execute job</b>. NCS writes the current coding to {c('WORK⧵FSW_PSW.TRC')}.",
    f"Change the options — in BimmerDaten {app('coding', '⚙️ Coding')}: <b>Load TRC</b>, edit, <b>Export .MAN</b> (writes {c('FSW_PSW.MAN')}).",
    f"<b>Change job</b> → {c('SG_CODIEREN')} → <b>Execute job</b>. NCS codes the ECU and applies the changes from {c('FSW_PSW.MAN')}.",
    f"Empty {c('FSW_PSW.MAN')} again afterwards, so the next {c('SG_CODIEREN')} on another ECU does not apply it by mistake.",
])}
{note("Running " + c("SG_CODIEREN") + " with an empty MAN file codes the ECU back to the factory defaults for your vehicle order — all manual changes on that ECU are lost.", "warn")}
{note("Back up: copy " + c("FSW_PSW.TRC") + " (and " + c("NETTODAT.TRC") + ") of every ECU before you change it. BimmerDaten keeps a coding history too.", "tip")}
""",
    keywords=("workflow", "sg_codieren", "codierdaten_lesen", "process ecu", "change job", "how to code"),
    related=("ncs-work-files", "fsw-psw", "ncs-profiles"),
)

topic(
    "fsw-psw",
    "NCS Expert",
    "FSW and PSW (coding keywords)",
    "How a coding option and its value are named.",
    f"""
<p>Coding is written as keyword pairs:</p>
{table(["Term", "German", "Meaning", "Example"], [
    ["<b>FSW</b>", "Funktionsschlüsselwort", "Function keyword — the option", c("KALTSTART_REDUZIERUNG")],
    ["<b>PSW</b>", "Parameterschlüsselwort", "Parameter keyword — its value", c("aktiv / nicht_aktiv")],
    ["<b>ASW</b>", "Auftragsschlüsselwort", "Order keyword — links equipment to coding", ""],
])}
<p>{c("FSW_PSW.TRC")} lists one FSW followed by its PSW on the next line (indented). The names are German
abbreviations; BimmerDaten shows translations from NCS Dummy's {c("Translations.csv")} if you have it.</p>
<p>The keyword dictionaries are {c("SWTFSW??.DAT")}, {c("SWTPSW??.DAT")} and {c("SWTASW??.DAT")} in each chassis
folder of {link("ncs-daten", "DATEN")}.</p>
""",
    keywords=("fsw", "psw", "asw", "keyword", "option", "value", "aktiv", "nicht_aktiv", "translations.csv"),
    locations=(("{NCS}\\DATEN\\E46", "SWT*.DAT"),),
    related=("ncs-work-files", "ncs-daten"),
)

topic(
    "ncs-work-files",
    "NCS Expert",
    "WORK folder files (TRC / MAN)",
    "FSW_PSW.TRC, FSW_PSW.MAN, NETTODAT.TRC, FA.TRC, SYSDATEN.TRC …",
    table(["File", "Written by", "Contents"], [
        [c("FSW_PSW.TRC"), f"NCS ({c('CODIERDATEN_LESEN')})", "Current coding of the last ECU read, as FSW / PSW lines."],
        [c("FSW_PSW.MAN"), "You / BimmerDaten", f"Manipulation file: the coding to write with {c('SG_CODIEREN')}. Should be empty when not coding."],
        [c("NETTODAT.TRC"), "NCS", "The same coding as raw bytes (blocks / addresses). Good as a backup."],
        [c("FA.TRC"), "NCS", f"{link('g-fa', 'Vehicle order')}: type key, SA codes, paint, upholstery …"],
        [c("SYSDATEN.TRC"), "NCS", "VIN, ECU part number, production date, SA list. BimmerDaten shows the VIN from it."],
        [c("ASW.TRC, ASW1/2.TRC"), "NCS", "Chassis / order keywords. First line = chassis (e.g. E46) — BimmerDaten detects the model from it."],
        [c("ABLAUF.TRC"), "NCS", "Log of the last NCS run (which steps were executed)."],
    ], [20, 25, 55]),
    keywords=("trc", "man", "fsw_psw", "nettodat", "fa.trc", "sysdaten", "asw", "work"),
    locations=(("{NCS}\\WORK", "*.TRC"), ("{NCS}\\WORK", "*.MAN")),
    related=("ncs-workflow", "fsw-psw", "g-fa"),
)

topic(
    "ncs-daten",
    "NCS Expert",
    "DATEN folder (coding data)",
    "Per-chassis coding data: .Cxx module files, AT / ZST tables, keyword dictionaries.",
    f"""
<p>{c("NCSEXPER⧵DATEN")} has one folder per chassis ({c("E36, E46, E60 …")}). Inside:</p>
{table(["File", "Meaning"], [
    [c("<module>.Cxx") + "<br>" + c("GM5.C05, EK924.C11"), f"<b>Coding data</b> for one ECU. {c('xx')} is the {link('g-coding-index', 'coding index')} (hex) the ECU reports — NCS picks the file that matches the ECU in the car."],
    [c("<chassis>AT.000"), "Order table: which SA / FA codes switch which coding options. Used for coding by vehicle order (BimmerDaten's SA Options reads it)."],
    [c("<chassis>ZST.000"), f"Table for decoding the {link('g-zcs', 'ZCS')} (older cars)."],
    [c("SWTFSW??.DAT, SWTPSW??.DAT, SWTASW??.DAT"), f"Keyword dictionaries ({link('fsw-psw', 'FSW / PSW / ASW')})."],
    [c("SGET, SGVT, CVT, ZCSUT, AEDOC, SGFAM.DAT"), "Internal tables: which ECUs exist on the chassis, versions, change history. NCS reads them; never edit."],
])}
{note("Coding data and flash data are separate: NCS DATEN is not used by WinKFP, and WinKFP's DATA is not used by NCS.", "info")}
""",
    keywords=("daten", "cxx", "c01", "at.000", "zst", "module", "coding data", "sgfam"),
    locations=(("{NCS}\\DATEN", "*"), ("{NCS}\\DATEN\\E46", "*.C??")),
    related=("fsw-psw", "g-coding-index", "g-fa", "g-zcs"),
)

topic(
    "ncs-profiles",
    "NCS Expert",
    "NCS profiles (.pfl)",
    "Profiles decide what NCS Expert allows and shows.",
    f"""
<p>A <b>profile</b> ({c("NCSEXPER⧵PFL⧵*.pfl")}) is a set of NCS Expert settings: which menus are visible,
whether jobs other than {c("SG_CODIEREN")} are offered, whether {c("FSW_PSW.MAN")} is used, and how the
{link("g-fa", "vehicle order")} is read.</p>
{bullets([
    "Expert profiles (e.g. “Expertmodus”) show all jobs and use the manipulation file — needed for manual coding.",
    "The default profile only codes by vehicle order.",
])}
<p>The keys that matter for manual coding:</p>
{table(["Key", "Must be", "Effect"], [
    [c("FswPswLesenModus"), c("1"), f"Reading coding writes {c('FSW_PSW.TRC')}."],
    [c("FswPswManipulieren"), c("1"), f"{c('SG_CODIEREN')} applies {c('FSW_PSW.MAN')}."],
    [c("FktSgCodieren"), c("1"), f"Job {c('SG_CODIEREN')} is allowed."],
])}
<p>BimmerDaten's {app("coding", "⚙️ Coding")} tab reads the profiles and shows in the orange bar which of them can read and
write manual coding.</p>
""",
    keywords=("profile", "pfl", "expertmodus", "expert mode", "ncs profile"),
    locations=(("{NCS}\\PFL", "*.pfl"),),
    related=("ncs-workflow",),
)

# =========================================================================== WinKFP: how it works

topic(
    "comfort-expert",
    "WinKFP: how it works",
    "Comfort vs. Expert mode",
    "WinKFP chooses the files for you — or you choose them yourself.",
    f"""
{table(["", "Comfort", "Expert"], [
    ["You enter", f"{link('zb-number', 'ZB number')} (or F3 Update ZUSB) and {link('integration-position', 'integration position')}", f"PABD, P-SGBD, ECU address, program file (0PA), data file (0DA)"],
    ["Files chosen by", f"WinKFP, from {c("<family>" + '.DAT')}", "You"],
    ["Checks", f"HW compatibility ({c('.HWH')}), ZB history ({c('.HIS')}), writes the UIF (VIN, ZB, date)", "None — you can flash software that does not fit the hardware"],
    ["Needs", f"Complete family data and a correct {link('gdaten', 'gdaten')} (KFCONF, INFO.{LANG}, HWNR)", f"Only the files; they must be in {c('DATA⧵DEVELOP')}"],
])}
<h4>Comfort</h4>
{bullets([
    "<b>F2 Choose ZUSB</b> — pick the family and a ZB number from the list.",
    "<b>F3 Update ZUSB</b> — WinKFP reads the current ZB from the ECU and offers the newest successor. You still have to pick the family and integration position first, because WinKFP needs the PABD, P-SGBD and address to talk to the ECU.",
])}
<h4>Expert</h4>
<p>WinKFP remembers one Expert configuration in {link("winkfpt-ini", "Winkfpt.ini")}. BimmerDaten's
{app("winkfp/presets", "💾 Presets")} stores many and loads the one you pick; {app("winkfp/what to flash", "🔎 What to flash")}
gives you the exact values.</p>
{note("Expert mode file dialogs only list files in " + c("NFS⧵DATA⧵DEVELOP") + ". Presets copy the needed 0PA / 0DA files there for you.", "info")}
""",
    keywords=("comfort", "komfort", "expert", "mode", "choose zusb", "update zusb", "f2", "f3"),
    related=("zb-number", "integration-position", "flash-workflow", "pabd"),
)

topic(
    "zb-number",
    "WinKFP: how it works",
    "ZB number (ZUSB)",
    "The 7-digit number of an ECU with a specific software.",
    f"""
<p>A <b>ZB number</b> (Zusammenbau-Nummer, “assembly number”, shown as ZUSB in WinKFP) is a 7-digit BMW part
number for <b>hardware + program + data</b> together, e.g. {c("8510735")}. Flashing a new ZB means putting new
software on the same hardware.</p>
<h4>Where to find the current ZB</h4>
{bullets([
    "WinKFP <b>F3 Update ZUSB</b> reads it from the ECU automatically.",
    f"WinKFP <b>Read UIF</b> (special functions) shows the ZB of the last programming — {link('g-uif', 'UIF')}.",
    "The label on the ECU, or INPA / Tool32 ident.",
])}
<h4>Where ZB numbers are defined</h4>
{table(["File", "Role"], [
    [c("<family>" + ".DAT"), "Every ZB of the family: which HW number it fits and which program / data files it uses."],
    [c("<family>" + ".HIS"), "ZB history: old ZB → new ZB. Following the chain gives the newest software."],
])}
<p>WinKFP's “Choose ZUSB” only shows bare numbers. {app("winkfp/families", "📦 Families")} → ZB numbers shows each ZB with
the software description (chassis, engine, gearbox, kW) read from the flash files.</p>
""",
    keywords=("zb", "zusb", "zusammenbau", "assembly number", "software number"),
    related=("hw-number", "family-dat", "family-his", "comfort-expert"),
)

topic(
    "hw-number",
    "WinKFP: how it works",
    "Hardware (HW) number",
    "The 7-digit number of the ECU box itself.",
    f"""
<p>The <b>HW number</b> identifies the physical ECU without its software, e.g. {c("7806897")}. You find it on
the ECU label or with <b>Read ident</b> (WinKFP) / job {c("IDENT")} (Tool32, INPA).</p>
{table(["File", "What it tells"], [
    [c("gdaten⧵HWNR.DA2"), "HW number → ECU family. Answers “which family do I choose?”"],
    [c("<family>" + ".DAT"), "Which ZB numbers (software) are allowed on this HW."],
    [c("<family>" + ".HWH"), "Groups of HW numbers that are compatible with each other."],
])}
{note("Type the HW number (and the current ZB, if you know it) into " + app("winkfp/what to flash", "🔎 What to flash") + ": it finds the family, the allowed ZBs, the newest one and the exact Expert-mode files.", "tip")}
""",
    keywords=("hw", "hardware number", "hw-nr", "hwnr", "ident", "label"),
    locations=(("{NFS}\\DATA\\gdaten", "HWNR.DA2"),),
    related=("zb-number", "hwnr", "family-hwh"),
)

topic(
    "integration-position",
    "WinKFP: how it works",
    "Integration position and ECU address",
    "Which physical ECU in the car you mean.",
    f"""
<p>The <b>integration position</b> (German “Einbauort”) tells WinKFP which physical ECU you want to flash. It
defines the <b>diagnostic address</b> WinKFP uses to talk to it.</p>
<p>Most ECUs exist once per car, so there is only one position — the engine ECU is always at address
{c("0x12")}. In {c("INFO.GER")} that looks like:</p>
<pre>$AA WB 12 01 DDE71</pre>
<p>({c("WB")} = position code, {c("12")} = address 0x12, {c("DDE71")} = family). DSC / ABS is at {c("0x29")}.</p>
<p>Several positions exist when the same ECU type is fitted more than once: driver / passenger door, left / right
headlight, driver / passenger seat. Same family and software, different addresses.</p>
{note("The list comes from " + c("DATA⧵gdaten⧵INFO." + "<lang>") + " (INFO.ENG with English WinKFP). If that file is missing the list is empty and Comfort mode cannot continue. " + app("winkfp/health", "🩺 Health") + " creates it from INFO.GER.", "warn")}
""",
    keywords=("integration position", "einbauort", "address", "ecu address", "sg_adr", "0x12", "miejsce montazu"),
    related=("info-file", "comfort-expert", "kfconf"),
)

topic(
    "ecu-family",
    "WinKFP: how it works",
    "ECU families and their names",
    "Why a family is called EK924, DDE71 or GKE191.",
    f"""
<p>A <b>family</b> (SG-Familie) is one ECU type in BMW's flash logistics. Each has a folder in
{c("NFS⧵DATA")} and one line in {link("kfconf", "KFCONF")}. The names are internal and BMW does not publish the
scheme; from the files the pattern is:</p>
{table(["Family", "ECU system (from flash files)", "Reading"], [
    [c("DDE504, DDE604, DDE71"), "EDC16C1, EDC16C35, EDC17CP02", "<b>D</b>igitale <b>D</b>iesel-<b>E</b>lektronik + version"],
    [c("MDS42, MDS43, MDS450"), "MS42, MS43, MS45", "<b>M</b>otor (petrol) + Siemens MS version"],
    [c("MSS54"), "MSS54", "M engine S54"],
    [c("MD526"), "M5.2", "Bosch Motronic 5.2"],
    [c("GD20, GKE191, GD8600"), "GS20, GS19.11, GS8.60", "<b>G</b> = gearbox (Getriebe)"],
    [c("EK924, EKB924, EKV946"), "ME9.2 (N42, N40/N45), MEV9.2 (N46)", "ME 9.2 variants — exact letters unknown"],
])}
<p>Because the names are cryptic, {app("winkfp/families", "📦 Families")} shows the chassis, engines and ECU system
read from the flash files. Search there for {c("E46")} or {c("N42")}.</p>
<h4>A family is complete when it has</h4>
{steps([
    f"folder {c('DATA⧵<family>')} with {c('.DAT')}, {c('.HIS')}, {c('.HWH')} and the 0PA / 0DA files,",
    f"its {link('pabd', 'PABD')} in {c('SGDAT')}, named as in KFCONF,",
    f"its P-SGBD in {c('EDIABAS⧵Ecu')}, named as in KFCONF,",
    f"entries in {link('gdaten', 'gdaten')}: KFCONF (both modes), INFO and HWNR (Comfort).",
])}
""",
    keywords=("family", "sg-familie", "ek924", "dde71", "mss54", "naming", "name", "gke"),
    locations=(("{NFS}\\DATA", "*"),),
    related=("kfconf", "family-dat", "pabd", "sp-daten"),
)

topic(
    "pabd",
    "WinKFP: how it works",
    "PABD, P-SGBD and address",
    "The three settings that tell WinKFP how to talk to an ECU.",
    f"""
{table(["Item", "What it is", "Example (ME9.2 / E46)"], [
    ["<b>PABD</b>", f"Programmier-Ablaufbeschreibung — the flash sequence script ({c('SGDAT⧵*.ipo')}). Decides the steps: identify, erase, write, check, write UIF.", c("22EK924.IPO")],
    ["<b>P-SGBD</b>", f"The {link('sgbd', 'SGBD')} with the flash jobs ({c('EDIABAS⧵Ecu⧵*.prg')}). Often shared by many families ({c('08FLASH.prg')}).", c("22EK92.PRG")],
    ["<b>ECU address</b>", f"Diagnostic address (hex) — see {link('integration-position', 'integration position')}.", c("12")],
])}
<p>The leading number of a PABD is its version: {c("07dde71.ipo")} is version 7 of the DDE71 sequence. Use the
version named in KFCONF — or the newest one if KFCONF names a file that does not exist
({app("winkfp/health", "🩺 Health")} fixes this).</p>
{note("Never use a coding file " + c("A_*.ipo") + " as PABD — see " + link("ipo-files", ".ipo files") + ".", "warn")}
""",
    keywords=("pabd", "p-sgbd", "psgbd", "address", "programmier ablaufbeschreibung", "kf_pabd"),
    locations=(("{NFS}\\SGDAT", "*.ipo"),),
    related=("ipo-files", "kfconf", "integration-position", "flash-files"),
)

topic(
    "flash-workflow",
    "WinKFP: how it works",
    "Flashing with WinKFP — step by step",
    "A safe Expert-mode flash using BimmerDaten.",
    f"""
<h4>Before</h4>
{bullets([
    "Connect a <b>battery charger</b> (stable 13–14 V). Low voltage is the main cause of failed flashes.",
    "Use a reliable cable, COM port latency 1 ms, laptop on mains power, sleep mode off.",
    "Close INPA, Tool32 and NCS Expert — only one program may use the interface.",
    f"Run {app('winkfp/health', '🩺 Health')} and fix the reported problems.",
])}
<h4>Find the files</h4>
{steps([
    "Read the HW number and current ZB (WinKFP <b>Read ident</b> / <b>Read UIF</b>).",
    f"Enter them in {app('winkfp/what to flash', '🔎 What to flash')}: you get the target ZB, PABD, P-SGBD, address, 0PA and 0DA.",
    "Click <b>Save as preset</b>, then in 💾 Presets <b>Load into WinKFP</b> (close WinKFP first). Files are copied to DATA⧵DEVELOP.",
])}
<h4>Flash</h4>
{steps([
    "Start WinKFP, ignition on, choose <b>Expert mode</b>. The preset values are filled in.",
    "Press <b>Prog. Program</b> (and then <b>Prog. Data</b> if needed) — only now is something written.",
    "Do not touch anything until WinKFP reports the end. If it fails, flash again — do not switch the ignition off.",
    "Code the ECU afterwards with NCS Expert (" + c("SG_CODIEREN") + ").",
])}
{note("F4 Diagnosis functions are read-only. F3 Special functions include writing functions (e.g. calibration, EWS alignment) — read the description before you use one.", "warn")}
""",
    keywords=("flash", "how to flash", "steps", "battery", "prog program", "prog data", "safe"),
    related=("comfort-expert", "pabd", "flash-files", "errors-common"),
)

# =========================================================================== WinKFP: files

topic(
    "gdaten",
    "WinKFP: files",
    "gdaten folder (global tables)",
    "KFCONF, INFO, HWNR and other tables shared by all families.",
    table(["File", "Purpose", "Format"], [
        [link("kfconf", c("KFCONF??.DA2")), "Family → PABD, P-SGBD, address, data-file prefix, DAT / HIS / HWH names", "fixed-width text, ME lines"],
        [link("info-file", c("INFO.GER / INFO.ENG")), "Integration positions and addresses for Comfort mode", "text, $AA lines"],
        [link("hwnr", c("HWNR.DA2")), "HW number → family", "CSV"],
        [c("Historie.bsu"), "History of boot sector updates (BSU)", "text"],
        [c("SWTconf0.dat"), "Which ECUs use which SWT / FSC sequence", "text"],
        [c("SGIDC.as2, SGIDD.as2"), "ECU identification data", "text"],
        [c("npv.dat, prgifsel.dat"), "Internal WinKFP tables", ""],
    ], [28, 52, 20]) + note(
        "WinKFP converts these files into a cache " + c("DATA\\konv.tmp") + " at every start, so after changing them nothing has to be cleared.", "info"),
    keywords=("gdaten", "global", "kfconf", "info", "hwnr", "konv.tmp", "historie.bsu", "swtconf"),
    locations=(("{NFS}\\DATA\\gdaten", "*"),),
    related=("kfconf", "info-file", "hwnr"),
)

topic(
    "kfconf",
    "WinKFP: files",
    "KFCONF??.DA2",
    "The main table: one line per ECU family.",
    f"""
<p>Every family has one {c("ME")} line in {c("DATA⧵gdaten⧵KFCONF??.DA2")} (fixed column widths):</p>
<pre>ME WB 12 01 DDE71   03DDE71.IPO   00DDE71.PRG   …   DDE71.HIS   DDE71.DAT   A   …   DDE71.HWH</pre>
{table(["Field", "Meaning"], [
    [c("WB 12 01"), f"{link('integration-position', 'Integration position')} code and ECU address (0x12)"],
    [c("DDE71"), "Family"],
    [c("03DDE71.IPO"), f"{link('pabd', 'PABD')} — must exist in SGDAT"],
    [c("00DDE71.PRG"), "P-SGBD — must exist in EDIABAS⧵Ecu"],
    [c("DDE71.HIS / .DAT / .HWH"), f"Logistics files in {c('DATA⧵DDE71')}"],
    [c("A"), f"Prefix letter of the {link('flash-files', 'data files')} (A1234567.0DA)"],
])}
{note("Typical problem: KFCONF is older than SGDAT and names a PABD version that is not installed (e.g. " + c("03DDE71.IPO") + " while SGDAT has " + c("07dde71.ipo") + "). Comfort mode then fails with 1065 and WinKFP error 106. " + app("winkfp/health", "🩺 Health") + " rewrites the line to the newest installed version (with backup).", "warn")}
""",
    keywords=("kfconf", "da2", "me line", "configuration", "1065"),
    locations=(("{NFS}\\DATA\\gdaten", "KFCONF*.DA2"),),
    related=("gdaten", "pabd", "errors-common"),
)

topic(
    "info-file",
    "WinKFP: files",
    "INFO.GER / INFO.ENG",
    "Integration positions shown in Comfort mode.",
    f"""
<p>One {c("$AA")} line per family and position: {c("$AA WB 12 01 DDE71")}. WinKFP reads
{c("INFO." + "<lang>")} where {c("<lang>")} is {c("SPRACHE")} in {link("winkfpt-ini", "Winkfpt.ini")} —
{c("INFO.ENG")} for English.</p>
{note("Many installs only have INFO.GER. With English WinKFP this gives error <b>1020 “file could not be opened … info.eng”</b> at start and an empty integration position list. Copying INFO.GER to INFO.ENG fixes it — the file contains codes and addresses, the German descriptions do not matter. " + app("winkfp/health", "🩺 Health") + " does this with one click.", "warn")}
""",
    keywords=("info.ger", "info.eng", "$aa", "sprache", "1020", "language"),
    locations=(("{NFS}\\DATA\\gdaten", "INFO.*"),),
    related=("integration-position", "winkfpt-ini", "errors-common"),
)

topic(
    "hwnr",
    "WinKFP: files",
    "HWNR.DA2",
    "Which family a hardware number belongs to.",
    f"""
<p>CSV lines {c("HWNR,AT_HWNR,EP_TSNR,SG_TYP")}, grouped by {c(";$SG <family>")}:</p>
<pre>4028612,0000000,0000000,ABS56</pre>
<p>Column 1 is the {link("hw-number", "HW number")}, the last column the family. {app("winkfp/what to flash", "🔎 What to flash")}
uses it to find the family for a HW number.</p>
""",
    keywords=("hwnr", "da2", "hardware", "family lookup"),
    locations=(("{NFS}\\DATA\\gdaten", "HWNR.DA2"),),
    related=("hw-number", "gdaten"),
)

topic(
    "family-dat",
    "WinKFP: files",
    "&lt;family&gt;.DAT",
    "All ZB numbers of a family and their files.",
    f"""
<p>CSV rules: {c("ZB, TYPE, HW, IX, SW-NR, …, CS")}. One line = one allowed combination.</p>
{table(["Column", "Meaning"], [
    [c("ZB"), link("zb-number", "ZB number")],
    [c("HW, IX"), f"{link('hw-number', 'HW number')} and HW index → program file {c('<HW><IX>.0PA')}"],
    [c("SW-NR"), f"Data number → data file {c('<prefix><SW-NR>.0DA')} (prefix from KFCONF). {c('0000000')} = no data file."],
    [c("last columns"), "Internal flags and checksum"],
])}
""",
    keywords=("dat", "family.dat", "zb rules", "sw-nr"),
    related=("flash-files", "zb-number", "family-his"),
)

topic(
    "family-his",
    "WinKFP: files",
    "&lt;family&gt;.HIS",
    "ZB history: which ZB replaces which.",
    f"""
<p>Lines {c("old ZB, new ZB")}. Following the chain from your current ZB gives the newest software, e.g.
{c("8509111 → … → 8510688")}. Comfort's F3 Update ZUSB and {app("winkfp/what to flash", "🔎 What to flash")} use it.</p>
""",
    keywords=("his", "history", "successor", "newest"),
    related=("zb-number", "family-dat"),
)

topic(
    "family-hwh",
    "WinKFP: files",
    "&lt;family&gt;.HWH",
    "Groups of compatible hardware numbers.",
    f"""
<p>Each group lists HW numbers that can run the same software. Comfort mode refuses a ZB that is not meant for the
HW group of the connected ECU. {app("winkfp/families", "📦 Families")} → HW groups shows them.</p>
""",
    keywords=("hwh", "hardware group", "compatible"),
    related=("hw-number", "family-dat"),
)

topic(
    "flash-files",
    "WinKFP: files",
    "Flash files: 0PA, 0DA, 0BA",
    "The program and data that end up in the ECU.",
    f"""
{table(["Extension", "Contents", "Name"], [
    [c(".0PA"), "Program (the ECU's software)", f"{c('<HW-NR><IX>.0PA')}, e.g. {c('7508292A.0PA')}"],
    [c(".0DA"), "Data (maps, calibration)", f"{c('<prefix><SW-NR>.0DA')}, e.g. {c('L7525327.0DA')}"],
    [c(".0BA"), "Additional loadable sequence (NAAB) for some ECUs", "rare"],
])}
<p>They are text files: a header with metadata (ECU system, engine, chassis, gearbox, kW, dates), then the binary
in Intel HEX. BimmerDaten reads the headers to describe each ZB.</p>
<p>In Expert mode the files must be in {c("NFS⧵DATA⧵DEVELOP")}.</p>
""",
    keywords=("0pa", "0da", "0ba", "naab", "program file", "data file", "intel hex", "develop"),
    locations=(("{NFS}\\DATA\\DEVELOP", "*"),),
    related=("family-dat", "pabd", "flash-workflow"),
)

topic(
    "winkfpt-ini",
    "WinKFP: files",
    "Winkfpt.ini",
    "WinKFP settings and the remembered Expert configuration.",
    f"""
{table(["Section / key", "Meaning"], [
    [c("[Einstellungen] SPRACHE=eng"), f"Language — also selects {c('INFO.ENG')}."],
    [c("CabdFormat=IPO"), "Format of PABD files; must match COAPI.INI."],
    [c("KOMFORT_MIT_AIF / EXPERT_MIT_AIF"), f"Write the {link('g-uif', 'UIF')} after flashing in Comfort / Expert mode."],
    [c("API_TRACE / IFH_TRACE"), "Trace levels."],
    [c("[HW-Interface]"), "Interfaces offered in Communication → HW interface."],
    [c("[Expert-Modus-Konfiguration]"), f"{c('KF_PABD, KF_PSGBD, KF_SG_ADR, KF_PROGRAMM_DATEI, KF_DATEN_DATEI')} — the values Expert mode proposes. {app('winkfp/presets', '💾 Presets')} writes this section."],
    [c("WindowPosition"), "Saved by WinKFP on exit — changes every time, harmless."],
])}
""",
    keywords=("winkfpt.ini", "ini", "settings", "kf_pabd", "expert-modus-konfiguration", "sprache", "windowposition"),
    locations=(("{NFS}\\BIN", "Winkfpt.ini"),),
    related=("comfort-expert", "info-file"),
)

topic(
    "coapi-files",
    "WinKFP: files",
    "COAPI.INI and error text files",
    "Settings of the coding / flash API and the official error texts.",
    table(["File", "Meaning"], [
        [c("CFGDAT\\COAPI.INI"), "Settings of COAPI, the library NCS Expert and WinKFP use to run CABD / PABD."],
        [c("CFGDAT\\Coapierr.eng / .ger"), "Official texts of COAPI error codes (1000–4999)."],
        [c("CFGDAT\\Edierror.eng / .ger"), "Official texts of EDIABAS error codes."],
        [c("CFGDAT\\FciConfig.csv"), "WinKFP's interpreted errors (900000+): summaries of an error event."],
    ], [35, 65]),
    keywords=("coapi", "coapierr", "edierror", "fciconfig", "error texts"),
    locations=(("{NFS}\\CFGDAT", "*"),),
    related=("errors-common", "winkfp-logs"),
)

topic(
    "winkfp-logs",
    "WinKFP: files",
    "Logs and result files",
    "ERROR_*.LOG, error1.log and the .OUT files of special functions.",
    f"""
{table(["File", "Contents"], [
    [c("BIN⧵ERROR_<IF>_<unit>.LOG"), "Error log per interface, e.g. ERROR_STDOBD__.LOG. Events separated by ==== lines."],
    [c("BIN⧵error1.log"), "Additional error log."],
    [c("IDENT_*.OUT"), "Result of Read ident (part numbers, HW / SW)."],
    [c("AIF_*.OUT"), f"Result of Read UIF ({link('g-uif', 'UIF')}: VIN, ZB, date of last programming)."],
    [c("REF_*.OUT"), "Reference / ZIF data."],
    [c("INNENTMP_*.OUT"), "Internal temperature."],
])}
<p>{app("winkfp/logs", "🧾 Logs")} groups the log into events and explains each code. An empty .OUT means no ECU answered.</p>
""",
    keywords=("log", "error log", "out", "ident", "aif", "uif", "ref", "error1.log"),
    locations=(("{NFS}\\BIN", "*.LOG"), ("{NFS}\\BIN", "*.OUT")),
    related=("errors-common", "coapi-files"),
)

topic(
    "ctl-batch",
    "WinKFP: files",
    "CTL batch files",
    "WinKFP's batch mode — flashes without asking.",
    f"""
<p>{c("winkfpt.exe -RUN -BATCH=<file>.CTL")} starts WinKFP with a {c("[MULTIFLASH]")} section
({c("MF_PABD, MF_PSGBD, MF_SG_ADR")} …) and <b>flashes immediately, without confirmation</b>.</p>
{note("BimmerDaten deliberately does not use batch mode. Presets only fill in Expert mode; you always press the programming button yourself.", "info")}
""",
    keywords=("ctl", "batch", "multiflash", "-run"),
    related=("comfort-expert",),
)

# =========================================================================== Errors


def _errors_body() -> str:
    try:
        from winkfp_errors import ERROR_TIPS, IFH_TIPS
    except Exception:  # pragma: no cover - module always present in the app
        return "<p>Error tips not available.</p>"
    rows = [
        [f"<b>{code}</b>", escape(tip.title), escape(tip.cause), escape(tip.fix)]
        for code, tip in sorted(ERROR_TIPS.items())
    ]
    ifh_rows = [
        [f"<b>IFH-{code}</b>", escape(tip.title), escape(tip.cause), escape(tip.fix)]
        for code, tip in sorted(IFH_TIPS.items())
    ]
    return (
        f"<p>Codes 1000–4999 come from COAPI (the flash / coding library), {c('IFH-xxxx')} from the EDIABAS "
        f"interface, 900000+ are WinKFP's summaries. WinKFP's own message “Error 106” only says that programming "
        f"could not start — the real cause is in the log. {app('winkfp/logs', '🧾 Logs')} shows these tips next to each event.</p>"
        "<h4>COAPI codes</h4>"
        + table(["Code", "Meaning", "Cause", "What to do"], rows, [8, 22, 35, 35])
        + '<h4><a name="ifh"></a>Interface errors (IFH)</h4>'
        + table(["Code", "Meaning", "Cause", "What to do"], ifh_rows, [10, 22, 34, 34])
    )


topic(
    "errors-common",
    "Errors & troubleshooting",
    "WinKFP / COAPI error codes",
    "What the numbers in WinKFP errors mean and how to fix them.",
    _errors_body(),
    keywords=("error", "1020", "1063", "1065", "2000", "2020", "3000", "4204", "106", "coapi", "fehler"),
    related=("errors-ifh", "winkfp-logs"),
)

topic(
    "errors-ifh",
    "Errors & troubleshooting",
    "No connection to the car",
    "IFH-0018, IFH-0009 and similar interface problems.",
    f"""
{steps([
    "Cable plugged into the car and PC, ignition on (position 2), battery charger connected.",
    f"Device Manager → Ports: the K+DCAN cable's COM port matches {c('OBD.INI')} (usually COM1), latency 1 ms.",
    f"{link('ediabas-ini', 'EDIABAS.INI')}: {c('Interface = STD:OBD')}.",
    "Only one program uses the interface — close INPA, Tool32, NCS Expert, other diagnostic apps.",
    "Test in INPA first: if INPA reads the car, the cable and EDIABAS are fine.",
])}
{table(["Message", "Meaning"], [
    [c("IFH-0018"), "Interface could not be initialised — cable / COM port / driver. Nothing was sent to the ECU."],
    [c("IFH-0009"), "Interface works but the ECU does not answer — ignition, address, wrong bus."],
    [c("IFH-0003 / IFH-0010"), "Unstable connection (PC ↔ cable / cable ↔ car)."],
])}
""",
    keywords=("ifh", "ifh-0018", "ifh-0009", "no connection", "cable", "com port", "k+dcan", "interface"),
    related=("ediabas-ini", "errors-common"),
)

topic(
    "comfort-not-working",
    "Errors & troubleshooting",
    "Comfort mode shows nothing / error 106",
    "Checklist when Comfort mode cannot find the ECU or files.",
    f"""
{steps([
    f"Integration position list empty → {c('INFO.ENG')} missing ({link('info-file', 'INFO file')}).",
    f"Error 1065 / 106 after choosing a family → KFCONF names a PABD version that is not installed ({link('kfconf', 'KFCONF')}).",
    f"Family not in the list → its {c('DATA')} folder is missing; maybe still in a {c('DATA_…')} backup ({link('sp-daten', 'SP-Daten')}).",
    "Error 3000 → the ZB is not in any installed family.",
    f"Error 4204 → a 0PA / 0DA file from {c("<family>" + '.DAT')} is missing.",
])}
{note(app("winkfp/health", "🩺 Health") + " checks all of these at once and offers fixes with backup.", "tip")}
""",
    keywords=("comfort", "106", "1065", "empty list", "not working", "family missing"),
    related=("kfconf", "info-file", "ecu-family"),
)

# =========================================================================== Using BimmerDaten

topic(
    "bd-winkfp",
    "Using BimmerDaten",
    "The WinKFP tab",
    "What each WinKFP sub-tab does.",
    table(["Sub-tab", "Use it to"], [
        [app("winkfp/health", "🩺 Health"), "Check the install; one-click fixes (INFO.ENG, KFCONF) with backup and undo."],
        [app("winkfp/updates", "🔄 Updates"), "See what an SP-Daten update changed; compare with backup folders."],
        [app("winkfp/families", "📦 Families"), "Browse ECU families with chassis / engine / system; ZB table; restore families from backups."],
        [app("winkfp/what to flash", "🔎 What to flash"), "HW number (+ current ZB) → newest ZB and the exact Expert-mode values."],
        [app("winkfp/sgdat", "🗂 SGDAT"), "Every .ipo labelled as flash, coding or activation codes."],
        [app("winkfp/logs", "🧾 Logs"), "Error logs explained; IDENT / UIF / REF result files."],
        [app("winkfp/presets", "💾 Presets"), "Named Expert configurations loaded into Winkfpt.ini."],
        [app("winkfp/installation", "⚙️ Installation"), "Paths, versions and installation summary."],
    ], [25, 75]),
    keywords=("winkfp tab", "health", "updates", "families", "presets", "sgdat", "logs"),
    related=("winkfp", "flash-workflow"),
)

topic(
    "bd-coding",
    "Using BimmerDaten",
    "The Coding and SA Options tabs",
    "Editing NCS coding offline.",
    f"""
{steps([
    f"Read the ECU in NCS Expert ({c('CODIERDATEN_LESEN')}).",
    f"{app('coding', '⚙️ Coding')} → <b>Load TRC</b>; choose model and module (or <b>Detect module</b>).",
    "Change values in the table — only valid values are offered; ★ marks favourites.",
    f"<b>Export .MAN</b> → run {c('SG_CODIEREN')} in NCS Expert.",
])}
<p>{app("sa", "🔧 SA Options")} decodes the car's vehicle order: which SA codes it has and what they mean.</p>
""",
    keywords=("coding tab", "trc", "man", "export", "sa options", "preset"),
    related=("ncs-workflow", "fsw-psw"),
)

topic(
    "bd-diagnosis",
    "Using BimmerDaten",
    "The Diagnosis tab",
    "Browsing SGBD files without a car.",
    f"""
{bullets([
    "<b>File → Open .PRG</b> (Ctrl+O) opens any SGBD from EDIABAS⧵Ecu.",
    "<b>💼 Jobs</b>: every job with description, arguments, results; translated from German.",
    "<b>📋 Tables</b>: fault texts, live value definitions, …",
    "<b>🚗 Models</b>: INPA's car / ECU menus with the SGBD each one uses.",
    "P-SGBD links in the WinKFP tab open here too.",
])}
""",
    keywords=("diagnosis tab", "prg", "jobs", "tables", "models", "disassembly"),
    related=("sgbd", "job"),
)

topic(
    "bimmerdaten-data",
    "Using BimmerDaten",
    "BimmerDaten's own files",
    "Where BimmerDaten keeps its database, backups and snapshots.",
    table(["Path in %LOCALAPPDATA%\\BimmerDaten", "Contents"], [
        [c("database.db"), "Translations, coding presets, favourites, coding history."],
        [c("WinKFP_backups\\<time>"), "Copies of WinKFP files made before every fix, with manifest.json — used by Restore backup."],
        [c("WinKFP_snapshots"), "Saved states of the WinKFP installation (Updates tab baseline)."],
        [c("WinKFP_cache"), "Cached flash file headers (faster Families tab)."],
        [c("winkfp_presets.json"), "Expert-mode presets."],
        [c("winkfp_paths.json"), "Paths to NFS and EDIABAS\\Ecu."],
    ], [40, 60]),
    keywords=("appdata", "backup", "snapshot", "database", "cache", "presets", "config"),
    locations=(("{APPDATA}", "*"),),
    related=("bimmerdaten",),
)

# =========================================================================== Glossary

_GLOSSARY = [
    ("g-fa", "FA (vehicle order)", "Fahrzeugauftrag — the car's build specification.",
     "<p><b>FA</b> (Fahrzeugauftrag, vehicle order) lists the type key, SA codes, paint and upholstery of the car. "
     "It is stored in several ECUs (e.g. CAS, KOMBI). NCS Expert reads it (FA.TRC) and codes ECUs to match it. "
     "Newer E-series and all F-series cars use the FA; older ones use the " + link("g-zcs", "ZCS") + ".</p>",
     ("fa", "fahrzeugauftrag", "vehicle order", "vo")),
    ("g-zcs", "ZCS (central coding key)", "Zentralcodierschlüssel — the older form of the vehicle order.",
     "<p><b>ZCS</b> (Zentralcodierschlüssel) is a set of three codes (GM, SA, VN) stored in the EWS / instrument cluster "
     "of older cars (E36, E38, E39, early E46, E53). It encodes the equipment like the " + link("g-fa", "FA") + " does on newer cars.</p>",
     ("zcs", "gm", "vn", "zentralcodierschluessel")),
    ("g-sa", "SA code", "Sonderausstattung — a factory option.",
     "<p>A 3-character code for a factory option, e.g. 534 = automatic air conditioning. Part of the FA / ZCS. "
     + app("sa", "SA Options") + " lists and explains them.</p>",
     ("sa", "sonderausstattung", "option code")),
    ("g-vin", "VIN / FGNR", "Vehicle identification number.",
     "<p>17 characters; BMW tools often use the last 7 (FGNR, Fahrgestellnummer). Stored in many ECUs and written to the UIF when flashing.</p>",
     ("vin", "fgnr", "fahrgestellnummer", "chassis number")),
    ("g-uif", "UIF / AIF", "User information field written after flashing.",
     "<p>The <b>UIF</b> (AIF, Anwender-Informations-Feld) is a small record the ECU keeps of each programming: VIN, ZB, date, "
     "workshop. WinKFP writes it after flashing (Comfort mode; Expert if enabled) and <b>Read UIF</b> shows it.</p>",
     ("uif", "aif", "anwender informations feld", "read uif")),
    ("g-coding-index", "Coding index", "Which coding data file version an ECU needs.",
     "<p>Each ECU reports a coding index; NCS Expert uses the matching " + c("<module>.Cxx") + " file (xx = index, hex). "
     "After flashing new software the index can change.</p>",
     ("coding index", "cxx", "codierindex")),
    ("g-best", "BEST/1, BEST/2", "The language jobs in SGBD files are written in.",
     "<p>SGBD jobs are written in BEST/2 and compiled into BEST/1 bytecode, which EDIABAS executes. BimmerDaten's Disassembly tab shows it.</p>",
     ("best", "best/1", "best/2", "bytecode", "disassembly")),
    ("g-ds2-kwp", "DS2, KWP2000, UDS", "Diagnostic protocols.",
     "<p><b>DS2</b>: BMW protocol of older cars (K-line). <b>KWP2000</b>: standard protocol of later E-series. "
     "<b>UDS</b>: F-series and newer. The SGBD hides the protocol from the program.</p>",
     ("ds2", "kwp2000", "kwp", "uds", "protocol", "k-line", "d-can")),
    ("g-swt-fsc", "SWT / FSC", "Activation codes for ECU functions.",
     "<p>An <b>FSC</b> (Freischaltcode) is a signed code from BMW that unlocks a function or data in one ECU for one VIN "
     "(e.g. navigation maps). <b>SWT</b> is the process of storing such codes and certificates. Their .ipo files are not used for coding or flashing.</p>",
     ("swt", "fsc", "freischaltcode", "activation")),
    ("g-ecu", "ECU / SG", "Electronic control unit.",
     "<p>Any control module in the car (engine, gearbox, body, lights …). German: SG, Steuergerät — hence SGBD, SGDAT.</p>",
     ("ecu", "sg", "steuergeraet", "module")),
    ("g-ews", "EWS / CAS", "Immobiliser.",
     "<p><b>EWS</b> (Elektronische Wegfahrsperre) — immobiliser of older cars; <b>CAS</b> (Car Access System) on newer ones. "
     "The engine ECU must be synchronised with it after replacement (EWS alignment).</p>",
     ("ews", "cas", "immobiliser", "immobilizer", "wegfahrsperre", "abgleich")),
    ("g-kdcan", "K+DCAN cable", "The usual USB diagnostic cable.",
     "<p>USB-to-OBD cable for E-series cars (K-line and D-CAN). Appears as a COM port; EDIABAS uses it with " + c("Interface = STD:OBD") + ".</p>",
     ("k+dcan", "kdcan", "cable", "usb", "obd")),
]

for _id, _title, _summary, _body, _kw in _GLOSSARY:
    topic(_id, "Glossary", _title, _summary, _body, keywords=_kw)


TOPICS_BY_ID: dict[str, DocTopic] = {t.id: t for t in TOPICS}
