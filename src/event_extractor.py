"""Extract calendar events from QQ Mail messages."""
from __future__ import annotations

import datetime as dt
import json
import re
import urllib.request

from config_store import EMAIL_PROVIDERS, load_config
from logger import get_logger
from usage import record_usage

log = get_logger("event_extractor")


def build_email_url(uid: str) -> str:
    config = load_config()
    provider = config.get("email_provider") or "qq"
    mailbox_url = (
        config.get("mailbox_web_url")
        or EMAIL_PROVIDERS.get(provider, {}).get("mailbox_web_url")
        or ""
    ).strip()
    if mailbox_url:
        return mailbox_url
    return f"/api/emails/{uid}/raw"


def build_email_web_url(uid: str) -> str:
    """Return the provider mailbox home URL, not an unstable per-message sid URL."""
    config = load_config()
    provider = config.get("email_provider") or "qq"
    mailbox_url = (
        config.get("mailbox_web_url")
        or EMAIL_PROVIDERS.get(provider, {}).get("mailbox_web_url")
        or ""
    ).strip()
    return mailbox_url


def build_email_download_url(uid: str) -> str:
    return f"/api/emails/{uid}/raw"

TYPE_KEYWORDS = {
    "interview": ["面试", "邀约", "视频面", "面谈"],
    "assessment": ["测评", "笔试", "测验", "在线测试"],
    "event": ["宣讲会", "空宣", "直播", "线上活动", "讲座"],
    "meeting": ["会议", "周会", "评审", "例会"],
    "deadline": ["截止", "失效", "过期", "完成时间"],
}

TYPE_COLORS = {
    "interview": "#4f46e5",
    "assessment": "#e11d48",
    "event": "#d97706",
    "meeting": "#0d9488",
    "deadline": "#dc2626",
    "other": "#64748b",
}

NOISE_KEYWORDS = [
    "投递成功",
    "感谢应聘",
    "感谢关注",
    "简历更新",
    "绑定或更换",
    "验证码",
    "定价调整",
    "满意度问卷",
    "应聘结果反馈",
    "邀请您更新",
    "面试取消",
    "已取消",
    "简历完善",
    "\ufffd",
]

NON_ACTIONABLE_KEYWORDS = [
    "投递成功",
    "感谢投递",
    "感谢应聘",
    "感谢关注",
    "应聘结果",
    "简历已收到",
    "收到您的简历",
    "反馈通知",
    "简历投递成功",
    "申请已提交",
    "投递信息",
    "欢迎投递",
    "简历投递",
]

SUBJECT_NON_ACTIONABLE = [
    "投递成功",
    "感谢投递",
    "感谢应聘",
    "感谢关注",
    "简历已收到",
    "欢迎投递",
    "简历投递",
]

DATETIME_PATTERNS = [
    r"(?P<year>20\d{2})[-/年.](?P<month>\d{1,2})[-/月.](?P<day>\d{1,2})[日号]?\s*(?:T|[周星期天日]{1,3}\s*)?(?P<hour>\d{1,2})[:：](?P<minute>\d{2})",
    r"(?P<month>\d{1,2})[-/月.](?P<day>\d{1,2})[日号]?\s*(?:T|[周星期天日]{1,3}\s*)?(?P<hour>\d{1,2})[:：](?P<minute>\d{2})",
    r"(?P<year>20\d{2})年(?P<month>\d{1,2})月(?P<day>\d{1,2})日(?:\s*星期[一二三四五六日天])?\s*(?P<hour>\d{1,2})[:：](?P<minute>\d{2})",
    r"(?P<month>\d{1,2})月(?P<day>\d{1,2})日(?:\s*星期[一二三四五六日天])?\s*(?P<hour>\d{1,2})[:：](?P<minute>\d{2})",
    r"(?P<year>20\d{2})[-/年.](?P<month>\d{1,2})[-/月.](?P<day>\d{1,2})[日号]?",
    r"(?P<month>\d{1,2})[-/月.](?P<day>\d{1,2})[日号]?",
    r"(?P<year>20\d{2})年(?P<month>\d{1,2})月(?P<day>\d{1,2})日",
    r"(?P<month>\d{1,2})月(?P<day>\d{1,2})日",
]

