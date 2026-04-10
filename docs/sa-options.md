# SA Options

The SA Options tab lets you decode your vehicle's **FA (Fahrzeugauftrag / Vehicle Order)** and browse every SA (Sonderausstattung / Special Equipment) code available for your BMW model — including which ones are **coding-relevant**.

---

## What are SA codes?

Every BMW is built to a specific factory order. That order includes a list of SA codes — numeric codes identifying every option the car was built with. For example:

| SA | Meaning |
|---|---|
| 205 | Automatic transmission |
| 494 | Navigation system |
| 676 | Comfort Access (keyless entry) |

SA codes matter for coding because some features require specific SA codes to be present in the ECU's configuration. Coding without the right SA may enable features that are not physically installed.

---

## Loading your vehicle's FA file

BimmerDaten reads SA codes from `fa.trc` — the NCS Expert vehicle order file.

### Automatic load

When you open the SA Options tab, BimmerDaten automatically looks for `fa.trc` in the NCS Expert working directory (`C:\NCSEXPER\WORK\` by default). If found, it loads immediately.

### Manual load

Click the **📂** button to select a `fa.trc` file manually. This is useful if you have multiple vehicle configurations saved in different folders.

Once loaded:
- The **VIN** is displayed at the top (read from `SYSDATEN.TRC`)
- The **Show only your car codes** toggle becomes active

---

## The SA options table

| Column | Description |
|---|---|
| **SA** | SA code number |
| **ASW name** | Internal NCS Expert name (from DATEN files) |
| **Description DE** | German description from NCS Expert DATEN |
| **Description EN** | English translation (from database or auto-translated) |
| **Coding** | ✅ = coding-relevant, ❌ = not relevant for coding |

### Row highlighting

When a `fa.trc` is loaded, rows matching your vehicle's SA codes are highlighted:

| Highlight | Meaning |
|---|---|
| **Bold blue** | SA present in your car AND coding-relevant |
| Light blue | SA present in your car, not coding-relevant |
| Normal | SA not in your car |

---

## Filters

### Model selector

Choose your BMW model from the dropdown. The list is built from the `.at` DATEN files found in your NCS Expert installation.

### Show only your car codes

Toggle this button to hide all SA codes that are not in your vehicle's FA. Useful for quickly reviewing which coding-relevant options your car actually has.

### Category filter

Filter SA codes by category:

| Category | Examples |
|---|---|
| Engine | Engine type, displacement |
| Transmission | Automatic, manual, sport |
| Safety | ABS, airbags, DSC |
| Comfort | Seat heating, climate control |
| Multimedia | Navigation, audio, BMW ConnectedDrive |
| Lighting | Xenon, LED, adaptive lights |
| Body | Roof type, trim, exterior package |
| Other | Everything else |

### Search

Type any text to filter by SA code number, ASW name, or description (both DE and EN).

---

## English translations

German descriptions come directly from the NCS Expert DATEN files. English translations are fetched automatically from Google Translate and saved to the local database so each translation only happens once.

### Translating a row

If the **Description EN** column shows *(double-click to translate)*, double-click any cell in that row to trigger translation. A ⏳ indicator appears while the translation is in progress.

Once translated, the English text is saved permanently in the database — no internet connection is needed on future launches.

---

## Source of SA data

SA option data comes from the `.at` files inside your NCS Expert DATEN folder (`C:\NCSEXPER\DATEN\`). These files are part of your BMW Standard Tools installation — BimmerDaten reads them but never modifies them.

The available models in the dropdown depend entirely on which DATEN files are installed on your system.
