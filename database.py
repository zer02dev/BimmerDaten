"""
database.py
SQLite storage for offline job comment translations.
"""

from __future__ import annotations

import json
import sqlite3
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
        self._ensure_sa_translations_schema()
        self._ensure_table_descriptions_schema()
        self.conn.commit()

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
                table_name      TEXT PRIMARY KEY,
                name_en         TEXT NOT NULL DEFAULT '',
                description_en  TEXT NOT NULL DEFAULT ''
            );
            """
        )

        rows = [
            ("JOBRESULT", "Job Result Codes", "Standard status codes returned by all jobs: OKAY, BUSY, ERROR_ECU_REJECTED, ERROR_ECU_PARAMETER, etc."),
            ("LIEFERANTEN", "Supplier List", "List of ECU hardware manufacturers/suppliers (Bosch, Siemens, Hella, Delphi, etc.) used across all modules"),
            ("FORTTEXTE", "Progress Texts", "Standard text strings for diagnostic progress and status reporting"),
            ("FARTTEXTE", "Color/State Texts", "Text labels for colors and operational states"),
            ("BETRIEBSWTAB", "Live Data Parameter Table", "Defines all live data parameters readable from this ECU: byte position, data type, measurement unit, scaling factors (FACT_A/B), and DS2 telegram bytes"),
            ("FDETAILSTRUKTUR", "Fault Detail Structure", "Defines the byte structure of fault memory detail records"),
            ("IDETAILSTRUKTUR", "Info Detail Structure", "Defines the byte structure of info/status detail records"),
            ("HDETAILSTRUKTUR", "History Detail Structure", "Defines the byte structure of historical fault records"),
            ("FUMWELTTEXTE", "Fault Environment Texts", "Text descriptions for fault environment (Umwelt) data fields"),
            ("IUMWELTTEXTE", "Info Environment Texts", "Text descriptions for info environment data fields"),
            ("KONZEPT_TABELLE", "Diagnostic Concept Table", "Maps diagnostic concepts/modes to their implementation parameters"),
            ("STEUERN_DIGITAL", "Digital Control Values", "Digital input/output control value definitions"),
            ("ASCII", "ASCII Lookup Table", "ASCII character mapping table used for string encoding"),
            ("JOBRESULTEXTENDED", "Extended Job Result Codes", "Extended set of job status codes beyond the standard JOBRESULT set"),
            ("FUMWELTMATRIX", "Fault Environment Matrix", "Matrix defining which environment data is captured for each fault code"),
            ("FEHLERTEXT", "Fault Code Texts", "Human-readable text descriptions for diagnostic trouble codes"),
            ("STATUS_TEXT", "Status Texts", "Text representations of ECU status values"),
        ]
        self.conn.executemany(
            """
            INSERT OR IGNORE INTO table_descriptions (table_name, name_en, description_en)
            VALUES (?, ?, ?)
            """,
            rows,
        )

    def get_table_description(self, table_name: str) -> tuple[str, str] | None:
        row = self.conn.execute(
            "SELECT name_en, description_en FROM table_descriptions WHERE table_name = ?",
            (table_name.upper(),),
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
