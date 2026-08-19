"""Local web app that serves the MailCal UI and APIs."""
from __future__ import annotations

import datetime as dt
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from config_store import ROOT, ensure_config_file, get_meta, load_config, mask_config, merge_config, save_config, validate_config
from event_status import decorate
from event_validation import prepare_event, validate_event_update
from file_io import atomic_write_json
from logger import LOG_FILE, cleanup_logs, clear_logs, get_logger, setup_logging
from mail_sync import DATA_PATH, fetch_mailbox_stats, fetch_raw_email, sync_events
from model_catalog import clear_cache, fetch_available_models
from sync_cursor import load_cursor, reset_cursor
from usage import reset_usage, summarize

STATIC_DIR = ROOT / "static"
SYNC_LOCK = threading.Lock()
LAST_SYNC = {"time": None, "status": "idle", "message": ""}
SYNC_PROGRESS = {
    "status": "idle",
    "stage": "idle",
    "progress": 0,
    "message": "",
    "started_at": "",
    "updated_at": "",
}
log = get_logger("app")


def run_sync() -> dict:
    if not SYNC_LOCK.acquire(blocking=False):
        log.info("sync already in progress, skipping duplicate request")
        return {"ok": True, "busy": True, "message": "同步已在进行中"}
    try:
        config = load_config()
        SYNC_PROGRESS.update(
            {
                "status": "running",
                "stage": "starting",
                "progress": 0,
                "message": "准备同步",
                "started_at": dt.datetime.now().astimezone().isoformat(),
                "updated_at": dt.datetime.now().astimezone().isoformat(),
            }
        )
        log.info("email sync started")
        def progress_callback(stage, progress, message):
            SYNC_PROGRESS.update(
                {
                    "status": "running",
                    "stage": stage,
                    "progress": progress,
                    "message": message,
                    "updated_at": dt.datetime.now().astimezone().isoformat(),
                }
            )

        result = sync_events(config, progress_callback)
        LAST_SYNC.update({"time": result["updated_at"], "status": "ok", "message": "同步完成"})
        SYNC_PROGRESS.update(
            {
                "status": "done",
                "stage": "done",
                "progress": 100,
                "message": "同步完成",
                "updated_at": dt.datetime.now().astimezone().isoformat(),
            }
        )
        log.info("email sync finished with %s events", len(result.get("events", [])))
        return {"ok": True, **result}
    except Exception as exc:
        log.exception("email sync failed")
        LAST_SYNC.update({"status": "error", "message": str(exc)})
        SYNC_PROGRESS.update(
            {
                "status": "error",
                "stage": "error",
                "message": str(exc),
                "updated_at": dt.datetime.now().astimezone().isoformat(),
            }
        )
        return {"ok": False, "message": str(exc)}
    finally:
        SYNC_LOCK.release()


def auto_sync_loop():
    interval = 1800
    while True:
        try:
            config = load_config()
            interval = max(60, int(config.get("sync_interval_minutes", 30)) * 60)
            if config.get("auto_sync") and config.get("email"):
                run_sync()
        except Exception:
            pass
        time.sleep(interval)


