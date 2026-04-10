"""
database.py
SQLite storage for offline job comment translations.
"""

from __future__ import annotations

import json
import sqlite3
import urllib.error
from pathlib import Path
from typing import Optional


class Database:
    def __init__(self, db_path: str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self) -> None:
        self._ensure_translations_schema()
        self._ensure_trc_history_schema()
        self._ensure_trc_favorites_schema()
        self._ensure_presets_schema()
        self._ensure_sa_translations_schema()
        self._ensure_table_descriptions_schema()
        self.conn.commit()
        self.apply_seeds()

    def apply_seeds(self) -> None:
        """Import seed CSV files from ./seeds into matching tables using INSERT OR IGNORE."""
        import csv

        seeds_dir = Path(__file__).resolve().parent / "seeds"
        try:
            seed_files = sorted(seeds_dir.glob("*.csv"))
        except Exception:
            return

        for seed_file in seed_files:
            try:
                table_name = seed_file.stem

                with seed_file.open("r", encoding="utf-8", newline="") as handle:
                    reader = csv.DictReader(handle)
                    if not reader.fieldnames:
                        continue

                    existing_cols = [
                        row[1]
                        for row in self.conn.execute(
                            f"PRAGMA table_info({table_name})"
                        ).fetchall()
                    ]
                    if not existing_cols:
                        continue

                    csv_cols = [col for col in reader.fieldnames if col in existing_cols]
                    if not csv_cols:
                        continue

                    placeholders = ", ".join("?" * len(csv_cols))
                    col_list = ", ".join(csv_cols)
                    sql = (
                        f"INSERT OR IGNORE INTO {table_name} ({col_list}) "
                        f"VALUES ({placeholders})"
                    )

                    for row in reader:
                        try:
                            values = [row.get(col) for col in csv_cols]
                            self.conn.execute(sql, values)
                        except Exception:
                            continue

                    self.conn.commit()
            except Exception:
                # Never crash app startup if a seed file is invalid.
                continue

    def _ensure_translations_schema(self) -> None:
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS translations (
                prg_file    TEXT,
                job_name    TEXT,
                comment_de  TEXT,
                comment_en  TEXT,
                comment_pl  TEXT,
                updated_at  TEXT DEFAULT (datetime('now')),
                PRIMARY KEY (prg_file, job_name)
            );
            """
        )

        rows = self.conn.execute("PRAGMA table_info(translations)").fetchall()
        columns = {row[1] for row in rows}
        if "prg_file" in columns:
            return

        # Legacy schema detected, rebuild table with the new composite key.
        self.conn.execute("ALTER TABLE translations RENAME TO translations_old")
        self.conn.execute(
            """
            CREATE TABLE translations (
                prg_file    TEXT,
                job_name    TEXT,
                comment_de  TEXT,
                comment_en  TEXT,
                comment_pl  TEXT,
                updated_at  TEXT DEFAULT (datetime('now')),
                PRIMARY KEY (prg_file, job_name)
            );
            """
        )
        self.conn.execute(
            """
            INSERT OR REPLACE INTO translations (
                prg_file, job_name, comment_de, comment_en, comment_pl, updated_at
            )
            SELECT
                '', job_name, comment_de, comment_en, comment_pl, updated_at
            FROM translations_old
            """
        )
        self.conn.execute("DROP TABLE translations_old")

    def _ensure_trc_history_schema(self) -> None:
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS trc_history (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                model          TEXT NOT NULL,
                module         TEXT NOT NULL,
                module_file    TEXT NOT NULL,
                content_before  TEXT NOT NULL,
                content_after   TEXT NOT NULL,
                notes          TEXT NOT NULL DEFAULT '',
                changed_options TEXT NOT NULL,
                vin            TEXT,
                teilenummer    TEXT,
                production_date TEXT,
                sa_codes       TEXT,
                exported_at    TEXT DEFAULT (datetime('now'))
            );
            """
        )

        rows = self.conn.execute("PRAGMA table_info(trc_history)").fetchall()
        columns = {row[1] for row in rows}
        if "notes" not in columns:
            self.conn.execute("ALTER TABLE trc_history ADD COLUMN notes TEXT NOT NULL DEFAULT ''")
        if "vin" not in columns:
            self.conn.execute("ALTER TABLE trc_history ADD COLUMN vin TEXT")
        if "teilenummer" not in columns:
            self.conn.execute("ALTER TABLE trc_history ADD COLUMN teilenummer TEXT")
        if "codierdatum" in columns:
            try:
                self.conn.execute("ALTER TABLE trc_history DROP COLUMN codierdatum")
            except sqlite3.Error:
                # Older SQLite versions may not support DROP COLUMN.
                pass
        if "production_date" not in columns:
            self.conn.execute("ALTER TABLE trc_history ADD COLUMN production_date TEXT")
        if "sa_codes" not in columns:
            self.conn.execute("ALTER TABLE trc_history ADD COLUMN sa_codes TEXT")

    def _ensure_trc_favorites_schema(self) -> None:
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS trc_favorites (
                model        TEXT NOT NULL,
                module       TEXT NOT NULL,
                option_name  TEXT NOT NULL,
                pinned       INTEGER NOT NULL DEFAULT 1,
                updated_at   TEXT DEFAULT (datetime('now')),
                PRIMARY KEY (model, module, option_name)
            );
            """
        )

    def _ensure_presets_schema(self) -> None:
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS coding_presets (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                model       TEXT NOT NULL,
                module      TEXT NOT NULL,
                changes     TEXT NOT NULL,
                created_at  TEXT DEFAULT (datetime('now')),
                updated_at  TEXT DEFAULT (datetime('now'))
            );
            """
        )

    def _ensure_sa_translations_schema(self) -> None:
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sa_translations (
                chassis     TEXT,
                sa_code     TEXT,
                desc_de     TEXT,
                desc_en     TEXT,
                desc_pl     TEXT,
                updated_at  TEXT DEFAULT (datetime('now')),
                PRIMARY KEY (chassis, sa_code)
            );
            """
        )

    def _ensure_table_descriptions_schema(self) -> None:
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS table_descriptions (
                table_name     TEXT PRIMARY KEY,
                name_en        TEXT NOT NULL DEFAULT '',
                description_en TEXT NOT NULL DEFAULT ''
            );
            """
        )
        self.conn.commit()

    def get_table_description(self, table_name: str) -> tuple[str, str] | None:
        row = self.conn.execute(
            """SELECT name_en, description_en
               FROM table_descriptions
               WHERE table_name = UPPER(?)""",
            (table_name,),
        ).fetchone()
        return (row["name_en"], row["description_en"]) if row else None

    def save_table_description(self, table_name: str, name_en: str, description_en: str) -> None:
        self.conn.execute(
            """INSERT OR REPLACE INTO table_descriptions (table_name, name_en, description_en)
               VALUES (?, ?, ?)""",
            (table_name.upper(), name_en, description_en),
        )
        self.conn.commit()

    def save_trc_history(
        self,
        model: str,
        module: str,
        module_file: str,
        content_before: str,
        content_after: str,
        changed_options: list[dict],
        notes: str = "",
        vin: str = "",
        teilenummer: str = "",
        production_date: str = "",
        sa_codes: list[str] | None = None,
    ) -> int:
        payload = json.dumps(changed_options, ensure_ascii=False)
        sa_codes_payload = json.dumps(sa_codes or [], ensure_ascii=False)
        cursor = self.conn.execute(
            """
            INSERT INTO trc_history (
                model, module, module_file,
                content_before, content_after, notes, changed_options,
                vin, teilenummer, production_date, sa_codes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                (model or "").upper(),
                (module or "").upper(),
                module_file or "",
                content_before or "",
                content_after or "",
                notes or "",
                payload,
                vin or "",
                teilenummer or "",
                production_date or "",
                sa_codes_payload,
            ),
        )
        self.conn.execute(
            """
            DELETE FROM trc_history
            WHERE model = ? AND module = ? AND id NOT IN (
                SELECT id
                FROM trc_history
                WHERE model = ? AND module = ?
                ORDER BY id DESC
                LIMIT 35
            )
            """,
            ((model or "").upper(), (module or "").upper(), (model or "").upper(), (module or "").upper()),
        )
        self.conn.commit()
        return int(cursor.lastrowid or 0)

    def list_trc_history(self, model: str, module: str, limit: int = 50) -> list[dict]:
        try:
            rows = self.conn.execute(
                """
                SELECT id, model, module, module_file,
                      content_before, content_after, notes,
                        changed_options, vin, teilenummer,
                      production_date, sa_codes, exported_at
                FROM trc_history
                WHERE model = ? AND module = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                ((model or "").upper(), (module or "").upper(), int(limit)),
            ).fetchall()
        except sqlite3.Error:
            return []

        result: list[dict] = []
        for row in rows:
            try:
                changed_options = json.loads(row["changed_options"] or "[]")
            except Exception:
                changed_options = []
            try:
                sa_codes = json.loads(row["sa_codes"] or "[]")
            except Exception:
                sa_codes = []
            result.append(
                {
                    "id": row["id"],
                    "model": row["model"],
                    "module": row["module"],
                    "module_file": row["module_file"],
                    "content_before": row["content_before"],
                    "content_after": row["content_after"],
                    "notes": row["notes"] if row["notes"] else "",
                    "changed_options": changed_options,
                    "vin": row["vin"] if row["vin"] else "",
                    "teilenummer": row["teilenummer"] if row["teilenummer"] else "",
                    "production_date": row["production_date"] if row["production_date"] else "",
                    "sa_codes": sa_codes,
                    "exported_at": row["exported_at"],
                }
            )
        return result

    def get_trc_history(self, model: str, module: str, limit: int = 50) -> list[dict]:
        return self.list_trc_history(model, module, limit=limit)

    def list_all_trc_history(self, limit: int = 200) -> list[dict]:
        try:
            rows = self.conn.execute(
                """
                SELECT id, model, module, module_file,
                      content_before, content_after, notes,
                        changed_options, vin, teilenummer,
                      production_date, sa_codes, exported_at
                FROM trc_history
                ORDER BY id DESC
                LIMIT ?
                """,
                (int(limit),),
            ).fetchall()
        except sqlite3.Error:
            return []

        result: list[dict] = []
        for row in rows:
            try:
                changed_options = json.loads(row["changed_options"] or "[]")
            except Exception:
                changed_options = []
            try:
                sa_codes = json.loads(row["sa_codes"] or "[]")
            except Exception:
                sa_codes = []
            result.append(
                {
                    "id": row["id"],
                    "model": row["model"],
                    "module": row["module"],
                    "module_file": row["module_file"],
                    "content_before": row["content_before"],
                    "content_after": row["content_after"],
                    "notes": row["notes"] if row["notes"] else "",
                    "changed_options": changed_options,
                    "vin": row["vin"] if row["vin"] else "",
                    "teilenummer": row["teilenummer"] if row["teilenummer"] else "",
                    "production_date": row["production_date"] if row["production_date"] else "",
                    "sa_codes": sa_codes,
                    "exported_at": row["exported_at"],
                }
            )
        return result

    def get_trc_history_by_id(self, record_id: int) -> dict | None:
        try:
            row = self.conn.execute(
                """
                SELECT id, model, module, module_file,
                      content_before, content_after, notes,
                        changed_options, vin, teilenummer,
                      production_date, sa_codes, exported_at
                FROM trc_history
                WHERE id = ?
                LIMIT 1
                """,
                (int(record_id),),
            ).fetchone()
        except sqlite3.Error:
            return None

        if not row:
            return None

        try:
            changed_options = json.loads(row["changed_options"] or "[]")
        except Exception:
            changed_options = []
        try:
            sa_codes = json.loads(row["sa_codes"] or "[]")
        except Exception:
            sa_codes = []

        return {
            "id": row["id"],
            "model": row["model"],
            "module": row["module"],
            "module_file": row["module_file"],
            "content_before": row["content_before"],
            "content_after": row["content_after"],
            "notes": row["notes"] if row["notes"] else "",
            "changed_options": changed_options,
            "vin": row["vin"] if row["vin"] else "",
            "teilenummer": row["teilenummer"] if row["teilenummer"] else "",
            "production_date": row["production_date"] if row["production_date"] else "",
            "sa_codes": sa_codes,
            "exported_at": row["exported_at"],
        }

    def get_translation(self, prg_file: str, job_name: str, lang: str) -> Optional[str]:
        """Return translation for a job in one language: de/en/pl, else None."""
        lang_map = {
            "de": "comment_de",
            "en": "comment_en",
            "pl": "comment_pl",
        }
        column = lang_map.get((lang or "").lower())
        if not column:
            return None

        try:
            row = self.conn.execute(
                f"SELECT {column} FROM translations WHERE prg_file = ? AND job_name = ?",
                ((prg_file or "").upper(), job_name),
            ).fetchone()
        except sqlite3.Error:
            return None

        if not row:
            return None
        value = row[column]
        return value if value else None

    def save_translation(
        self,
        prg_file: str,
        job_name: str,
        comment_de: str | None = None,
        comment_en: str | None = None,
        comment_pl: str | None = None,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO translations (prg_file, job_name, comment_de, comment_en, comment_pl)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(prg_file, job_name) DO UPDATE SET
                comment_de = COALESCE(excluded.comment_de, comment_de),
                comment_en = COALESCE(excluded.comment_en, comment_en),
                comment_pl = COALESCE(excluded.comment_pl, comment_pl),
                updated_at = datetime('now')
            """,
            (
                (prg_file or "").upper(),
                job_name or "",
                comment_de,
                comment_en,
                comment_pl,
            ),
        )
        self.conn.commit()

    def get_all_translations(self, prg_file: str, job_name: str) -> dict:
        """Return all available translations as {de, en, pl} keys."""
        result = {"de": None, "en": None, "pl": None}
        try:
            row = self.conn.execute(
                """
                SELECT comment_de, comment_en, comment_pl
                FROM translations
                WHERE prg_file = ? AND job_name = ?
                """,
                ((prg_file or "").upper(), job_name),
            ).fetchone()
        except sqlite3.Error:
            return result

        if not row:
            return result

        result["de"] = row["comment_de"] if row["comment_de"] else None
        result["en"] = row["comment_en"] if row["comment_en"] else None
        result["pl"] = row["comment_pl"] if row["comment_pl"] else None
        return result

    def get_trc_favorites(self, model: str, module: str) -> set[str]:
        model_key = (model or "").strip().upper()
        module_key = (module or "").strip().upper()
        if not model_key or not module_key:
            return set()

        try:
            rows = self.conn.execute(
                """
                SELECT option_name
                FROM trc_favorites
                WHERE model = ? AND module = ? AND pinned = 1
                """,
                (model_key, module_key),
            ).fetchall()
        except sqlite3.Error:
            return set()

        favorites: set[str] = set()
        for row in rows:
            option_name = str(row["option_name"] or "").strip().upper()
            if option_name:
                favorites.add(option_name)
        return favorites

    def set_trc_favorite(self, model: str, module: str, option_name: str, pinned: bool) -> None:
        model_key = (model or "").strip().upper()
        module_key = (module or "").strip().upper()
        option_key = (option_name or "").strip().upper()
        if not model_key or not module_key or not option_key:
            return

        try:
            if pinned:
                self.conn.execute(
                    """
                    INSERT INTO trc_favorites (model, module, option_name, pinned)
                    VALUES (?, ?, ?, 1)
                    ON CONFLICT(model, module, option_name) DO UPDATE SET
                        pinned = 1,
                        updated_at = datetime('now')
                    """,
                    (model_key, module_key, option_key),
                )
            else:
                self.conn.execute(
                    """
                    DELETE FROM trc_favorites
                    WHERE model = ? AND module = ? AND option_name = ?
                    """,
                    (model_key, module_key, option_key),
                )
            self.conn.commit()
        except sqlite3.Error:
            return

    def get_presets(self, model: str = "", module: str = "") -> list[dict]:
        if model and module:
            rows = self.conn.execute(
                """SELECT id, name, description, model, module, changes,
                          created_at, updated_at
                   FROM coding_presets
                   WHERE UPPER(model)=UPPER(?) AND UPPER(module)=UPPER(?)
                   ORDER BY name""",
                (model, module),
            ).fetchall()
        else:
            rows = self.conn.execute(
                """SELECT id, name, description, model, module, changes,
                          created_at, updated_at
                   FROM coding_presets ORDER BY model, module, name"""
            ).fetchall()
        result = []
        for row in rows:
            d = dict(row)
            d["changes"] = json.loads(d["changes"] or "[]")
            result.append(d)
        return result

    def save_preset(
        self,
        name: str,
        description: str,
        model: str,
        module: str,
        changes: list[dict],
        preset_id: int | None = None,
    ) -> int:
        payload = json.dumps(changes, ensure_ascii=False)
        if preset_id:
            self.conn.execute(
                """UPDATE coding_presets
                   SET name=?, description=?, model=?, module=?, changes=?,
                       updated_at=datetime('now')
                   WHERE id=?""",
                (name, description, model.upper(), module.upper(), payload, preset_id),
            )
            self.conn.commit()
            return preset_id
        cursor = self.conn.execute(
            """INSERT INTO coding_presets
                   (name, description, model, module, changes)
               VALUES (?, ?, ?, ?, ?)""",
            (name, description, model.upper(), module.upper(), payload),
        )
        self.conn.commit()
        return int(cursor.lastrowid or 0)

    def delete_preset(self, preset_id: int) -> None:
        self.conn.execute("DELETE FROM coding_presets WHERE id=?", (preset_id,))
        self.conn.commit()

    def get_sa_translation(self, chassis: str, sa_code: str, lang: str) -> Optional[str]:
        lang_map = {
            "de": "desc_de",
            "en": "desc_en",
            "pl": "desc_pl",
        }
        column = lang_map.get((lang or "").lower())
        if not column:
            return None

        try:
            row = self.conn.execute(
                f"SELECT {column} FROM sa_translations WHERE chassis = ? AND sa_code = ?",
                ((chassis or "").strip().upper(), (sa_code or "").strip().upper()),
            ).fetchone()
        except sqlite3.Error:
            return None

        if not row:
            return None
        value = row[column]
        return value if value else None

    def save_sa_translation(
        self,
        chassis: str,
        sa_code: str,
        desc_de: str | None = None,
        desc_en: str | None = None,
        desc_pl: str | None = None,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO sa_translations (chassis, sa_code, desc_de, desc_en, desc_pl)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(chassis, sa_code) DO UPDATE SET
                desc_de = COALESCE(excluded.desc_de, desc_de),
                desc_en = COALESCE(excluded.desc_en, desc_en),
                desc_pl = COALESCE(excluded.desc_pl, desc_pl),
                updated_at = datetime('now')
            """,
            (
                (chassis or "").strip().upper(),
                (sa_code or "").strip().upper(),
                desc_de,
                desc_en,
                desc_pl,
            ),
        )
        self.conn.commit()

    def update_from_github(self, progress_callback=None) -> dict:
        """
        Fetch seed CSVs from GitHub and import new rows via INSERT OR IGNORE.
        Returns dict: {table_name: rows_processed} for each file.
        """
        import csv
        import io
        import urllib.request

        base_url = "https://raw.githubusercontent.com/zer02dev/BimmerDaten/main/seeds/"
        seed_files = {
            "table_descriptions.csv": "table_descriptions",
            "translations.csv": "translations",
            "coding_presets.csv": "coding_presets",
            "sa_translations.csv": "sa_translations",
        }

        results: dict[str, int | str] = {}

        for filename, table_name in seed_files.items():
            if progress_callback:
                progress_callback(f"Fetching {filename}...")

            url = base_url + filename
            try:
                with urllib.request.urlopen(url, timeout=10) as resp:
                    content = resp.read().decode("utf-8")
            except urllib.error.HTTPError as exc:
                if exc.code == 404:
                    results[table_name] = "not available"
                else:
                    results[table_name] = f"ERROR: HTTP {exc.code}"
                continue
            except Exception as exc:
                results[table_name] = f"ERROR: {exc}"
                continue

            reader = csv.DictReader(io.StringIO(content))
            if not reader.fieldnames:
                results[table_name] = "empty"
                continue

            try:
                existing_cols = [
                    row[1]
                    for row in self.conn.execute(
                        f"PRAGMA table_info({table_name})"
                    ).fetchall()
                ]
            except Exception:
                results[table_name] = "ERROR: table not found"
                continue

            csv_cols = [c for c in reader.fieldnames if c in existing_cols]
            if not csv_cols:
                results[table_name] = "no matching columns"
                continue

            placeholders = ", ".join("?" * len(csv_cols))
            col_list = ", ".join(csv_cols)
            sql = f"INSERT OR IGNORE INTO {table_name} ({col_list}) VALUES ({placeholders})"

            count = 0
            for row in reader:
                values = [row.get(col) for col in csv_cols]
                try:
                    self.conn.execute(sql, values)
                    count += 1
                except Exception:
                    pass

            self.conn.commit()
            results[table_name] = count

        return results

    def import_csv_file(self, file_path: str, table_name: str) -> int:
        """
        Import a local CSV file into the specified table using INSERT OR IGNORE.
        CSV must have a header row with column names.
        Only columns present in both the CSV and the DB table are imported.
        Returns number of rows processed.
        Raises exception on file or schema error.
        """
        import csv

        with open(file_path, encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            if not reader.fieldnames:
                raise ValueError("CSV file has no header row.")

            existing_cols = [
                row[1]
                for row in self.conn.execute(
                    f"PRAGMA table_info({table_name})"
                ).fetchall()
            ]
            if not existing_cols:
                raise ValueError(f"Table '{table_name}' does not exist in the database.")

            csv_cols = [c for c in reader.fieldnames if c in existing_cols]
            if not csv_cols:
                raise ValueError(
                    f"No matching columns between CSV and table '{table_name}'.\n"
                    f"CSV columns: {list(reader.fieldnames)}\n"
                    f"Table columns: {existing_cols}"
                )

            placeholders = ", ".join("?" * len(csv_cols))
            col_list = ", ".join(csv_cols)
            sql = f"INSERT OR IGNORE INTO {table_name} ({col_list}) VALUES ({placeholders})"

            count = 0
            for row in reader:
                values = [row.get(col) for col in csv_cols]
                try:
                    self.conn.execute(sql, values)
                    count += 1
                except Exception:
                    pass

            self.conn.commit()
            return count

    def close(self):
        try:
            self.conn.close()
        except Exception:
            pass


if __name__ == "__main__":
    default_db = Path(__file__).resolve().parent / "data" / "database.db"
    db = Database(str(default_db))

    sample_prg = "ME9K_NG4"
    sample_job = "STATUS_MOTORDREHZAHL"
    print(f"DB path: {default_db}")
    print("Single translation EN:", db.get_translation(sample_prg, sample_job, "en"))
    print("All translations:", db.get_all_translations(sample_prg, sample_job))

    db.close()
