"""MCP server for the MailCal app.

Run with stdio (default) or streamable HTTP:

    python src/mcp_server.py
    python src/mcp_server.py --http --port 5174
"""
from __future__ import annotations

import argparse
import json
import sys

from config_store import ensure_config_file, load_config, mask_config
from event_normalizer import parse_datetime
from event_status import decorate
from event_validation import validate_event_update
from event_validation import prepare_event
from mail_sync import DATA_PATH, sync_events
from model_catalog import fetch_available_models
from sync_cursor import load_cursor, reset_cursor
from usage import reset_usage, summarize

from mcp.server import MCPServer

server = MCPServer(
    "mailcal-mcp",
    title="MailCal MCP",
    version="0.1.0",
    instructions="Read QQ Mail, list calendar events, add events, and trigger email sync.",
)


def read_events() -> list[dict]:
    if not DATA_PATH.exists():
        return []
    try:
        data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
        return data.get("events", [])
    except (json.JSONDecodeError, OSError):
        return []


def write_events(events: list[dict]) -> None:
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    DATA_PATH.write_text(
        json.dumps({"updated_at": "", "events": events}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


@server.tool(
    name="list_events",
    description="List calendar events. start_date and end_date are optional ISO datetimes; end_date must be after start_date.",
)
def list_events(start_date: str = "", end_date: str = "") -> dict:
    start = parse_datetime(start_date)
    end = parse_datetime(end_date)
    if start_date and start is None:
        return {"ok": False, "message": "start_date 必须是可解析的 ISO 时间"}
    if end_date and end is None:
        return {"ok": False, "message": "end_date 必须是可解析的 ISO 时间"}
    if start and end and end <= start:
        return {"ok": False, "message": "end_date 必须晚于 start_date"}
    start_value = start.strftime("%Y-%m-%dT%H:%M:%S") if start else ""
    end_value = end.strftime("%Y-%m-%dT%H:%M:%S") if end else ""
    events = read_events()
    if start_value:
        events = [e for e in events if e.get("start", "") >= start_value]
    if end_value:
        events = [e for e in events if e.get("start", "") <= end_value]
    return {"events": decorate(events)}


@server.tool(name="get_event", description="Get one calendar event by non-empty id, including current status.")
def get_event(event_id: str) -> dict:
    if not event_id:
        return {"ok": False, "message": "event_id 必填"}
    event = next((e for e in read_events() if e.get("id") == event_id), None)
    if not event:
        return {"ok": False, "message": "event not found"}
    return {"event": decorate([event])[0]}


@server.tool(name="sync_emails", description="Read the configured email inbox and refresh calendar events.")
def sync_emails() -> dict:
    try:
        return sync_events(load_config())
    except Exception as exc:
        return {"ok": False, "message": str(exc)}


@server.tool(name="list_models", description="List available models from the configured provider API.")
def list_models() -> dict:
    return fetch_available_models(load_config(), refresh=True)


@server.tool(name="get_status", description="Return masked account config, event count, and data file path.")
def get_status() -> dict:
    events = read_events()
    return {
        "config": mask_config(load_config()),
        "event_count": len(events),
        "data_path": str(DATA_PATH),
        "sync_cursor": load_cursor(),
    }


@server.tool(name="reset_sync_cursor", description="Reset the mailbox sync cursor to reprocess recent email.")
def reset_sync_cursor() -> dict:
    return reset_cursor()


@server.tool(name="get_usage", description="Return model token usage and estimated cost, grouped by model.")
def get_usage() -> dict:
    return summarize()


@server.tool(name="reset_usage", description="Reset all model token usage statistics.")
def reset_usage_tool() -> dict:
    return reset_usage()


@server.tool(
    name="add_event",
    description="Add a calendar event. title and start are required; end must be after start; type and status use fixed enums.",
)
def add_event(
    title: str,
    start: str,
    end: str = "",
    event_type: str = "other",
    description: str = "",
    status: str = "auto",
) -> dict:
    event, errors = prepare_event(
        {
            "title": title,
            "start": start,
            "end": end,
            "type": event_type,
            "description": description,
            "status": status,
        },
        source_subject="MCP 调用",
        source_from="",
    )
    if event is None:
        return {"ok": False, "message": "; ".join(errors), "errors": errors}
    events = read_events()
    events.append(
        {
            "id": f"mcp-{len(events)}-{start}",
            **event,
        }
    )
    events.sort(key=lambda e: e.get("start", ""))
    write_events(events)
    return {"ok": True, "events": decorate(events)}


@server.tool(
    name="update_event",
    description="Update an existing calendar event by id. Provide at least one updatable field.",
)
def update_event(
    event_id: str,
    title: str = "",
    start: str = "",
    end: str = "",
    event_type: str = "",
    description: str = "",
    status: str = "",
) -> dict:
    updates = {
        key: value
        for key, value in {
            "title": title,
            "start": start,
            "end": end,
            "type": event_type,
            "description": description,
            "status": status,
        }.items()
        if value
    }
    if not updates:
        return {"ok": False, "message": "至少提供一个要更新的字段"}
    errors = validate_event_update(updates)
    if errors:
        return {"ok": False, "message": "; ".join(errors), "errors": errors}
    events = read_events()
    target = next((e for e in events if e.get("id") == event_id), None)
    if not target:
        return {"ok": False, "message": "event not found"}
    candidate = {**target, **updates}
    event, errors = prepare_event(candidate)
    if event is None:
        return {"ok": False, "message": "; ".join(errors), "errors": errors}
    event["id"] = target["id"]
    events.sort(key=lambda e: e.get("start", ""))
    events = [event if e.get("id") == event["id"] else e for e in events]
    write_events(events)
    return {"ok": True, "event": decorate([event])[0]}


@server.tool(name="delete_event", description="Delete a calendar event by non-empty id.")
def delete_event(event_id: str) -> dict:
    if not event_id:
        return {"ok": False, "message": "event_id 必填"}
    events = [e for e in read_events() if e.get("id") != event_id]
    write_events(events)
    return {"ok": True, "events": decorate(events)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--http", action="store_true", help="Run streamable HTTP MCP server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5174)
    args = parser.parse_args()

    ensure_config_file()
    if args.http:
        import anyio

        async def run_http():
            await server.run_streamable_http_async(host=args.host, port=args.port)

        print(f"MCP HTTP server listening on http://{args.host}:{args.port}/mcp")
        anyio.run(run_http)
    else:
        import anyio

        anyio.run(server.run_stdio_async)
    return 0


if __name__ == "__main__":
    sys.exit(main())
