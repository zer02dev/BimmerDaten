<h1 align="center">BimmerDaten</h1>
<p align="center"><em>A modern companion for BMW EDIABAS, NCS Expert and WinKFP</em></p>
<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-GPL--3.0-blue"/></a>
  <img src="https://img.shields.io/badge/Python-3.10%2B-blue"/>
  <img src="https://img.shields.io/badge/Version-1.1.0-green"/>
  <img src="https://img.shields.io/badge/Platform-Windows-lightgrey"/>
  <img src="https://img.shields.io/badge/BMW%20Standard%20Tools-required-orange"/>
</p>

---

## What is it?

BimmerDaten is a Windows desktop application for enthusiasts and technicians working with BMW diagnostic and coding files. It provides a clean, modern interface for exploring EDIABAS job files (`.prg`), editing NCS Expert coding files (`.trc`) and making sense of WinKFP flash programming — tasks that traditionally required using old, cryptic BMW tools with no real visibility into what you were actually changing.

If you have ever used NCS Expert, WinKFP or Tool32 and thought *"there must be a better way to see what this module actually does"* — this is that better way.

---

## Why not NCS Dummy or Tool32?

| | NCS Dummy | Tool32 | BimmerDaten |
|---|---|---|---|
| Coding TRC files | ✅ | ❌ | ✅ |
| Coding parameter translations (NCS) | ✅ ¹ | ❌ | ✅ ¹ |
| View EDIABAS jobs | ❌ | ✅ | ✅ |
| Job parameters & descriptions | ❌ | ✅ | ✅ |
| Job / EDIABAS translations (DE→EN/PL) | ❌ | ❌ | ✅ ² |
| Live data table viewer | ❌ | partial | ✅ |
| Change tracking & history | ❌ | ❌ | ✅ |
| FA/SA decoder | ❌ | ❌ | ✅ |
| PDF export | ❌ | ❌ | ✅ |
| WinKFP installation check & fixes | ❌ | ❌ | ✅ |
| "What to flash" assistant (HW / ZB number) | ❌ | ❌ | ✅ |
| WinKFP error log explanations | ❌ | ❌ | ✅ |
| Modern UI | ❌ | ❌ | ✅ |

> ¹ Coding parameter translations (module options, their descriptions and interdependencies)
> are sourced from NCS Dummy's `Translations.csv` © REVTOR. BimmerDaten reads this file
> from your local NCS Dummy installation — it is never bundled with this project.
> Both tools share the same data source here; BimmerDaten does not improve on it.
>
> ² Job descriptions and EDIABAS-related translations are BimmerDaten's own offline DB
> with automatic online fallback. This is entirely independent of NCS Dummy.

BimmerDaten is not a replacement for BMW Standard Tools — it works alongside them. You still need EDIABAS, NCS Expert and (for flashing) WinKFP installed. BimmerDaten reads the same files and gives you a much better view of their contents.

---

## Features

### EDIABAS Job Viewer
- Browse all jobs inside any `.prg` ECU file
- View job input arguments (ARG), output results (RESULT) with types and descriptions
- Live data parameter table (BETRIEBSWTAB) with byte positions, scaling factors, and DS2 telegram breakdown
- Per-job table viewer — see which tables a job uses and browse their contents
- Full disassembly view of BEST/1 bytecode
- Automatic job categorization (fault memory, live data, coding, identification, etc.)

### NCS Expert Coding
- Load and edit FSW/PSW coding files (`.trc`) then export it to .MAN file to upload it do your Bimmer
- Human-readable parameter names via NCS Dummy's `Translations.csv`
- Automatic module detection from TRC content
- Change tracking — see exactly what you changed vs. the original
- Coding history with comparison and filtering
- PDF export of coding reports
- Coding presets — save, apply and share named coding configurations

### WinKFP Flash Helper *(new in 1.1.0)*
WinKFP is powerful but opaque. BimmerDaten reads the same files WinKFP uses (`C:\EC-APPS\NFS`) and explains them — it never flashes anything itself.
- **🩺 Health** — checks the installation (`INFO.<language>`, KFCONF ↔ SGDAT ↔ EDIABAS\Ecu ↔ DATA, missing flash files) and fixes common problems with one click, e.g. the missing `INFO.ENG` that leaves Comfort mode without integration positions, or KFCONF pointing to PABD versions that are not installed
- **🔄 Updates** — snapshots the installation and shows what an SP-Daten update changed: families added / removed, SGDAT and EDIABAS changes, comparison with update backup folders (`DATA_…`, `SGDAT_…`, `ECU_…`)
- **📦 Families** — every ECU family with status, vehicles, engines and ECU system, ZB numbers with software descriptions, ZB history and compatible hardware; restore families that an update dropped from `DATA`
- **🔎 What to flash** — enter the ECU's HW number (and optionally the current ZB from *Read UIF*) and get the newest matching ZB plus the exact PABD, P-SGBD, ECU address and files for Expert and Comfort mode
- **🗂 SGDAT** — every `.ipo` classified as flash sequence (PABD), NCS coding sequence (CABD) or activation codes (SWT/FSC), with job list — and a warning before you pick a coding file as PABD (WinKFP error 1063)
- **🧾 Logs** — WinKFP error logs grouped into events, with plain-language cause and fix for COAPI / EDIABAS / IFH errors, plus the IDENT / UIF / REF result files
- **💾 Presets** — named Expert-mode configurations; *Load into WinKFP* writes `WINKFPT.INI` and copies the flash files to `DATA\DEVELOP` (the only folder Expert mode lists)
- Every change to the WinKFP installation is previewed, backed up to `%LOCALAPPDATA%\BimmerDaten\WinKFP_backups` and can be undone

