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
                exported_at    TEXT DEFAULT (datetime('now'))
            );
            """
        )

        rows = self.conn.execute("PRAGMA table_info(trc_history)").fetchall()
        columns = {row[1] for row in rows}
        if "notes" not in columns:
            self.conn.execute("ALTER TABLE trc_history ADD COLUMN notes TEXT NOT NULL DEFAULT ''")

    def save_trc_history(
        self,
        model: str,
        module: str,
        module_file: str,
        content_before: str,
        content_after: str,
        changed_options: list[dict],
        notes: str = "",
    ) -> int:
        payload = json.dumps(changed_options, ensure_ascii=False)
        cursor = self.conn.execute(
            """
            INSERT INTO trc_history (
                model, module, module_file,
                content_before, content_after, notes, changed_options
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                (model or "").upper(),
                (module or "").upper(),
                module_file or "",
                content_before or "",
                content_after or "",
                notes or "",
                payload,
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
                LIMIT 10
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
                       changed_options, exported_at
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
                    "exported_at": row["exported_at"],
                }
            )
        return result

    def get_trc_history(self, model: str, module: str, limit: int = 50) -> list[dict]:
        return self.list_trc_history(model, module, limit=limit)

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
