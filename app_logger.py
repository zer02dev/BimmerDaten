from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path

_CURRENT_LOG_FILE: Path | None = None


def _logs_dir() -> Path:
    local_appdata = os.environ.get("LOCALAPPDATA")
    base = Path(local_appdata) if local_appdata else (Path.home() / "AppData" / "Local")
    return base / "BimmerDaten" / "Logs"


def get_log_file_path() -> str:
    return str(_CURRENT_LOG_FILE) if _CURRENT_LOG_FILE else ""


def get_logs_dir_path() -> str:
    return str(_logs_dir())


def setup_logger() -> logging.Logger:
    global _CURRENT_LOG_FILE

    logs_dir = _logs_dir()
    logs_dir.mkdir(parents=True, exist_ok=True)

    # Keep only 5 most recent log files.
    existing = sorted(logs_dir.glob("bimmerdaten_*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
    # Keep 4 previous files; the current session log becomes the 5th file.
    for old_file in existing[4:]:
        try:
            old_file.unlink()
        except OSError:
            # Keep startup robust even when old logs are locked.
            pass

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    _CURRENT_LOG_FILE = logs_dir / f"bimmerdaten_{timestamp}.log"

    logger = logging.getLogger("bimmerdaten")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    # Reconfigure handlers for current session file.
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        try:
            handler.close()
        except Exception:
            pass

    file_handler = logging.FileHandler(_CURRENT_LOG_FILE, encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    logger.addHandler(file_handler)

    logger.info("Logger initialized. File: %s", _CURRENT_LOG_FILE)
    return logger
