"""Read QQ Mail over IMAP and build calendar events."""
from __future__ import annotations

import datetime as dt
import email
import hashlib
import imaplib
import json
from email.header import decode_header, make_header
from email.utils import parsedate_to_datetime
from pathlib import Path

from config_store import ROOT
from event_normalizer import normalize_events
from event_extractor import extract_from_email
from file_io import atomic_write_json
from logger import get_logger
from model_agent import extract_events as agent_extract_events
from sync_cursor import load_cursor, save_cursor
from text_cleaner import clean_text as clean_email_text
from text_cleaner import html_to_text

DATA_PATH = ROOT / "data" / "events.json"
log = get_logger("mail_sync")


def decode_header_value(value) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return str(value)


def decode_payload(part) -> str:
    payload = part.get_payload(decode=True)
    if payload is None:
        return ""
    charset = part.get_content_charset() or "utf-8"
    try:
        return payload.decode(charset, errors="replace")
    except LookupError:
        return payload.decode("utf-8", errors="replace")


def get_text_body(msg) -> str:
    plain_parts = []
    html_parts = []
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                plain_parts.append(decode_payload(part))
            elif part.get_content_type() == "text/html":
                html_parts.append(decode_payload(part))
    else:
        content = decode_payload(msg)
        if msg.get_content_type() == "text/html":
            html_parts.append(content)
        else:
            plain_parts.append(content)

    plain_text = clean_email_text(" ".join(plain_parts)) if plain_parts else ""
    html_text = html_to_text(" ".join(html_parts)) if html_parts else ""
    if html_text and (
        not plain_text
        or len(plain_text) < 40
        or len(html_text) > len(plain_text) * 2
    ):
        return html_text
    return plain_text or html_text


def get_html_body(msg) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                return decode_payload(part)
    elif msg.get_content_type() == "text/html":
        return decode_payload(msg)
    return ""


def summarize(msg, message_id: bytes, max_body_chars: int) -> dict:
    try:
        received = parsedate_to_datetime(msg.get("Date"))
        date = received.astimezone().isoformat() if received else ""
    except Exception:
        date = msg.get("Date") or ""
    return {
        "id": message_id.decode(),
        "date": date,
        "from": decode_header_value(msg.get("From")),
        "to": decode_header_value(msg.get("To")),
        "subject": decode_header_value(msg.get("Subject")),
        "body": clean_email_text(get_text_body(msg))[:max_body_chars],
        "html": get_html_body(msg)[:200_000],
    }


def fetch_new_messages(config: dict, cursor: dict | None = None, limit: int | None = None) -> list[dict]:
    if not config.get("email") or not config.get("auth_code"):
        raise RuntimeError("邮箱或授权码未配置")
    conn = imaplib.IMAP4_SSL(config["imap_host"], int(config.get("imap_port", 993)))
    conn.login(config["email"], config["auth_code"])
    conn.select("INBOX", readonly=True)
    last_uid = int((cursor or {}).get("last_uid", 0) or 0)
    if last_uid:
        typ, data = conn.uid("search", None, f"{last_uid + 1}:*")
    else:
        typ, data = conn.uid("search", None, "ALL")
    if typ != "OK" or not data or not data[0]:
        conn.logout()
        return []
    ids = data[0].split()
    if not last_uid:
        ids = ids[-int(limit or config.get("fetch_limit", 50)) :]
    messages = []
    for uid in ids:
        typ, msg_data = conn.uid("fetch", uid, "(BODY.PEEK[])")
        if typ != "OK" or not msg_data:
            continue
        raw = None
        for part in msg_data:
            if isinstance(part, tuple):
                raw = part[1]
                break
        if raw is None:
            continue
        messages.append(summarize(email.message_from_bytes(raw), uid, 6000))
    conn.logout()
    log.debug("fetched %s new messages after uid %s", len(messages), last_uid)
    return messages


def fetch_mailbox_stats(config: dict) -> dict:
    if not config.get("email") or not config.get("auth_code"):
        return {"total": 0, "unread": 0}
    try:
        conn = imaplib.IMAP4_SSL(config["imap_host"], int(config.get("imap_port", 993)))
        conn.login(config["email"], config["auth_code"])
        typ, data = conn.select("INBOX", readonly=True)
        total = int(data[0]) if typ == "OK" and data and data[0] else 0
        typ, data = conn.search(None, "UNSEEN")
        unread = len(data[0].split()) if typ == "OK" and data and data[0] else 0
        conn.logout()
        return {"total": total, "unread": unread}
    except Exception as exc:
        log.warning("failed to fetch mailbox stats: %s", exc)
        return {"total": 0, "unread": 0, "error": str(exc)}


