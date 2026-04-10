# Getting Started

## What is BimmerDaten?

BimmerDaten is a Windows desktop application for BMW enthusiasts and technicians working with BMW diagnostic and coding files. It provides a modern interface for two core tasks:

- **Exploring EDIABAS files** — browse jobs, live data parameters, tables and disassembly inside `.prg` ECU files
- **Editing coding files** — load, edit and export NCS Expert coding files (`.trc`) with full change tracking

BimmerDaten works **alongside** BMW Standard Tools — it does not replace them. You still need EDIABAS and NCS Expert installed to have the source files the application reads.

---

## Requirements

| Component | Required | Notes |
|---|---|---|
| Windows 10 or newer | ✅ | 64-bit recommended |
| Python 3.10+ | ✅ | [python.org](https://www.python.org/downloads/) |
| BMW Standard Tools | ✅ | EDIABAS, NCS Expert, Tool32 — e.g. via Mike's Easy BMW Tools |
| NCS Dummy | ⚠️ Optional | Required for coding parameter translations (Translations.csv © REVTOR) |

> **EDIABAS default path:** `C:\EDIABAS\Ecu\`
> BimmerDaten expects ECU files here. If your installation is different, you can change the path in the application.

---

## Installation

```bash
# 1. Clone the repository
git clone https://github.com/zer02dev/BimmerDaten.git
cd BimmerDaten

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run
python main_window.py
```

No build step, no installer required.

---

## First launch

When you start BimmerDaten for the first time, a **Startup Guard** runs automatically. It checks whether required paths (EDIABAS, NCS Expert) are correctly configured on your system. If any path is missing or incorrect, a dialog will appear with instructions.

### Setting up paths

Click **Change path** in the Coding tab left sidebar to configure:

- **EDIABAS path** — folder containing `.prg` ECU files (default: `C:\EDIABAS\Ecu\`)
- **NCS Expert path** — NCS Expert working directory (default: `C:\NCSEXPER\WORK\`)
- **Translations.csv** — path to NCS Dummy's translation file (optional)

Once paths are configured, they are saved and remembered between sessions.

---

## Interface overview

BimmerDaten has three main tabs at the top:

| Tab | Purpose |
|---|---|
| 🔧 **Diagnosis** | Browse EDIABAS `.prg` files — jobs, tables, models |
| ⚙️ **Coding** | Load and edit NCS Expert coding files (`.trc`) |
| 🔧 **SA Options** | Decode FA/SA option codes from your vehicle order |

Each tab is independent — you can work in all three during the same session.
