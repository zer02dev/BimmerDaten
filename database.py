"""
database.py
SQLite storage for offline job comment translations.
"""

from __future__ import annotations

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
