<h1 align="center">BimmerDaten</h1>
<p align="center"><em>Expert for EDIABAS and NCS</em></p>
<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-GPL--3.0-blue"/></a>
  <img src="https://img.shields.io/badge/Python-3.10%2B-blue"/>
  <img src="https://img.shields.io/badge/Version-1.0-green"/>
  <img src="https://img.shields.io/badge/Platform-Windows-lightgrey"/>
  <img src="https://img.shields.io/badge/BMW%20Standard%20Tools-required-orange"/>
</p>

## Overview

BimmerDaten is a Windows GUI tool for viewing, editing, and decoding BMW NCS Expert coding files and EDIABAS job files. It simplifies BMW ECU coding by replacing the cryptic NCS Expert and NCS Dummy workflow with a clean, modern interface. The application is built with Python and PyQt6.

## Features

- FSW/PSW TRC viewer and editor with change tracking.
- NCS DATEN parser for .Cxx modules and option/value mapping.
- Automatic module detection from loaded TRC content.
- Translation support using NCS Dummy Translations.csv.
- TRC and MAN export flow with confirmation and notes.
- Coding history storage, comparison, and filtering.
- PDF export of coding comparison/history reports.
- EDIABAS .PRG decoder with jobs, tables, and disassembly views.
- INPA model parser with script-to-PRG discovery.
- FA/SA decoder for AT.000 and fa.trc data.

## Requirements

- Windows (32-bit EDIABAS compatibility layer)
- Python 3.10+
- BMW Standard Tools (NCS Expert, EDIABAS)
- NCS Dummy (optional but recommended; required for parameter translations)

Point BimmerDaten to your local Translations.csv in Settings.

Download NCS Dummy:
https://forums.bimmerforums.com/forum/showthread.php?t=1553779

## Installation

```bash
pip install -r requirements.txt
python main_window.py
```

## Usage

1. Open or select your BMW model/module data.
2. Load a TRC file.
3. Review and edit coding options.
4. Export changes to MAN/TRC and apply them in your standard BMW workflow.

## Disclaimer

This software is provided as is, without warranty of any kind.
Incorrect ECU coding can damage your vehicle. Always back up your coding data before making changes.
The author is not responsible for any damage caused by the use of this software.

## Contributing

Issues and bug reports are welcome via GitHub Issues.
Pull requests are not accepted at this time.

## License

GPL-3.0 - see LICENSE.
Translations loaded from NCS Dummy's Translations.csv are copyright (c) REVTOR and are not bundled with this project.

## 🇵🇱 Dla polskiej społeczności BMW

BimmerDaten to narzędzie do przeglądania i edycji plików kodowania NCS Expert oraz plików jobów EDIABAS.
Zostało stworzone jako czytelna i nowoczesna alternatywa dla NCS Dummy, z dodatkowymi funkcjami takimi jak eksport PDF, dekoder kodów FA i historia kodowania.
Tłumaczenia parametrów: Program obsługuje plik Translations.csv z NCS Dummy - wskaż jego lokalizację w Ustawieniach.
Projekt jest open source na licencji GPL-3.0. Zgłoszenia błędów mile widziane przez GitHub Issues.