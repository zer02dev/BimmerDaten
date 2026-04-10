# Coding

The Coding tab allows you to load, view, edit and export NCS Expert coding files (`.trc`) with full change tracking, history, and preset support.

> ⚠️ **Warning:** Incorrect ECU coding can cause serious damage to your vehicle. Always back up your coding data before making any changes. BimmerDaten does not connect to your car — changes are applied through NCS Expert as usual.

---

## Left sidebar

The left sidebar contains all controls for loading and navigating coding files:

| Control | Purpose |
|---|---|
| **Model** | Select your BMW model (E36, E46, E90, etc.) |
| **Module** | Select the ECU module (e.g. GM5.C10, CAS.C01) |
| **🔍 Detect module** | Auto-detect the module from the loaded TRC content |
| **📂 Load TRC** | Load the current TRC file from the NCS Expert working directory |
| **Presets** | Save and apply coding presets (see [Presets](presets.md)) |
| **🔄 Refresh** | Reload the TRC file from disk |
| **📂 History** | Open the coding history dialog |

---

## Loading a TRC file

Click **📂 Load TRC** to read the current `FSW_PSW.TRC` file from your NCS Expert working directory (`C:\NCSEXPER\WORK\` by default).

When the file loads:
- The **Model** field is automatically set from `ASW.TRC` (first line = model name)
- The coding table populates with all options from the file
- A status message shows how many options were loaded

> **Tip:** Run NCS Expert first to read your vehicle's current coding into the TRC file, then load it in BimmerDaten to view and edit it.

---

## Coding table

The main table shows all coding options from the TRC file:

| Column | Description |
|---|---|
| ★ | Favourite — pin frequently used options for quick access |
| Nr | Option number |
| Option | Raw option name from the TRC file |
| Translation | Human-readable name (from NCS Dummy's Translations.csv if configured) |
| Value | Current value — editable via dropdown when a module is loaded |
| Value translation | Human-readable translation of the current value |
| Changed | Indicates if this option differs from the original loaded value |

### Filtering and search

- Use the **filter bar** at the top to search by option name or translation
- Enable **Favourites only** to show only pinned options
- Click ★ on any row to pin/unpin it — favourites are saved per model/module in the database

### Editing values

When a module is loaded (via **Detect module** or manual selection), editable options show a **dropdown** with all valid values for that option. Invalid or unknown values are marked with ⚠️.

Options that belong to the selected module are **fully editable**. Options outside the module are shown in grey and cannot be changed — this prevents accidental modification of unrelated ECU settings.

### Change tracking

The **Changed** column and row highlighting show which options have been modified since the file was loaded. A counter at the bottom right shows the total number of changes.

---

## Detecting the module

Click **🔍 Detect module** after loading a TRC file. BimmerDaten analyses the options in the file and compares them against the known module definitions to find the best match.

A progress indicator appears during detection. When complete, a result dialog shows the detected module and the match percentage. Select the module to apply it.

The match percentage indicates how many options in your TRC file match the module definition — 80%+ is a reliable match.

---

## Exporting

Once you have made your changes, export them back to NCS Expert format:

### Export .MAN

Exports to `FSW_PSW.MAN` in the NCS Expert working directory. This is the file NCS Expert reads when you run a coding job. After exporting, use NCS Expert to write the coding to your vehicle.

### Export .TRC

Exports a complete `.TRC` file with all your changes applied. Use this to save a snapshot of a specific configuration.

Both export dialogs show:
- A preview of all changed options (before → after)
- An optional notes field
- Vehicle metadata (VIN, part number, production date, SA codes) if available

---

## Closing the application

When you close BimmerDaten, if `FSW_PSW.MAN` is not empty, the application asks whether you want to clear it. This follows BMW best practice — the MAN file should be empty when not actively coding.
