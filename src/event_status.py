"""Derive calendar event state from time and manual overrides."""
from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

LOCAL_TZ = ZoneInfo("Asia/Shanghai")

STATUS_LABELS = {
    "upcoming": "待开始",
    "ongoing": "进行中",
    "overdue": "已逾期",
    "done": "已完成",
    "cancelled": "已取消",
}


def _parse(value: str):
    if not value:
        return None
    text = value.strip()
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError:
        try:
            parsed = dt.datetime.strptime(text, "%Y-%m-%dT%H:%M:%S")
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=LOCAL_TZ)
    return parsed


def get_status(event: dict, now: dt.datetime | None = None) -> str:
    manual = event.get("status")
    if manual in ("done", "cancelled"):
        return manual
    current = now or dt.datetime.now(LOCAL_TZ)
    start = _parse(event.get("start", ""))
    end = _parse(event.get("end", ""))
    if start is None:
        return "upcoming"
    if end is None:
        end = start + dt.timedelta(hours=1)
    if current < start:
        return "upcoming"
    if current <= end:
        return "ongoing"
    return "overdue"


def decorate(events: list[dict], now: dt.datetime | None = None) -> list[dict]:
    result = []
    for event in events:
        item = dict(event)
        item["current_status"] = get_status(item, now)
        result.append(item)
    return result
