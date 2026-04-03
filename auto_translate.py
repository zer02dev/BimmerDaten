"""
auto_translate.py
Automatyczne tłumaczenie komentarzy jobów z pliku .prg do bazy danych.
Używa Google Translate przez deep-translator (darmowe, bez klucza API).

Użycie:
    python auto_translate.py C:\EDIABAS\Ecu\ME9K_NG4.prg
"""

import sys
import sqlite3
import time
from pathlib import Path

try:
    from deep_translator import GoogleTranslator
except ImportError:
    print("Zainstaluj deep-translator: pip install deep-translator")
    sys.exit(1)

try:
    from decoderPrg import parse_prg
except ImportError:
    print("Nie znaleziono decoderPrg.py — upewnij się że jesteś w folderze projektu")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Konfiguracja

DB_PATH = Path(__file__).parent / "data" / "database.db"
DELAY_BETWEEN_REQUESTS = 0.5  # sekundy między requestami do Google


# ---------------------------------------------------------------------------
# Helpers

def extract_jobcomment(comments: list[str]) -> str:
    """Wyciąga JOBCOMMENT z listy komentarzy joba."""
    for line in comments:
        if line.startswith("JOBCOMMENT:"):
            return line[len("JOBCOMMENT:"):].strip()
    return ""


def translate_text(text: str, target: str) -> str:
    """Tłumaczy tekst z DE na docelowy język. Zwraca oryginał przy błędzie."""
    if not text.strip():
        return ""
    try:
        result = GoogleTranslator(source='de', target=target).translate(text)
        return result or text
    except Exception as e:
        print(f"  ⚠️  Błąd tłumaczenia ({target}): {e}")
        return text


def ensure_db(conn: sqlite3.Connection):
    """Tworzy tabelę jeśli nie istnieje."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS translations (
            prg_file    TEXT,
            job_name    TEXT,
            comment_de  TEXT,
            comment_en  TEXT,
            comment_pl  TEXT,
            updated_at  TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (prg_file, job_name)
        )
    """)
    conn.commit()


def job_exists(conn: sqlite3.Connection, prg_file: str, job_name: str) -> bool:
    """Sprawdza czy tłumaczenie już istnieje w bazie."""
    row = conn.execute(
        "SELECT 1 FROM translations WHERE prg_file=? AND job_name=?",
        (prg_file, job_name)
    ).fetchone()
    return row is not None


def upsert_translation(conn: sqlite3.Connection, prg_file: str, job_name: str,
                        comment_de: str, comment_en: str, comment_pl: str):
    """Wstawia lub aktualizuje tłumaczenie w bazie."""
    conn.execute("""
        INSERT INTO translations (prg_file, job_name, comment_de, comment_en, comment_pl)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(prg_file, job_name) DO UPDATE SET
            comment_de = excluded.comment_de,
            comment_en = excluded.comment_en,
            comment_pl = excluded.comment_pl,
            updated_at = datetime('now')
    """, (prg_file, job_name, comment_de, comment_en, comment_pl))
    conn.commit()


# ---------------------------------------------------------------------------
# Główna logika

def translate_prg(prg_path: str, force: bool = False):
    """
    Tłumaczy wszystkie joby z pliku .prg i zapisuje do bazy danych.
    
    Args:
        prg_path: ścieżka do pliku .prg
        force: jeśli True — nadpisuje istniejące tłumaczenia
    """
    prg_path = Path(prg_path)
    if not prg_path.exists():
        print(f"❌ Nie znaleziono pliku: {prg_path}")
        sys.exit(1)

    prg_file = prg_path.stem.upper()  # np. "ME9K_NG4"

    print(f"📂 Wczytuję: {prg_path.name}")
    prg = parse_prg(str(prg_path))
    print(f"✅ Znaleziono {len(prg.jobs)} jobów")

    # Upewnij się że folder data/ istnieje
    DB_PATH.parent.mkdir(exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    ensure_db(conn)

    # Zlicz ile jobów ma komentarze
    jobs_with_comments = [
        job for job in prg.jobs
        if extract_jobcomment(job.comments)
    ]
    jobs_without_comments = len(prg.jobs) - len(jobs_with_comments)

    print(f"📝 Jobów z komentarzem: {len(jobs_with_comments)}")
    print(f"⏭️  Jobów bez komentarza: {jobs_without_comments}")
    print(f"💾 Baza danych: {DB_PATH}")
    print()

    translated = 0
    skipped = 0
    errors = 0

    for i, job in enumerate(prg.jobs):
        comment_de = extract_jobcomment(job.comments)

        if not comment_de:
            # Brak komentarza — wstaw pusty wpis żeby wiedzieć że przetworzono
            if not job_exists(conn, prg_file, job.name):
                upsert_translation(conn, prg_file, job.name, "", "", "")
            continue

        # Sprawdź czy już przetłumaczone
        if not force and job_exists(conn, prg_file, job.name):
            skipped += 1
            continue

        print(f"[{i+1:3}/{len(prg.jobs)}] {job.name}")
        print(f"  DE: {comment_de}")

        # Tłumacz EN
        comment_en = translate_text(comment_de, 'en')
        time.sleep(DELAY_BETWEEN_REQUESTS)

        # Tłumacz PL
        comment_pl = translate_text(comment_de, 'pl')
        time.sleep(DELAY_BETWEEN_REQUESTS)

        print(f"  EN: {comment_en}")
        print(f"  PL: {comment_pl}")

        upsert_translation(conn, prg_file, job.name, comment_de, comment_en, comment_pl)
        translated += 1

    conn.close()

    print()
    print("=" * 50)
    print(f"✅ Przetłumaczono: {translated} jobów")
    print(f"⏭️  Pominięto (już w bazie): {skipped} jobów")
    if errors:
        print(f"⚠️  Błędy: {errors} jobów")
    print(f"💾 Zapisano do: {DB_PATH}")


# ---------------------------------------------------------------------------
# CLI

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Użycie: python auto_translate.py <plik.prg> [--force]")
        print("  --force  nadpisz istniejące tłumaczenia")
        sys.exit(1)

    force = "--force" in sys.argv
    translate_prg(sys.argv[1], force=force)