def read_events() -> list[dict]:
    if not DATA_PATH.exists():
        return []
    try:
        data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
        return data.get("events", [])
    except (json.JSONDecodeError, OSError):
        return []


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        return

    def _json(self, status: int, payload: dict):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-API-Token")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, PATCH, DELETE, OPTIONS")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def _serve_static(self, path: str):
        relative = path.lstrip("/") or "index.html"
        candidate = (STATIC_DIR / relative).resolve()
        if not str(candidate).startswith(str(STATIC_DIR.resolve())):
            self.send_error(403)
            return
        if not candidate.exists() or not candidate.is_file():
            self.send_error(404)
            return
        content_type = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
            ".png": "image/png",
            ".svg": "image/svg+xml",
            ".ico": "image/x-icon",
        }.get(candidate.suffix.lower(), "application/octet-stream")
        body = candidate.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        refresh = "refresh=1" in self.path
        log.debug("GET %s", path)
        if path == "/api/health":
            self._json(200, {"ok": True, "service": "mailcal"})
        elif path == "/api/openapi.json":
            self._json(
                200,
                {
                    "openapi": "3.0.0",
                    "info": {"title": "MailCal API", "version": "0.1.0"},
                    "paths": {
                        "/api/state": {"get": {"summary": "Get config, events, and sync status"}},
                        "/api/events": {"get": {"summary": "List events"}},
                        "/api/events/{id}": {"get": {"summary": "Get one event"}},
                        "/api/models": {"get": {"summary": "Get available models from provider"}},
                        "/api/sync": {"post": {"summary": "Trigger QQ Mail sync"}},
                        "/api/config": {"post": {"summary": "Update configuration"}},
                        "/api/export.ics": {"get": {"summary": "Download ICS calendar"}},
                        "/api/usage": {"get": {"summary": "Get model token usage and cost"}},
                        "/api/admin/stats": {"get": {"summary": "Get admin overview stats"}},
                        "/api/admin/logs": {"get": {"summary": "Get recent application logs"}},
                    },
                },
            )
        elif path == "/api/state":
            events = read_events()
            self._json(
                200,
                {
                    "config": mask_config(load_config()),
                    "events": decorate(events),
                    "sync": LAST_SYNC,
                    "sync_progress": SYNC_PROGRESS,
                    "sync_cursor": load_cursor(),
                    "data_path": str(DATA_PATH),
                    "usage": summarize(),
                    "meta": get_meta(),
                },
            )
        elif path == "/api/events":
            self._json(200, {"events": decorate(read_events())})
        elif path.startswith("/api/events/"):
            event_id = path.rsplit("/", 1)[-1]
            event = next((e for e in read_events() if e.get("id") == event_id), None)
            if event:
                self._json(200, {"event": decorate([event])[0]})
            else:
                self._json(404, {"ok": False, "message": "event not found"})
        elif path == "/api/usage":
            self._json(200, summarize())
        elif path == "/api/models":
            self._json(200, fetch_available_models(load_config(), refresh=refresh))
        elif path == "/api/admin/stats":
            config = load_config()
            self._json(
                200,
                {
                    "mailbox": fetch_mailbox_stats(config),
                    "events": len(read_events()),
                    "cursor": load_cursor(),
                    "usage": summarize(),
                    "sync": LAST_SYNC,
                    "cache": load_config().get("cache", {}),
                },
            )
        elif path == "/api/admin/logs":
            try:
                lines = int(self.path.split("lines=", 1)[1].split("&", 1)[0]) if "lines=" in self.path else 200
            except (ValueError, IndexError):
                lines = 200
            level_filter = ""
            if "level=" in self.path:
                level_filter = self.path.split("level=", 1)[1].split("&", 1)[0].upper()
            log_lines = []
            if LOG_FILE.exists():
                log_lines = LOG_FILE.read_text(encoding="utf-8").splitlines()[-lines:]
            rows = []
            for line in log_lines:
                parts = line.split(" | ", 3)
                if len(parts) == 4:
                    row = {
                        "time": parts[0].strip(),
                        "level": parts[1].strip(),
                        "module": parts[2].strip(),
                        "message": parts[3].strip(),
                    }
                else:
                    row = {"time": "", "level": "", "module": "", "message": line}
                if level_filter and row["level"] != level_filter:
                    continue
                rows.append(row)
            self._json(200, {"lines": log_lines, "rows": rows, "path": str(LOG_FILE)})
        elif path.startswith("/api/emails/") and path.endswith("/raw"):
            try:
                uid = path.split("/api/emails/", 1)[1].split("/", 1)[0]
                raw = fetch_raw_email(load_config(), uid)
                self.send_response(200)
                self.send_header("Content-Type", "message/rfc822")
                self.send_header("Content-Disposition", f'inline; filename="{uid}.eml"')
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
            except Exception as exc:
                self._json(400, {"ok": False, "message": str(exc)})
        elif path == "/api/export.ics":
            self._export_ics()
        else:
            self._serve_static(path)

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        log.debug("POST %s", path)
        if path == "/api/config":
            try:
                payload = self._read_json()
                if not payload.get("auth_code"):
                    payload.pop("auth_code", None)
                model_payload = payload.get("model")
                if isinstance(model_payload, dict) and not model_payload.get("api_key"):
                    model_payload.pop("api_key", None)
                merged = merge_config(payload)
                errors = validate_config(merged)
                if errors:
                    self._json(400, {"ok": False, "message": "; ".join(errors)})
                    return
                save_config(merged)
                setup_logging(merged.get("log_level", "INFO"))
                self._json(200, {"ok": True, "config": mask_config(merged)})
            except Exception as exc:
                self._json(400, {"ok": False, "message": str(exc)})
        elif path == "/api/sync":
            result = run_sync()
            self._json(200 if result.get("ok") else 500, result)
        elif path == "/api/models":
            try:
                payload = self._read_json()
                config = load_config()
                if payload.get("model"):
                    for key, value in payload["model"].items():
                        if value not in (None, ""):
                            config["model"][key] = value
                self._json(200, fetch_available_models(config, refresh=True))
            except Exception as exc:
                self._json(400, {"ok": False, "message": str(exc)})
        elif path == "/api/admin/clear":
            try:
                payload = self._read_json()
                target = payload.get("target", "all")
                result = {}
                if target in ("models", "all"):
                    result["models"] = clear_cache()
                if target in ("logs", "all"):
                    result["logs"] = clear_logs()
                if target in ("usage", "all"):
                    result["usage"] = reset_usage()
                if target in ("cursor", "all"):
                    result["cursor"] = reset_cursor()
                if target in ("events", "all"):
                    atomic_write_json(DATA_PATH, {"updated_at": "", "events": []})
                    result["events"] = True
                if target in ("expired", "all"):
                    cache_cfg = load_config().get("cache", {})
                    result["models"] = clear_cache()
                    result["logs"] = cleanup_logs(cache_cfg.get("log_retention_days", 7))
                    retention_days = int(cache_cfg.get("event_retention_days", 30))
                    cutoff = (
                        dt.datetime.now() - dt.timedelta(days=retention_days)
                    ).strftime("%Y-%m-%dT%H:%M:%S")
                    events = read_events()
                    kept = [e for e in events if (e.get("start") or "") >= cutoff]
                    atomic_write_json(DATA_PATH, {"updated_at": "", "events": kept})
                    result["events_removed"] = len(events) - len(kept)
                self._json(200, {"ok": True, **result})
            except Exception as exc:
                self._json(400, {"ok": False, "message": str(exc)})
        elif path == "/api/events":
            try:
                payload = self._read_json()
                event, errors = prepare_event(
                    payload,
                    source_subject="手动添加",
                    source_from="",
                )
                if event is None:
                    self._json(400, {"ok": False, "message": "; ".join(errors), "errors": errors})
                    return
                events = read_events()
                events.append(
                    {
                        "id": f"manual-{int(time.time() * 1000)}",
                        **event,
                        "color": payload.get("color") or "#0f766e",
                    }
                )
                events.sort(key=lambda e: e.get("start", ""))
                atomic_write_json(DATA_PATH, {"updated_at": "", "events": events})
                self._json(200, {"ok": True, "events": events})
            except Exception as exc:
                self._json(400, {"ok": False, "message": str(exc)})
        else:
            self._json(404, {"ok": False, "message": "not found"})

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-API-Token")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, PATCH, DELETE, OPTIONS")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_PUT(self):
        path = self.path.split("?", 1)[0]
        log.debug("PUT %s", path)
        if path != "/api/events":
            self._json(404, {"ok": False, "message": "not found"})
            return
        try:
            payload = self._read_json()
            updates = {
                key: payload[key]
                for key in ("title", "start", "end", "type", "color", "description", "status")
                if key in payload and payload[key] is not None
            }
            if not updates:
                self._json(400, {"ok": False, "message": "至少提供一个要更新的字段"})
                return
            errors = validate_event_update(updates)
            if errors:
                self._json(400, {"ok": False, "message": "; ".join(errors), "errors": errors})
                return
            events = read_events()
            target = next((e for e in events if e.get("id") == payload.get("id")), None)
            if not target:
                self._json(404, {"ok": False, "message": "event not found"})
                return
            candidate = {**target, **updates}
            event, errors = prepare_event(candidate)
            if event is None:
                self._json(400, {"ok": False, "message": "; ".join(errors), "errors": errors})
                return
            event["id"] = target["id"]
            if "color" in updates:
                event["color"] = updates["color"]
            events.sort(key=lambda e: e.get("start", ""))
            events = [event if e.get("id") == event["id"] else e for e in events]
            atomic_write_json(DATA_PATH, {"updated_at": "", "events": events})
            self._json(200, {"ok": True, "event": event})
        except Exception as exc:
            self._json(400, {"ok": False, "message": str(exc)})

    def do_PATCH(self):
        self.do_PUT()

    def do_DELETE(self):
        path = self.path.split("?", 1)[0]
        log.debug("DELETE %s", path)
        if path == "/api/events":
            try:
                event_id = self._read_json().get("id")
                events = [e for e in read_events() if e.get("id") != event_id]
                atomic_write_json(DATA_PATH, {"updated_at": "", "events": events})
                self._json(200, {"ok": True, "events": events})
            except Exception as exc:
                self._json(400, {"ok": False, "message": str(exc)})
        elif path == "/api/usage":
            self._json(200, reset_usage())
        elif path == "/api/sync-cursor":
            self._json(200, {"ok": True, "cursor": reset_cursor()})
        else:
            self._json(404, {"ok": False, "message": "not found"})

    def _export_ics(self):
        lines = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//MailCal//CN",
            "CALSCALE:GREGORIAN",
        ]
        for event in read_events():
            start = event.get("start", "")
            end = event.get("end", "")
            if not start:
                continue
            lines.append("BEGIN:VEVENT")
            lines.append(f"UID:{event.get('id', start)}@mailcal")
            lines.append(f"DTSTART;TZID=Asia/Shanghai:{start.replace('-', '').replace(':', '').replace('T', 'T')}")
            lines.append(f"DTEND;TZID=Asia/Shanghai:{end.replace('-', '').replace(':', '').replace('T', 'T')}")
            lines.append(f"SUMMARY:{event.get('title', '')}".replace("\n", " "))
            if event.get("description"):
                lines.append(f"DESCRIPTION:{event['description'][:200]}".replace("\n", " "))
            lines.append("END:VEVENT")
        lines.append("END:VCALENDAR")
        body = ("\r\n".join(lines) + "\r\n").encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/calendar; charset=utf-8")
        self.send_header("Content-Disposition", 'attachment; filename="calendar.ics"')
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="MailCal web app")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5173)
    args = parser.parse_args()

    ensure_config_file()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    setup_logging(load_config().get("log_level", "INFO"))
    log.info("MailCal running at http://%s:%s", args.host, args.port)
    print(f"MailCal running at http://{args.host}:{args.port}")
    threading.Thread(target=auto_sync_loop, daemon=True).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main()