CONTEXT_WORDS = [
    "截止",
    "失效",
    "过期",
    "时间",
    "面试",
    "测评",
    "笔试",
    "开始",
    "安排",
    "开播",
    "直播",
    "会议",
    "邀请",
    "生效",
    "进行",
    "完成",
]

LINK_RE = re.compile(r"https?://[^\s<>\"'）)\]]+")


def detect_type(text: str) -> str:
    for event_type in ("deadline", "assessment", "event", "interview", "meeting"):
        keywords = TYPE_KEYWORDS[event_type]
        if any(keyword in text for keyword in keywords):
            return event_type
    return "other"


def clean_title(subject: str, text: str) -> str:
    title = subject.strip()
    for prefix in ("【", "["):
        if title.startswith(prefix) and "]" in title:
            title = title.split("]", 1)[-1].strip("】 ")
    if not title:
        title = "新邮件安排"
    if len(title) > 28:
        title = title[:28].rstrip() + "…"
    return title


def summarize_title(subject: str, text: str) -> str:
    title = clean_title(subject, text)
    title = re.sub(r"【[^】]*[A-Za-z][^】]*】", "", title)
    title = re.sub(r"\[[^\]]*[A-Za-z][^\]]*\]", "", title)
    title = re.sub(r"[A-Za-z][A-Za-z0-9 .\-/_:]*$", "", title).strip()
    for suffix in (
        "邀请函",
        "邀请邮件",
        "投递成功反馈",
        "投递成功通知",
        "简历投递成功反馈",
        "感谢您的关注",
        "感谢您的应聘",
        "应聘反馈通知",
        "招聘通知",
        "通知",
        "提醒",
    ):
        if len(title) > len(suffix) + 4 and title.endswith(suffix):
            title = title[: -len(suffix)].rstrip("的 ：:，,.;；|/")
            break
    title = re.sub(r"\s+", " ", title).strip("【】[]()（） ：:，,;；|/")
    if len(title) > 24:
        title = title[:22].rstrip("，,；;：: ") + "…"
    return title or clean_title(subject, text)


def is_actionable(text: str) -> bool:
    action_keywords = (
            "测评",
            "笔试",
            "面试",
            "预约",
            "宣讲会",
            "空宣",
            "会议",
            "截止",
            "请完成",
            "需要完成",
            "完成时间",
            "参加",
            "作答",
            "提交",
        )
    if any(keyword in text for keyword in action_keywords):
        return True
    if any(keyword in text for keyword in NON_ACTIONABLE_KEYWORDS):
        return False
    return False


def classify_link(context: str) -> str:
    if any(keyword in context for keyword in ("测评", "笔试", "在线测试", "评估")):
        return "在线测评链接"
    if any(keyword in context for keyword in ("面试", "视频面试", "预约", "选择面试时间")):
        return "面试预约 / 视频面试链接"
    if any(keyword in context for keyword in ("宣讲会", "空宣", "直播", "直播间")):
        return "宣讲会 / 直播入口"
    if any(keyword in context for keyword in ("问卷", "survey", "反馈")):
        return "问卷链接"
    if any(keyword in context for keyword in ("投递", "官网", "职位", "岗位", "招聘官网")):
        return "投递 / 官网入口"
    return "邮件内链接"


def analyze_links(text: str) -> list[dict]:
    links = []
    seen = set()
    for match in LINK_RE.finditer(text):
        url = match.group(0).rstrip(".,;，。；、）")
        if url in seen:
            continue
        seen.add(url)
        context = text[max(0, match.start() - 36) : match.end() + 48].replace("\n", " ")
        links.append(
            {
                "url": url,
                "label": classify_link(context),
                "context": context[:160],
            }
        )
    return links


