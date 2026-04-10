# Glossary

A reference of terms used in BimmerDaten and the BMW Standard Tools ecosystem.

---

## ASW.TRC

A file written by NCS Expert in its working directory (`C:\NCSEXPER\WORK\`). The first line contains the vehicle model code (e.g. `E46`). BimmerDaten reads this file to auto-detect the model when loading a TRC file.

---

## BETRIEBSWTAB

A data table found in some EDIABAS `.prg` files. It defines live data parameters — what physical value each byte in a DS2 telegram represents, including scaling factors and units. Only present in advanced ECU files (roughly 5% of all `.prg` files). In BimmerDaten, BETRIEBSWTAB rows are filtered per job to show only the parameters that job uses.

---

## BEST/1

**BMW Embedded Software Toolchain / 1** — the bytecode language used inside EDIABAS `.prg` files. Jobs are compiled to BEST/1 bytecode, which the EDIABAS runtime executes when communicating with an ECU. BimmerDaten can display a disassembly of this bytecode.

---

## BIP

**BMW Interface Protocol** — version information stored in the header of a `.prg` file. The BIP version tells you which generation of EDIABAS produced the file.

---

## Coding

The process of writing configuration values to a BMW ECU. In the BMW Standard Tools workflow:
1. NCS Expert reads the current ECU configuration into `FSW_PSW.TRC`
2. You edit the values (in NCS Expert or in BimmerDaten)
3. NCS Expert writes the changes back via `FSW_PSW.MAN`

BimmerDaten handles steps 1 and 2 — it does not write directly to the car.

---

## DATEN

The NCS Expert DATEN folder (`C:\NCSEXPER\DATEN\`) contains model-specific data files including `.at` files (SA option lists), `.c` files (coding parameter definitions), and other support files. BimmerDaten reads these files to power the SA Options tab and coding module definitions.

---

## DS2

A BMW-proprietary ECU communication protocol used in older vehicles (E-series). The DS2 telegram is a sequence of bytes sent to the ECU to request data or trigger an action. BETRIEBSWTAB rows include the full DS2 telegram for each live data parameter.

---

## ECU

**Engine Control Unit** — a generic term for any electronic control module in the car. BMW vehicles contain dozens of ECUs (engine, gearbox, body control, lighting, etc.), each with its own `.prg` file and coding parameters.

---

## EDIABAS

**Electronic Diagnostic Base System** — BMW's diagnostic software framework. It consists of a runtime that executes `.prg` files to communicate with ECUs. EDIABAS is part of BMW Standard Tools. BimmerDaten reads EDIABAS `.prg` files but does not execute them.

---

## FA

**Fahrzeugauftrag** (Vehicle Order) — the factory build specification for a specific BMW. The FA contains all SA codes that describe exactly how the car was built. NCS Expert reads the FA from the vehicle and writes it to `fa.trc`.

---

## FSW_PSW.TRC / FSW_PSW.MAN

Two key files in the NCS Expert working directory:

| File | Purpose |
|---|---|
| `FSW_PSW.TRC` | Current ECU coding read from the car |
| `FSW_PSW.MAN` | Modified coding to be written back to the car |

BimmerDaten reads from `.TRC` and writes to `.MAN`.

---

## INPA

**Ingenieurbüro Norbert Pöll Application** — a BMW diagnostic scripting environment. INPA scripts (`.IPO` files) reference `.prg` files to perform diagnostic tasks. The **Models** tab in BimmerDaten parses the INPA installation to display the BMW model hierarchy and link models to their `.prg` files.

---

## Job

A named procedure inside a `.prg` file. Jobs are the executable units of EDIABAS — each job performs a specific diagnostic task such as reading fault codes, querying live data, or triggering an actuator. Jobs accept input arguments and return output results.

---

## MAN file

See **FSW_PSW.MAN** above.

---

## Module

In the coding context, a module is a specific ECU software configuration. Modules are identified by codes like `GM5.C10` or `CAS.C01`. The module determines which coding options are available and what valid values they accept.

---

## NCS Expert

**NCS = Network Coding System** — BMW's official coding tool. It connects to the vehicle via an OBD interface and can read or write ECU configurations. NCS Expert uses DATEN files and TRC files. BimmerDaten is designed to complement NCS Expert, not replace it.

---

## NCS Dummy

A third-party tool by REVTOR that adds human-readable translations to NCS Expert coding parameters. It ships with a `Translations.csv` file mapping raw option names to meaningful descriptions. BimmerDaten can optionally use this file if you have NCS Dummy installed.

> The translations in BimmerDaten come from your local copy of NCS Dummy's `Translations.csv`. They are the work of REVTOR — BimmerDaten does not include any translation data of its own.

---

## Preset

A named set of coding changes in BimmerDaten. A preset stores a model, module, and a list of option/value pairs. When applied to a loaded TRC file, each option in the preset is set automatically. See [Presets](coding/presets.md).

---

## .prg file

A compiled EDIABAS ECU program file. `.prg` files contain jobs (compiled BEST/1 bytecode) and data tables. Each ECU has its own `.prg` file. They are stored in the EDIABAS ECU folder (`C:\EDIABAS\Ecu\`).

---

## SA

**Sonderausstattung** (Special Equipment) — a numeric code identifying a factory-installed option. SA codes are part of the vehicle's FA and determine what features the car was built with. Some SA codes are coding-relevant, meaning the ECU's coding must match the installed hardware.

---

## SYSDATEN.TRC

A file in the NCS Expert working directory containing vehicle metadata: VIN, part number, production date, and SA codes. BimmerDaten reads this file to display the VIN in the SA Options tab and to include vehicle information in export dialogs.

---

## Tool32

A BMW diagnostic tool included in BMW Standard Tools. Tool32 allows manual execution of EDIABAS jobs — it is the reference tool for understanding what a job does and what it returns. BimmerDaten's Diagnosis tab provides a read-only browser of the same job information visible in Tool32.

---

## .trc file

A plain text file used by NCS Expert to store ECU coding. Each line is an `OPTION=VALUE` pair. `FSW_PSW.TRC` is the main coding file. BimmerDaten loads, edits, and exports `.trc` files.

---

## VIN

**Vehicle Identification Number** — the unique 17-character identifier for a specific car. BimmerDaten reads the VIN from `SYSDATEN.TRC` and displays it in the SA Options tab and coding export dialogs.
