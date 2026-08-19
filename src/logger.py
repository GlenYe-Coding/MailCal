"""Central logging setup. Debug output is opt-in via config or env."""
from __future__ import annotations

import logging
import os
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = ROOT / "logs"
LOG_FILE = LOG_DIR / "app.log"


def setup_logging(level: str | None = None) -> None:
    logger = logging.getLogger("email_calendar")
    resolved = level or os.getenv("EMAIL_CALENDAR_LOG_LEVEL") or "INFO"
    numeric = getattr(logging, str(resolved).upper(), logging.INFO)
    logger.setLevel(numeric)
    logger.propagate = False

    if logger.handlers:
        for handler in logger.handlers:
            handler.setLevel(numeric)
        return

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )

    file_handler = RotatingFileHandler(LOG_FILE, maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    file_handler.setLevel(numeric)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(numeric)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"email_calendar.{name}")


def clear_logs() -> dict:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    LOG_FILE.write_text("", encoding="utf-8")
    return {"ok": True}


def cleanup_logs(retention_days: int = 7) -> dict:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    cutoff = time.time() - max(1, int(retention_days)) * 86400
    removed = 0
    for path in LOG_DIR.glob("app.log.*"):
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink()
                removed += 1
        except OSError:
            continue
    return {"ok": True, "removed": removed}