def parse_candidates(text: str, base_date: dt.date | None = None):
    """Return datetime candidates found in text with a simple regex sweep."""
    now = dt.datetime.now()
    if base_date is None:
        base_date = now.date()
    candidates = []

    for pattern in DATETIME_PATTERNS:
        for match in re.finditer(pattern, text):
            groups = match.groupdict()
            hour = int(groups.get("hour") or 0)
            minute = int(groups.get("minute") or 0)
            year = int(groups["year"]) if groups.get("year") else None
            month = int(groups["month"]) if groups.get("month") else None
            day = int(groups["day"]) if groups.get("day") else None
            try:
                if year and month and day:
                    value = dt.datetime(year, month, day, hour, minute)
                elif month and day:
                    value = dt.datetime(base_date.year, month, day, hour, minute)
                else:
                    value = dt.datetime(base_date.year, base_date.month, base_date.day, hour, minute)
                if value not in candidates:
                    candidates.append(value)
            except ValueError:
                continue

    relative_map = {"今天": 0, "今晚": 0, "明天": 1, "明日": 1, "后天": 2}
    for word, offset in relative_map.items():
        if word in text:
            time_match = re.search(rf"{word}[^\d]{{0,8}}(\d{{1,2}})[:：](\d{{2}})", text)
            hour = int(time_match.group(1)) if time_match else (20 if word == "今晚" else 9)
            minute = int(time_match.group(2)) if time_match else 0
            value = dt.datetime.combine(base_date + dt.timedelta(days=offset), dt.time(hour, minute))
            if value not in candidates:
                candidates.append(value)

    return candidates


def parse_contextual_candidates(text: str, base_date: dt.date | None = None):
    """Return only datetimes that appear near calendar-related keywords."""
    now = dt.datetime.now()
    if base_date is None:
        base_date = now.date()
    found = []

    for pattern in DATETIME_PATTERNS:
        for match in re.finditer(pattern, text):
            groups = match.groupdict()
            hour = int(groups.get("hour") or 0)
            minute = int(groups.get("minute") or 0)
            year = int(groups["year"]) if groups.get("year") else None
            month = int(groups["month"]) if groups.get("month") else None
            day = int(groups["day"]) if groups.get("day") else None
            context = text[max(0, match.start() - 18) : match.end() + 18]
            if not any(keyword in context for keyword in CONTEXT_WORDS):
                continue
            try:
                if year and month and day:
                    value = dt.datetime(year, month, day, hour, minute)
                elif month and day:
                    value = dt.datetime(base_date.year, month, day, hour, minute)
                else:
                    value = dt.datetime(base_date.year, base_date.month, base_date.day, hour, minute)
                if value not in found:
                    found.append(value)
            except ValueError:
                continue

    relative_map = {"今天": 0, "今晚": 0, "明天": 1, "明日": 1, "后天": 2}
    for word, offset in relative_map.items():
        if word not in text:
            continue
        time_match = re.search(rf"{word}[^\d]{{0,10}}(\d{{1,2}})[:：](\d{{2}})", text)
        hour = int(time_match.group(1)) if time_match else (20 if word == "今晚" else 9)
        minute = int(time_match.group(2)) if time_match else 0
        value = dt.datetime.combine(base_date + dt.timedelta(days=offset), dt.time(hour, minute))
        if value not in found:
            found.append(value)

    return found


def parse_duration_hours(text: str) -> int:
    match = re.search(r"(\d+)\s*(?:个)?\s*(小时|h|hr|hrs|天)", text, flags=re.IGNORECASE)
    if not match:
        return 0
    amount = int(match.group(1))
    unit = match.group(2).lower()
    if unit.startswith("天"):
        amount *= 24
    return amount


