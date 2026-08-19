"""Normalize event start/end times and required fields."""
from __future__ import annotations

import datetime as dt
import re
from zoneinfo import ZoneInfo

LOCAL_TZ = ZoneInfo("Asia/Shanghai")
DEFAULT_DURATION_MINUTES = 60


def parse_datetime(value: str):
    if not value:
        return None
    text = str(value).strip()
    parsed = None
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = dt.datetime.fromisoformat(normalized)
    except ValueError:
        for fmt in (
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%dT%H:%M",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
        ):
            try:
                parsed = dt.datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
    if parsed is None:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(LOCAL_TZ).replace(tzinfo=None)
    return parsed


def normalize_event(event: dict, default_duration_minutes: int = DEFAULT_DURATION_MINUTES) -> dict | None:
    start = parse_datetime(event.get("start", ""))
    if start is None:
        return None
    end = parse_datetime(event.get("end", ""))
    if end is None or end <= start:
        end = start + dt.timedelta(minutes=default_duration_minutes)

    normalized = dict(event)
    normalized["start"] = start.strftime("%Y-%m-%dT%H:%M:%S")
    normalized["end"] = end.strftime("%Y-%m-%dT%H:%M:%S")
    normalized.setdefault("all_day", False)
    normalized.setdefault("type", "other")
    normalized.setdefault("status", "auto")
    normalized.setdefault("color", "#64748b")
    normalized.setdefault("links", [])
    normalized.setdefault("source_subject", "")
    normalized.setdefault("source_from", "")
    normalized.setdefault("description", "")
    return normalized


def normalize_events(events: list[dict], default_duration_minutes: int = DEFAULT_DURATION_MINUTES) -> list[dict]:
    result = []
    for event in events:
        normalized = normalize_event(event, default_duration_minutes)
        if normalized:
            result.append(normalized)
    return result


def valid_event_shape(event: dict) -> bool:
    return bool(
        event.get("title")
        and event.get("start")
        and re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", str(event.get("start", "")))
        and re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", str(event.get("end", "")))
    )
