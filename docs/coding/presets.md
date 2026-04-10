# Coding Presets

Presets allow you to save a set of coding changes and apply them to any compatible TRC file with a single click. Think of them as named configurations — for example "Enable auto-lock on speed" or "Comfort turn signal 5 flashes".

---

## Preset list

The **Presets** panel in the left sidebar shows all available presets. When a TRC file is loaded and a model/module is selected, the list automatically filters to show only presets for that model and module.

When no TRC is loaded, all presets are shown so you can browse and preview them.

---

## Applying a preset

1. Load a TRC file and select the correct model and module
2. Select a preset from the list
3. Click **Load preset**

BimmerDaten will match each option in the preset against the currently loaded TRC table. If a match is found, the value is set automatically — exactly as if you had changed it manually.

### Conflict handling

If a preset wants to set an option to a value that differs from what you have already set, a conflict dialog appears listing all conflicts:

```
The following options already have different values:
  - KOMFORT_BLINKEN: current = "nicht_aktiv" → preset = "aktiv"
  - VSLK: current = "inaktiv" → preset = "aktiv"

What would you like to do?
  [Apply all]  [Skip conflicts]  [Cancel]
```

| Choice | Result |
|---|---|
| **Apply all** | All preset values are applied, overwriting your existing changes |
| **Skip conflicts** | Only options that have not been changed are applied |
| **Cancel** | Nothing is changed |

### Unmatched options

If the preset contains options that do not exist in the currently loaded TRC file, a warning dialog lists the unmatched options after applying. This can happen when a preset was created for a slightly different module version.

---

## Creating a preset

> **Load TRC must be active** — the Add preset button is disabled when no TRC file is loaded.

1. Load a TRC file with the model and module you want to create a preset for
2. Click **Add preset** in the Presets panel
3. A new window opens showing the **full coding table** — identical to the main table, including translations, favourites and value dropdowns
4. Change the options you want to include in the preset — only options you actually change will be saved
5. Fill in the preset **name** and optional **description**
6. Click **Save**

The preset is saved to the local database and immediately appears in the list.

---

## Editing a preset

1. Select a preset from the list
2. Click **Preview / Edit**
3. The same editor window opens, pre-filled with the preset's saved values
4. Make your changes and click **Save**

> **Note:** If no TRC file is loaded, the editor opens in **read-only mode** showing only the saved option/value pairs. You cannot edit in this mode — load a TRC file first.

---

## Deleting a preset

1. Select a preset from the list
2. Click **Delete preset**
3. Confirm the deletion when prompted

Deletion is permanent — the preset is removed from the database.

---

## Sharing presets

Presets are stored in the local SQLite database (`bimmerdaten.db`). The database is included in the repository, so when you push to GitHub, your presets go with it.

Anyone who clones the repository gets your presets automatically.

To contribute a preset to the project, open a GitHub Issue describing the preset (model, module, options, what it does) and it will be added to the official database.
