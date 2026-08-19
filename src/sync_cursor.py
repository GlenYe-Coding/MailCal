"""Persist the mailbox sync cursor so sync only processes new email."""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from config_store import ROOT
from file_io import atomic_write_json
from logger import get_logger

CURSOR_PATH = ROOT / "data" / "sync_cursor.json"
log = get_logger("sync_cursor")


def load_cursor() -> dict:
    if not CURSOR_PATH.exists():
        return {"last_uid": 0, "synced_count": 0, "last_email_id": "", "last_date": "", "updated_at": ""}
    try:
        data = json.loads(CURSOR_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"last_uid": 0, "synced_count": 0, "last_email_id": "", "last_date": "", "updated_at": ""}
    return {
        "last_uid": int(data.get("last_uid", 0) or 0),
        "synced_count": int(data.get("synced_count", 0) or 0),
        "last_email_id": data.get("last_email_id", ""),
        "last_date": data.get("last_date", ""),
        "updated_at": data.get("updated_at", ""),
    }


def save_cursor(
    last_uid: int,
    synced_count: int,
    last_email_id: str = "",
    last_date: str = "",
) -> dict:
    cursor = {
        "last_uid": int(last_uid or 0),
        "synced_count": int(synced_count or 0),
        "last_email_id": last_email_id,
        "last_date": last_date,
        "updated_at": dt.datetime.now().astimezone().isoformat(),
    }
    CURSOR_PATH.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(CURSOR_PATH, cursor)
    log.debug("sync cursor saved: uid=%s count=%s", cursor["last_uid"], cursor["synced_count"])
    return cursor


def reset_cursor() -> dict:
    cursor = {
        "last_uid": 0,
        "synced_count": 0,
        "last_email_id": "",
        "last_date": "",
        "updated_at": "",
    }
    CURSOR_PATH.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(CURSOR_PATH, cursor)
    log.info("sync cursor reset")
    return cursor
