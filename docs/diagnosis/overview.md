# Diagnosis

The Diagnosis tab is the main area for exploring EDIABAS ECU files. It has three sub-tabs:

| Sub-tab | Purpose |
|---|---|
| 💼 **Jobs** | Browse and inspect all jobs inside a `.prg` file |
| 📋 **Tables** | Browse all data tables defined in the `.prg` file |
| 🚗 **Models** | Explore INPA model structure and discover related `.prg` files |

---

## Loading a .prg file

Click **📂 Open .PRG** in the top toolbar of the Jobs sub-tab. Navigate to your EDIABAS ECU folder (default: `C:\EDIABAS\Ecu\`) and select any `.prg` file.

Once loaded, the top bar shows:
- File name
- BIP version
- Revision
- Author
- Date
- Total number of jobs and tables

---

## Jobs sub-tab

### Job list (left panel)

All jobs in the file are listed on the left. Each job is color-coded by category:

| Color | Category | Example jobs |
|---|---|---|
| 🔵 Blue | Status / Live Data | `STATUS_*` |
| 🔴 Dark red | Fault memory | `FS_*` |
| 🟢 Green | Actuators | `STEUERN_*` |
| 🟣 Purple | Identification | `IDENT` |
| 🟤 Teal | RAM / Data | `RAM_*`, `DATA_*` |

Use the **Category** dropdown and **Search** field to filter the list.

### Job details (right panel)

Clicking a job opens its details in three sub-tabs:

#### ℹ️ General

Shows:
- **Job name** and hex address in file
- **Category** (auto-detected from name prefix)
- **Job comment** — description from the `.prg` file (in German by default)
- **Language selector** — switch between DE / EN / PL. Translations are loaded from the offline database; if unavailable, an online translation is fetched automatically and saved for future use.
- **Arguments (input)** — table of input parameters the job accepts:
  - Argument name
  - Data type
  - Description
- **Results (output)** — table of values the job returns:
  - Result name
  - Data type
  - Description

#### 📊 Parameters

Shows tables that this specific job actively uses (referenced in its code). Each table appears as a sub-tab.

For **BETRIEBSWTAB** (live data parameter table), only the rows relevant to this job are shown:

| Column | Description |
|---|---|
| Name | Parameter name |
| Byte | Byte position in the DS2 telegram |
| Type | Data type |
| Unit | Measurement unit (km/h, °C, rpm, etc.) |
| FACT_A | Scaling factor A |
| FACT_B | Scaling factor B (offset) |
| Telegram DS2 | Full DS2 telegram bytes with XOR checksum |

For all other tables, all rows are shown with a search/filter field.

Click **📋 Show all tables** to jump to the Tables sub-tab and see every table in the file.

> **Tip:** Click the **?** button on any table sub-tab to see an explanation of what that table contains.

#### 🔧 Disassembly

Shows the full BEST/1 bytecode disassembly of the job. Useful for advanced analysis of what the job actually does at the instruction level.

---

## Tables sub-tab

Shows all data tables defined in the `.prg` file, grouped into categories:

| Category | Tables |
|---|---|
| Errors | FEHLERCODES, FORTTEXTE, FUMWELTTEXTE, FDETAILSTRUKTUR, ... |
| Status | EWSSTART, SLSSTATUS, TEVSTATUS, ... |
| Bits | BITS, FASTABITS, FGRBITS, READINESSBITS |
| Communication | JOBRESULT, BAUDRATE, KONZEPT_TABELLE, ... |
| Other | BETRIEBSWTAB, LIEFERANTEN, and any file-specific tables |

Select a table on the left to preview its contents on the right. Use the **Filter** field to search within rows.

Click the **?** button next to any table name to see a description of what that table contains and how it is used.

> **Note:** Some tables (LIEFERANTEN, FORTTEXTE, JOBRESULT) are standard BMW framework tables present in most `.prg` files with identical content. Tables like BETRIEBSWTAB are ECU-specific and vary between files.

---

## Models sub-tab

Parses your local INPA installation and displays the BMW model tree:

```
BMW
├── E36
├── E39
├── E46
│   ├── Engine
│   │   ├── ME 9.2 for N42 / N45
│   │   └── MS 45.0 for M56
│   ├── Gearbox
│   └── ...
└── E90
```

Selecting an entry shows:
- ECU description
- Associated INPA script
- Available `.prg` files for that ECU

Click **Open PRG** to load the corresponding `.prg` file directly into the Jobs sub-tab.

Use **Change INPA path** if your INPA installation is not in the default location.
