"""Shared input validation for REST API and MCP event endpoints."""
from __future__ import annotations

from event_normalizer import normalize_event, parse_datetime

EVENT_TYPES = ("interview", "assessment", "event", "meeting", "deadline", "other")
EVENT_STATUSES = ("auto", "upcoming", "ongoing", "overdue", "done", "cancelled")
TITLE_MAX_LENGTH = 60
DESCRIPTION_MAX_LENGTH = 20000


def validate_event_input(payload: dict, partial: bool = False) -> list[str]:
    errors: list[str] = []
    if not isinstance(payload, dict):
        return ["事件参数必须是 JSON 对象"]

    title = payload.get("title")
    if title is not None:
        if not isinstance(title, str) or not title.strip():
            errors.append("title 必须是非空字符串")
        elif len(title.strip()) > TITLE_MAX_LENGTH:
            errors.append(f"title 不能超过 {TITLE_MAX_LENGTH} 个字符")

    for field, label in (("start", "开始时间"), ("end", "结束时间")):
        value = payload.get(field)
        if value is None or value == "":
            continue
        if not isinstance(value, str) or parse_datetime(value) is None:
            errors.append(f"{field} 必须是可解析的 ISO 时间")

    start = parse_datetime(payload.get("start", ""))
    end = parse_datetime(payload.get("end", ""))
    if start and end and end <= start:
        errors.append("end 必须晚于 start")

    event_type = payload.get("type")
    if event_type is not None and event_type not in EVENT_TYPES:
        errors.append(f"type 必须是 {', '.join(EVENT_TYPES)} 之一")

    status = payload.get("status")
    if status is not None and status not in EVENT_STATUSES:
        errors.append(f"status 必须是 {', '.join(EVENT_STATUSES)} 之一")

    description = payload.get("description")
    if "description" in payload and not isinstance(description, str):
        errors.append("description 必须是字符串")
    elif isinstance(description, str) and len(description) > DESCRIPTION_MAX_LENGTH:
        errors.append(f"description 不能超过 {DESCRIPTION_MAX_LENGTH} 个字符")

    if not partial:
        if not title or not str(title).strip():
            errors.append("title 必填")
        if not payload.get("start"):
            errors.append("start 必填")
    return errors


def validate_event_update(payload: dict) -> list[str]:
    return validate_event_input(payload, partial=True)


def prepare_event(payload: dict, **defaults) -> tuple[dict | None, list[str]]:
    errors = validate_event_input(payload)
    if errors:
        return None, errors
    event = normalize_event({**defaults, **payload})
    if event is None:
        return None, ["start/end 无法规范化"]
    return event, []