### Translations
- **EDIABAS jobs** — own offline DB (DE → EN, PL) with automatic online fallback; online results are saved locally for future use
- **Coding parameters (NCS)** — reads NCS Dummy's `Translations.csv` (© REVTOR) from your local installation; includes full parameter context and interdependencies authored by REVTOR
- **FA/SA option codes** — online lookup, results cached locally

### Other
- INPA model parser with script-to-PRG file discovery
- FA/SA decoder for `AT.000` and `fa.trc` files
- SQLite-based local database — no cloud, no account required
- Retro Windows look with modern, readable fonts

---

## Requirements

- **Windows 10** or newer
- **Python 3.10+** — [python.org](https://www.python.org/downloads/)
- **BMW Standard Tools** — EDIABAS, NCS Expert, Tool32  
  *(e.g. via Mike's Easy BMW Tools package)*
- **WinKFP / NFS** *(optional)* — for the WinKFP tab; expected at `C:\EC-APPS\NFS` (path can be changed in WinKFP → Installation)
- **NCS Dummy** *(optional but recommended)* — required for parameter name translations in the coding module. Point BimmerDaten to your local `Translations.csv` in Settings.

> BMW Standard Tools install EDIABAS to `C:\EDIABAS\` by default.
> BimmerDaten expects ECU files at `C:\EDIABAS\Ecu\`.

---

## Installation

### Option 1 — Download (recommended)

Go to the [**Releases**](https://github.com/zer02dev/BimmerDaten/releases) page and download the latest `.exe`. No Python, no dependencies — just run it.

### Option 2 — Run from source

```bash
# 1. Clone the repository
git clone https://github.com/zer02dev/BimmerDaten
cd BimmerDaten

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run
python main_window.py
```

Requires Python 3.10+.

---

## Quick Start

1. **Open a PRG file** — File → Open PRG → navigate to `C:\EDIABAS\Ecu\` and pick any `.prg` file
2. **Browse jobs** — the left panel lists all jobs in the file; use the search bar to filter
3. **Inspect a job** — click any job to see its description, arguments, results, and live data parameters in the right panel
4. **Open a TRC file** — File → Open TRC → load your coding file to view and edit module parameters
5. **WinKFP** — open the ⚡ WinKFP tab: *Health* checks your installation, *What to flash* tells you which software fits your ECU

---

## Screenshots

![jobs main screen](assets/screenshots/BimmerDaten_jobs_main.png)
![jobs params screen](assets/screenshots/BimmerDaten_jobs_params.png)
![jobs selector model](assets/screenshots/BimmerDaten_jobs_selector.png)
![jobs tables screen](assets/screenshots/BimmerDaten_jobs_tables.png)
![NCS coding screen main](assets/screenshots/BimmerDaten_NCS_coding_main.png)
![sa/fa codes all](assets/screenshots/BimmerDaten_SA_codes_all.png)
![sa/fa codes only car](assets/screenshots/BimmerDaten_SA_codes_your_car.png)
![WinKFP health check](assets/screenshots/BimmerDaten_WinKFP_health.png)
![WinKFP families](assets/screenshots/BimmerDaten_WinKFP_families.png)
![WinKFP what to flash](assets/screenshots/BimmerDaten_WinKFP_what_to_flash.png)
![WinKFP SGDAT browser](assets/screenshots/BimmerDaten_WinKFP_sgdat.png)
---

## Supported File Types

| Extension | What it is | Used for |
|---|---|---|
| `.prg` | EDIABAS ECU program file | Job viewer, live data, disassembly |
| `.trc` | NCS Expert coding file (FSW/PSW) | Coding editor, change tracking |
| `fa.trc` / `AT.000` | Vehicle order / FA file | FA/SA decoder |
| `Translations.csv` | NCS Dummy translation database | Parameter name translations |
| `KFCONF??.DA2`, `INFO.*`, `HWNR.DA2` | WinKFP global logistics (`DATA\gdaten`) | Health check, families, assistant |
| `<family>.DAT` / `.HIS` / `.HWH` | WinKFP ECU family logistics (ZB rules, ZB history, HW groups) | Families, What to flash |
| `.0PA` / `.0DA` / `.0BA` | WinKFP program / data / NAAB flash files | Vehicle & software descriptions |
| `.ipo` (SGDAT) | Compiled PABD / CABD sequences | SGDAT browser |
| `ERROR_*.LOG`, `*.OUT` | WinKFP error logs and result files | Logs |

---

## FAQ

**Do I need BMW Standard Tools installed?**  
Yes. BimmerDaten reads the files that come with EDIABAS and NCS Expert — it does not bundle them. You need a working installation of BMW Standard Tools.

**Will this modify my ECU directly?**  
No. BimmerDaten is a file viewer and editor for local coding files. It does not connect to your car. To apply changes you still use NCS Expert as usual.

**Does BimmerDaten flash ECUs?**  
No. The WinKFP tab only reads WinKFP's files, explains them and can fix or prepare the WinKFP installation (always with a backup). Flashing is still done in WinKFP, and only when you press the programming button there.

**WinKFP Comfort mode shows no integration positions / error 1020 at start-up.**  
Your language is English (`SPRACHE=eng`) but `DATA\gdaten\INFO.ENG` is missing. Open WinKFP → Health in BimmerDaten and apply the fix.

**My job shows "No live data parameters" — why?**  
Not all jobs read live data. Jobs that perform actions (coding, resets, adaptations) don't use BETRIEBSWTAB. The message is expected for those jobs.

**The translation shows German text even though I selected English.**  
The offline DB does not have a translation for that entry yet. BimmerDaten will attempt an online translation automatically — this requires an internet connection on first use.

**Can I use this on a non-BMW vehicle?**  
BimmerDaten is built specifically for BMW/MINI EDIABAS files and NCS Expert coding. Other brands are not supported.

---

## Disclaimer

This software is provided as-is, without warranty of any kind.

**Incorrect ECU coding or flashing can cause serious damage to your vehicle.** Flashing the wrong software can make an ECU unusable — always connect a battery charger and double-check the ZB number before programming. Always back up your coding data before making any changes. The author is not responsible for any damage to your vehicle, ECU, or any other component resulting from the use of this software.

When in doubt — don't code.

---

## Community Presets

Have a useful coding preset? Share it with the community via 
[GitHub Discusions](../../discussions/3) — attach an exported `.csv` file 
from DB Browser and describe what it does. 
The best presets will be added to the official database.


## Contributing and Issues

Bug reports and feature requests are welcome via [GitHub Issues](../../issues).

If you encounter any issue, please attach the log file from `%LOCALAPPDATA%\BimmerDaten\Logs\` to your report.

Pull requests are not accepted at this time.

---

## License

GPL-3.0 — see [LICENSE](LICENSE).

Translations loaded from NCS Dummy's `Translations.csv` are copyright © REVTOR and are not bundled with this project. BimmerDaten reads this file from the user's local NCS Dummy installation only.

---

## 🇵🇱 Dla polskiej społeczności BMW

BimmerDaten to narzędzie dla entuzjastów i techników pracujących z plikami diagnostycznymi, kodowania i flashowania BMW. Umożliwia przeglądanie plików jobów EDIABAS (`.prg`), edycję plików kodowania NCS Expert (`.trc`) oraz zrozumienie i przygotowanie flashowania w WinKFP — w czytelnym interfejsie.

**Co oferuje:**
- Przeglądarka jobów EDIABAS z opisami parametrów wejściowych i wynikowych
- Edytor kodowania TRC z śledzeniem zmian i historią kodowania
- Tłumaczenia jobów EDIABAS (DE → EN, PL) z własnej bazy offline + fallback online
- Tłumaczenia parametrów kodowania NCS z pliku `Translations.csv` NCS Dummy (© REVTOR) — wymagana lokalna instalacja NCS Dummy
- Dekoder kodów FA/SA z plików `AT.000` i `fa.trc`
- Eksport raportów kodowania do PDF
- **Pomocnik WinKFP (nowość w 1.1.0)** — sprawdzanie i naprawa instalacji WinKFP, wykrywanie zmian po aktualizacji SP-Daten, lista rodzin sterowników z pojazdami i silnikami, asystent „co wgrać” (numer HW / ZB → najnowszy ZB i gotowe ustawienia trybu Expert), przeglądarka SGDAT, wyjaśnienia błędów z logów i presety trybu Expert

**Wymagania:** BMW Standard Tools (EDIABAS, NCS Expert, opcjonalnie WinKFP), Python 3.10+, opcjonalnie NCS Dummy dla tłumaczeń parametrów kodowania.

Projekt jest open source na licencji GPL-3.0. Błędy i sugestie zgłaszaj przez GitHub Issues — każde zgłoszenie jest mile widziane.

> **Uwaga:** Nieprawidłowe kodowanie lub flashowanie modułów może uszkodzić pojazd. Zawsze rób kopię zapasową danych kodowania przed wprowadzeniem jakichkolwiek zmian.