def fetch_raw_email(config: dict, uid: str) -> bytes:
    if not config.get("email") or not config.get("auth_code"):
        raise RuntimeError("邮箱或授权码未配置")
    conn = imaplib.IMAP4_SSL(config["imap_host"], int(config.get("imap_port", 993)))
    conn.login(config["email"], config["auth_code"])
    conn.select("INBOX", readonly=True)
    typ, msg_data = conn.uid("fetch", str(uid), "(BODY.PEEK[])")
    if typ != "OK" or not msg_data:
        conn.logout()
        raise RuntimeError("邮件不存在")
    raw = None
    for part in msg_data:
        if isinstance(part, tuple):
            raw = part[1]
            break
    conn.logout()
    if raw is None:
        raise RuntimeError("无法读取邮件")
    return raw


def merge_events(events: list[dict]) -> list[dict]:
    seen = {}
    for event in events:
        if not event.get("start"):
            continue
        source = (event.get("source_subject") or event.get("title") or "")[:48]
        key = hashlib.sha1(
            f"{source}|{event.get('start')}|{event.get('type')}".encode("utf-8")
        ).hexdigest()[:16]
        event["id"] = key
        seen[key] = event
    return sorted(seen.values(), key=lambda e: e.get("start", ""))


def sync_events(config: dict, progress_callback=None) -> dict:
    cursor = load_cursor()
    if progress_callback:
        progress_callback("fetching", 2, "正在连接邮箱")
    messages = fetch_new_messages(config, cursor)
    if progress_callback:
        progress_callback("fetching", 20, f"获取到 {len(messages)} 封新邮件")
    existing_events = []
    if DATA_PATH.exists():
        try:
            existing_events = json.loads(DATA_PATH.read_text(encoding="utf-8")).get("events", [])
        except (json.JSONDecodeError, OSError):
            existing_events = []

    log.info("syncing %s new messages after uid %s", len(messages), cursor.get("last_uid", 0))
    raw_events = []
    model_events = []
    for index, message in enumerate(messages, start=1):
        if progress_callback:
            progress_callback(
                "processing",
                20 + int(index / max(len(messages), 1) * 50),
                f"清洗 {index}/{len(messages)}：{message.get('subject', '')[:40]}",
            )
        log.info(
            "processing email %s/%s: %s",
            index,
            len(messages),
            message.get("subject", "")[:60],
        )
        raw_events.extend(extract_from_email(message))

    if messages and config.get("model", {}).get("enabled"):
        if progress_callback:
            progress_callback("model_extract", 72, "模型提取事件中")
        model_events = agent_extract_events(messages, config["model"])
        for event in model_events:
            event.setdefault("type", "other")
            event.setdefault("color", "#64748b")
            event.setdefault("status", "auto")
            event["source_subject"] = "AI 提取"
            event["source_from"] = ""

    events = normalize_events(existing_events + raw_events + model_events)
    events = merge_events(events)

    retention_days = int((config.get("cache") or {}).get("event_retention_days", 30) or 30)
    cutoff = (dt.datetime.now() - dt.timedelta(days=retention_days)).strftime("%Y-%m-%dT%H:%M:%S")
    events = [e for e in events if (e.get("start") or "") >= cutoff]

    for event in events:
        event.setdefault("status", "auto")

    if progress_callback:
        progress_callback("saving", 90, "写入事件文件")
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(
        DATA_PATH,
        {
            "updated_at": dt.datetime.now().astimezone().isoformat(),
            "events": events,
            "email": config.get("email", ""),
        },
    )
    if messages:
        last_message = messages[-1]
        save_cursor(
            last_uid=int(last_message.get("id") or 0),
            synced_count=cursor.get("synced_count", 0) + len(messages),
            last_email_id=last_message.get("id", ""),
            last_date=last_message.get("date", ""),
        )
    if progress_callback:
        progress_callback("done", 100, "同步完成")
    return {
        "updated_at": dt.datetime.now().astimezone().isoformat(),
        "events": events,
        "new_messages": len(messages),
        "cursor": load_cursor(),
    }
