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

BimmerDaten is a Windows GUI tool for viewing, editing, and decoding BMW NCS Expert coding files and EDIABAS job files. It simplifies BMW ECU (modules) coding by replacing the cryptic NCS Expert workflow with a clean, modern interface. The application is built with Python and PyQt6.

## What it can do ?

- Simplifies coding ECU (FSW/PSW.TRC fles) witch change tracking.
- User friendly viewer for jobs used in Tool32 and INPA.
- Automatic module detection from loaded TRC content.
- Translation for coding names and parameters (NCS), jobs (Tool32/INPA) using offline DB (failover to online transaltions) and FA codes (online translations). Online transaltions that have been done in past are saved in DB.
- Coding history storage, comparison, and filtering.
- PDF export of coding comparison/history reports.
- INPA model parser with script-to-PRG discovery.
- FA/SA decoder for AT.000 and fa.trc data.

## Requirements

- Windows 10
- Python 3.10+
- BMW Standard Tools (NCS Expert, EDIABAS, Tool32 etc. like Mike's Easy BMW Tools)
- NCS Dummy (optional but recommended; required for parameter translations in modules coding (NCS))

Point BimmerDaten to your local Translations.csv in Settings.

## Installation

```bash
pip install -r requirements.txt
python main_window.py
```

## Usage

### A manual for BimmerDaten is available in this repo /help/MANUAL_EN.pdf
### The manual is still in development !

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