def estimate_event(message: dict, event_type: str, text: str) -> list[dict]:
    """Create a task anchored to the email date when action is required."""
    now = dt.datetime.now()
    try:
        received = dt.datetime.fromisoformat(str(message.get("date", "")))
        if received.tzinfo is not None:
            received = received.astimezone().replace(tzinfo=None)
    except ValueError:
        received = now

    base_date = received.date()
    if base_date < now.date() - dt.timedelta(days=30):
        return []
    if event_type == "interview" and not any(
        keyword in text for keyword in ("面试", "预约", "面谈", "视频面")
    ):
        return []
    if str(message.get("subject", "")).strip() == "新面试":
        return []

    has_72h = bool(re.search(r"72\s*小\s*时|72h|3\s*天\s*内|三\s*天\s*内", text))
    duration_hours = parse_duration_hours(text) or (72 if has_72h else 0)
    if duration_hours:
        start = received + dt.timedelta(hours=duration_hours)
        end = start + dt.timedelta(hours=1)
        all_day = False
        title_suffix = "截止（按邮件时间推算）"
    elif event_type == "deadline" or event_type == "assessment":
        start = received
        end = start + dt.timedelta(hours=1)
        all_day = False
        title_suffix = "测评/截止（按邮件时间）"
    elif event_type == "interview":
        start = received
        end = start + dt.timedelta(hours=1)
        all_day = False
        title_suffix = "面试/预约（按邮件时间）"
    elif event_type == "event":
        start = received
        end = start + dt.timedelta(hours=1)
        all_day = False
        title_suffix = "宣讲会/活动（按邮件时间）"
    elif event_type == "meeting":
        start = received
        end = start + dt.timedelta(hours=1)
        all_day = False
        title_suffix = "会议（按邮件时间）"
    else:
        return []

    title = summarize_title(message.get("subject", ""), text)
    if title_suffix not in title:
        title = f"{title}（{title_suffix}）"
    return [
        {
            "id": _stable_id(message.get("id", ""), title, start.isoformat()),
            "email_uid": str(message.get("id", "")),
            "email_url": build_email_url(message.get("id", "")),
            "email_web_url": build_email_web_url(message.get("id", "")),
            "email_download_url": build_email_download_url(message.get("id", "")),
            "title": title,
            "start": start.strftime("%Y-%m-%dT%H:%M:%S"),
            "end": end.strftime("%Y-%m-%dT%H:%M:%S"),
            "all_day": all_day,
            "type": event_type,
            "color": TYPE_COLORS[event_type],
            "source_subject": message.get("subject", ""),
            "source_from": message.get("from", ""),
            "description": text[:500],
            "status": "auto",
            "estimated": True,
            "date_source": "email_date",
            "source_body": str(message.get("body", ""))[:8000],
            "source_html": str(message.get("html", ""))[:200_000],
            "links": analyze_links(text),
        }
    ]


def extract_from_email(message: dict, base_date: dt.date | None = None) -> list[dict]:
    text = f"{message.get('subject', '')}\n{message.get('body', '')}"
    subject = str(message.get("subject", ""))
    if any(keyword in subject for keyword in SUBJECT_NON_ACTIONABLE):
        log.debug("submission-only subject skipped: %s", subject[:80])
        return []
    if any(keyword in text for keyword in NOISE_KEYWORDS):
        return []
    event_type = detect_type(text)
    if not is_actionable(text):
        log.debug("non-actionable email skipped: %s", message.get("subject", "")[:80])
        return []
    candidates = parse_contextual_candidates(text, base_date)
    if not candidates:
        estimated = estimate_event(message, event_type, text)
        if estimated:
            return estimated
        log.debug("no calendar candidates in email: %s", message.get("subject", "")[:80])
        return []

    color = TYPE_COLORS[event_type]
    title = summarize_title(message.get("subject", ""), text)
    now = dt.datetime.now()
    horizon = now + dt.timedelta(days=60)
    in_window = [
        c
        for c in candidates
        if now - dt.timedelta(hours=4) <= c <= horizon and (c.hour or c.minute)
    ]
    if not in_window:
        log.debug("candidates out of window: %s", message.get("subject", "")[:80])
        return []
    if event_type in ("deadline", "assessment"):
        selected = max(in_window)
    else:
        selected = min(in_window)
    end = selected + dt.timedelta(hours=1)

    deadline_match = re.search(r"截止(?:时间|日期)?[^\d]{0,8}(20\d{2}[-/年.].{0,18}?\d{1,2}[:：]\d{2})", text)
    if event_type == "deadline" and deadline_match:
        end = selected + dt.timedelta(hours=1)

    return [
        {
            "id": _stable_id(message.get("id", ""), title, selected.isoformat()),
            "email_uid": str(message.get("id", "")),
            "email_url": build_email_url(message.get("id", "")),
            "email_web_url": build_email_web_url(message.get("id", "")),
            "email_download_url": build_email_download_url(message.get("id", "")),
            "title": title,
            "start": selected.strftime("%Y-%m-%dT%H:%M:%S"),
            "end": end.strftime("%Y-%m-%dT%H:%M:%S"),
            "all_day": False,
            "type": event_type,
            "color": color,
            "source_subject": message.get("subject", ""),
            "source_from": message.get("from", ""),
            "description": text[:500],
            "status": "auto",
            "source_body": str(message.get("body", ""))[:8000],
            "source_html": str(message.get("html", ""))[:200_000],
            "links": analyze_links(text),
        }
    ]


