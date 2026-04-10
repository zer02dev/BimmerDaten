# FAQ & Troubleshooting

---

## General

### Does BimmerDaten connect to my car?

No. BimmerDaten is an **offline file editor and viewer**. It reads and writes files on your PC only. To actually write coding changes to your vehicle, you still use NCS Expert as usual.

### What BMW models are supported?

BimmerDaten supports any model for which you have:
- EDIABAS `.prg` files (for Diagnosis)
- NCS Expert DATEN files (for Coding and SA Options)

This covers most models from E30 to F-series and beyond, depending on your BMW Standard Tools installation.

### Do I need an internet connection?

No, for basic use. An internet connection is only used to fetch English translations for SA codes and EDIABAS job descriptions that are not yet in the local database. Once translated, everything is cached locally.

---

## Installation

### BimmerDaten won't start — missing module error

Make sure all dependencies are installed:

```bash
pip install -r requirements.txt
```

If you see an error about `deep_translator` or `PyQt6`, install them individually:

```bash
pip install PyQt6 deep-translator
```

### The Startup Guard shows path errors

BimmerDaten checks for EDIABAS and NCS Expert on first launch. If your tools are installed in non-default locations, configure the paths:

1. Go to the **Coding** tab
2. Click **Change path** in the left sidebar
3. Set the correct paths for EDIABAS, NCS Expert, and optionally Translations.csv

---

## Coding

### The Value dropdown is greyed out / not editable

The value dropdown is only active when a **module** is selected. Either:
- Select the module manually from the Module dropdown, or
- Click **🔍 Detect module** to auto-detect it from the loaded TRC file

### Detect module shows a low match percentage

A match below ~60% usually means:
- The wrong model is selected — double-check the Model dropdown
- The TRC file is from a different module variant than what is in the database
- The module definition is missing from the database

You can still manually select the module from the dropdown even with a low match.

### My changes aren't saved after closing

BimmerDaten does not auto-save. To preserve changes you must **export** them:
- **Export .MAN** — writes `FSW_PSW.MAN` for NCS Expert to apply
- **Export .TRC** — saves a complete snapshot file

### The MAN file prompt appears every time I close

This is by design. If `FSW_PSW.MAN` is not empty when you close BimmerDaten, the app asks whether to clear it. BMW best practice is to keep the MAN file empty when not actively coding — this prevents NCS Expert from accidentally applying old changes on its next run.

### Auto-detect model picked the wrong model

The model is read from the first line of `ASW.TRC` in the NCS Expert working directory. If NCS Expert wrote a different model there (e.g. from a previous session), the auto-detection may be wrong. Simply select the correct model manually from the dropdown.

---

## Presets

### The Add preset button is disabled

A TRC file must be loaded before you can create a preset. Click **📂 Load TRC** first.

### My preset shows "unmatched options" when applied

This happens when the preset was created for a slightly different module version. Options that exist in the preset but not in the currently loaded TRC are listed in a warning dialog after applying. The matched options are still applied normally.

### I edited a preset but the old values still appear

Make sure you click **Save** inside the preset editor window. Closing the window without saving discards all changes.

---

## Diagnosis

### No `.prg` files appear in the Models tab

Check that your EDIABAS path is set correctly. The default is `C:\EDIABAS\Ecu\`. Use **Change EDIABAS path** if your installation is elsewhere.

### Job descriptions are all in German

By default, job comments in `.prg` files are written in German. Use the **language selector** (DE / EN / PL) in the General tab of the Job details panel to switch language. English and Polish translations are fetched automatically and cached locally.

### The disassembly tab shows unreadable output

BEST/1 bytecode disassembly is an advanced feature intended for developers. The output is the raw instruction-level code of the job — it is not meant to be human-readable in the usual sense. If you just need to understand what a job does, read the comment and results tables instead.

### BETRIEBSWTAB is not showing in the Parameters tab

BETRIEBSWTAB (live data parameter table) is only present in advanced ECU files (~5% of `.prg` files). If a job uses it, you will see it as a tab in the Parameters section filtered to only the rows relevant to that job. If the job does not reference BETRIEBSWTAB, the tab does not appear.

---

## SA Options

### The model dropdown is empty

The SA Options tab reads model data from NCS Expert DATEN files (`C:\NCSEXPER\DATEN\`). If the folder is empty or inaccessible, no models appear. Check that NCS Expert is installed and the DATEN path is correct.

### fa.trc was not found automatically

BimmerDaten looks for `fa.trc` in the NCS Expert working directory. If it is not there, use the **📂** button to locate it manually. You may need to run NCS Expert's "Read FA" step to generate the file first.

### Translation shows "translating..." but never completes

This usually means no internet connection is available, or Google Translate is rate-limiting requests. Try again later. The translation only runs once — once cached, it works offline permanently.

---

## Database

### Where is the database stored?

The SQLite database file `bimmerdaten.db` is in the root of the BimmerDaten folder. It contains translations, presets, favourites, and coding history.

### Can I back up my presets?

Yes — back up `bimmerdaten.db`. All presets, favourites, and cached translations are stored in that file. Copy it to a safe location and restore it to the same path to recover everything.

### I accidentally deleted a preset

Deletion is permanent. If you have a recent backup of `bimmerdaten.db`, restore it to recover the preset.