def extract_with_model(messages: list[dict], model_config: dict) -> list[dict]:
    provider = model_config.get("provider") or "custom"
    if not model_config.get("enabled"):
        return []
    if not model_config.get("api_key") and provider != "ollama":
        return []
    api_base = (model_config.get("api_base") or "").rstrip("/")
    url = f"{api_base}/chat/completions"
    payload = {
        "model": model_config.get("model_name") or "gpt-4.1-mini",
        "temperature": 0.2,
        "messages": [
            {
                "role": "system",
                "content": (
                    "你是 MailCal 邮件日历事件提取器。事件时间是最高优先级字段，必须准确。"
                    "输入邮件已清洗为纯文本，不含 HTML。"
                    "先判断邮件类型：投递成功、感谢投递、感谢应聘、应聘反馈、验证码等仅通知邮件返回空 events。"
                    "对需要行动的邮件按场景处理："
                    "测评/笔试/截止类优先取邮件明确写出的截止时间；若邮件只写“请在24/72小时内完成”，"
                    "用该邮件 date 字段的时间加对应小时数推断截止时间。"
                    "面试/会议/宣讲会优先取邮件明确的开始时间；没有明确时间但需要预约/确认时，"
                    "使用该邮件 date 字段的日期作为 start。"
                    "title 必须精简到 20 字以内，保留公司/机构+事项类型，例如“平安银行测评”“小鹏AI测评”“快手面试预约”。"
                    '只返回严格 JSON，不要输出 Markdown 代码块，格式为 {"events":[{"title":"...",'
                    '"start":"YYYY-MM-DDTHH:MM:00","end":"YYYY-MM-DDTHH:MM:00",'
                    '"type":"interview|assessment|event|meeting|deadline|other"}]}。'
                    "start/end 使用 Asia/Shanghai 本地时间，不带时区后缀。"
                    '示例：{"events":[{"title":"平安银行测评","start":"2026-08-25T23:00:00","end":"2026-08-26T00:00:00","type":"assessment"}]}'
                ),
            },
            {
                "role": "user",
                "content": json.dumps(messages[:40], ensure_ascii=False),
            },
        ],
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {model_config['api_key']}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            result = json.loads(response.read().decode("utf-8"))
        events = result["choices"][0]["message"]["content"]
        usage = result.get("usage") or {}
        record_usage(
            provider=provider,
            model=model_config.get("model_name") or "unknown",
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            total_tokens=usage.get("total_tokens", 0),
        )
        parsed = json.loads(_strip_code_fence(events))
        log.info("model extracted %s events for %s", len(parsed.get("events", [])), provider)
        return parsed.get("events", [])
    except Exception as exc:
        log.warning("model extraction failed for %s: %s", provider, exc)
        return []


def _strip_code_fence(value: str) -> str:
    text = value.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:].strip()
    return text


def _stable_id(source_id: str, title: str, start: str) -> str:
    import hashlib

    raw = f"{source_id}|{title}|{start}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
