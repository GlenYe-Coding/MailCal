"""Local configuration helpers for the MailCal app."""
from __future__ import annotations

import json
import os
from pathlib import Path

from file_io import atomic_write_json

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config.json"

DEFAULTS = {
    "email_provider": "qq",
    "email": "",
    "auth_code": "",
    "imap_host": "imap.qq.com",
    "imap_port": 993,
    "mailbox_web_url": "",
    "fetch_limit": 50,
    "auto_sync": True,
    "sync_interval_minutes": 30,
    "log_level": "INFO",
    "cache": {
        "model_cache_ttl_hours": 24,
        "log_retention_days": 7,
        "event_retention_days": 30,
        "cleanup_interval_hours": 24,
    },
    "model": {
        "enabled": False,
        "provider": "openai",
        "api_base": "https://api.openai.com/v1",
        "api_key": "",
        "model_name": "gpt-4.1-mini",
    },
}


def _load_dotenv() -> None:
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _env_overrides() -> dict:
    mapping = {
        "email_provider": "EMAIL_CALENDAR_EMAIL_PROVIDER",
        "email": "EMAIL_CALENDAR_EMAIL",
        "auth_code": "EMAIL_CALENDAR_AUTH_CODE",
        "imap_host": "EMAIL_CALENDAR_IMAP_HOST",
        "imap_port": "EMAIL_CALENDAR_IMAP_PORT",
        "mailbox_web_url": "EMAIL_CALENDAR_MAILBOX_WEB_URL",
        "fetch_limit": "EMAIL_CALENDAR_FETCH_LIMIT",
        "auto_sync": "EMAIL_CALENDAR_AUTO_SYNC",
        "sync_interval_minutes": "EMAIL_CALENDAR_SYNC_INTERVAL_MINUTES",
        "log_level": "EMAIL_CALENDAR_LOG_LEVEL",
    }
    result = {}
    for key, env in mapping.items():
        value = os.getenv(env)
        if value is None:
            continue
        if key in ("imap_port", "fetch_limit", "sync_interval_minutes"):
            result[key] = int(value)
        elif key == "auto_sync":
            result[key] = value.lower() in ("1", "true", "yes", "on")
        else:
            result[key] = value

    model_env = {
        "enabled": "EMAIL_CALENDAR_MODEL_ENABLED",
        "provider": "EMAIL_CALENDAR_MODEL_PROVIDER",
        "api_base": "EMAIL_CALENDAR_MODEL_API_BASE",
        "api_key": "EMAIL_CALENDAR_MODEL_API_KEY",
        "model_name": "EMAIL_CALENDAR_MODEL_NAME",
    }
    model = {}
    for key, env in model_env.items():
        value = os.getenv(env)
        if value is None:
            continue
        if key == "enabled":
            model[key] = value.lower() in ("1", "true", "yes", "on")
        else:
            model[key] = value
    if model:
        result["model"] = model

    cache_env = {
        "model_cache_ttl_hours": "EMAIL_CALENDAR_MODEL_CACHE_TTL_HOURS",
        "log_retention_days": "EMAIL_CALENDAR_LOG_RETENTION_DAYS",
        "event_retention_days": "EMAIL_CALENDAR_EVENT_RETENTION_DAYS",
        "cleanup_interval_hours": "EMAIL_CALENDAR_CLEANUP_INTERVAL_HOURS",
    }
    cache = {}
    for key, env in cache_env.items():
        value = os.getenv(env)
        if value is not None:
            cache[key] = int(value)
    if cache:
        result["cache"] = cache
    return result


_load_dotenv()

EMAIL_PROVIDERS = {
    "qq": {
        "label": "QQ 邮箱",
        "imap_host": "imap.qq.com",
        "imap_port": 993,
        "mailbox_web_url": "https://mail.qq.com/",
        "auth_hint": "登录 QQ 邮箱网页版，设置 → 账号 → 开启 IMAP/SMTP，获取授权码",
    },
    "163": {
        "label": "163 邮箱",
        "imap_host": "imap.163.com",
        "imap_port": 993,
        "mailbox_web_url": "https://mail.163.com/",
        "auth_hint": "在 163 邮箱设置中开启 IMAP/SMTP，使用客户端授权码",
    },
    "126": {
        "label": "126 邮箱",
        "imap_host": "imap.126.com",
        "imap_port": 993,
        "mailbox_web_url": "https://mail.126.com/",
        "auth_hint": "在 126 邮箱设置中开启 IMAP/SMTP，使用客户端授权码",
    },
    "gmail": {
        "label": "Gmail",
        "imap_host": "imap.gmail.com",
        "imap_port": 993,
        "mailbox_web_url": "https://mail.google.com/",
        "auth_hint": "开启两步验证后，使用 Google 应用专用密码",
    },
    "outlook": {
        "label": "Outlook / Office 365",
        "imap_host": "outlook.office365.com",
        "imap_port": 993,
        "mailbox_web_url": "https://outlook.live.com/mail/0/",
        "auth_hint": "使用 Outlook 邮箱密码，或已开启两步验证的应用密码",
    },
    "sina": {
        "label": "新浪邮箱",
        "imap_host": "imap.sina.com",
        "imap_port": 993,
        "mailbox_web_url": "https://mail.sina.com.cn/",
        "auth_hint": "在新浪邮箱设置中开启 IMAP/SMTP 服务",
    },
    "sohu": {
        "label": "搜狐邮箱",
        "imap_host": "imap.sohu.com",
        "imap_port": 993,
        "mailbox_web_url": "https://mail.sohu.com/",
        "auth_hint": "在搜狐邮箱设置中开启 IMAP/SMTP 服务",
    },
    "icloud": {
        "label": "iCloud Mail",
        "imap_host": "imap.mail.me.com",
        "imap_port": 993,
        "mailbox_web_url": "https://www.icloud.com/mail/",
        "auth_hint": "在 Apple ID 中生成 App 专用密码，邮箱填 iCloud 邮箱",
    },
    "custom": {
        "label": "自定义 IMAP",
        "imap_host": "",
        "imap_port": 993,
        "mailbox_web_url": "",
        "auth_hint": "填写你的 IMAP 服务器、端口和认证密码",
    },
}

MODEL_PROVIDERS = {
    "openai": {
        "label": "OpenAI",
        "api_base": "https://api.openai.com/v1",
        "needs_key": True,
        "pricing": {
            "gpt-4.1-mini": {"input": 0.4, "output": 1.6},
            "gpt-4.1": {"input": 2.0, "output": 8.0},
            "gpt-4o-mini": {"input": 0.15, "output": 0.6},
            "o4-mini": {"input": 1.1, "output": 4.4},
        },
        "models": ["gpt-4.1-mini", "gpt-4.1", "gpt-4o-mini", "o4-mini"],
    },
    "deepseek": {
        "label": "DeepSeek",
        "api_base": "https://api.deepseek.com/v1",
        "needs_key": True,
        "pricing": {
            "deepseek-chat": {"input": 0.27, "output": 1.1},
            "deepseek-reasoner": {"input": 0.55, "output": 2.19},
            "default": {"input": 0.27, "output": 1.1},
        },
        "models": ["deepseek-chat", "deepseek-reasoner"],
    },
    "moonshot": {
        "label": "Moonshot Kimi",
        "api_base": "https://api.moonshot.cn/v1",
        "needs_key": True,
        "pricing": {
            "moonshot-v1-8k": {"input": 12.0, "output": 12.0},
            "moonshot-v1-32k": {"input": 24.0, "output": 24.0},
            "kimi-k2-0711-preview": {"input": 4.0, "output": 16.0},
            "default": {"input": 12.0, "output": 12.0},
        },
        "models": ["moonshot-v1-8k", "moonshot-v1-32k", "kimi-k2-0711-preview"],
    },
    "zhipu": {
        "label": "智谱 GLM",
        "api_base": "https://open.bigmodel.cn/api/paas/v4",
        "needs_key": True,
        "pricing": {
            "glm-4-plus": {"input": 2.0, "output": 6.0},
            "glm-4-flash": {"input": 0.0, "output": 0.0},
            "glm-4-air": {"input": 0.5, "output": 1.5},
            "default": {"input": 1.0, "output": 3.0},
        },
        "models": ["glm-4-plus", "glm-4-flash", "glm-4-air"],
    },
    "qwen": {
        "label": "阿里云百炼 Qwen",
        "api_base": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "needs_key": True,
        "pricing": {
            "qwen-turbo": {"input": 0.3, "output": 0.6},
            "qwen-plus": {"input": 0.8, "output": 2.0},
            "qwen-max": {"input": 2.4, "output": 9.6},
            "qwen3": {"input": 1.0, "output": 3.0},
            "default": {"input": 0.8, "output": 2.0},
        },
        "models": ["qwen-plus", "qwen-turbo", "qwen-max", "qwen3"],
    },
    "siliconflow": {
        "label": "硅基流动 SiliconFlow",
        "api_base": "https://api.siliconflow.cn/v1",
        "needs_key": True,
        "pricing": {
            "default": {"input": 0.2, "output": 0.6},
        },
        "models": [
            "Qwen/Qwen2.5-7B-Instruct",
            "deepseek-ai/DeepSeek-V3",
            "THUDM/glm-4-9b-chat",
        ],
    },
    "ollama": {
        "label": "Ollama 本地",
        "api_base": "http://127.0.0.1:11434/v1",
        "needs_key": False,
        "pricing": {
            "default": {"input": 0.0, "output": 0.0},
        },
        "models": ["llama3.1", "qwen2.5", "deepseek-r1", "gemma2"],
    },
    "custom": {
        "label": "自定义 OpenAI 兼容",
        "api_base": "",
        "needs_key": True,
        "pricing": {
            "default": {"input": 0.0, "output": 0.0},
        },
        "models": ["自定义模型"],
    },
}


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        data = json.loads(json.dumps(DEFAULTS))
    else:
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            data = {}
    return _merge(_merge(DEFAULTS, data), _env_overrides())


def ensure_config_file() -> Path:
    """Create config.json from safe defaults on first startup."""
    if not CONFIG_PATH.exists():
        atomic_write_json(CONFIG_PATH, DEFAULTS)
    return CONFIG_PATH


def save_config(config: dict) -> dict:
    merged = _merge(load_config(), config)
    atomic_write_json(CONFIG_PATH, merged)
    return merged


def merge_config(update: dict) -> dict:
    return _merge(load_config(), update)


def validate_config(config: dict) -> list[str]:
    errors = []
    if not config.get("email"):
        errors.append("邮箱不能为空")
    if not config.get("auth_code"):
        errors.append("授权码不能为空")
    if not config.get("imap_host"):
        errors.append("IMAP 服务器不能为空")
    try:
        port = int(config.get("imap_port", 0))
        if not 1 <= port <= 65535:
            errors.append("IMAP 端口必须在 1-65535 之间")
    except (TypeError, ValueError):
        errors.append("IMAP 端口必须是数字")
    try:
        fetch_limit = int(config.get("fetch_limit", 0))
        if not 1 <= fetch_limit <= 500:
            errors.append("拉取邮件数量必须在 1-500 之间")
    except (TypeError, ValueError):
        errors.append("拉取邮件数量必须是数字")
    model = config.get("model") or {}
    if model.get("enabled") and model.get("provider") != "ollama" and not model.get("api_key"):
        errors.append("启用模型后必须配置 API Key")
    return errors


def mask_config(config: dict) -> dict:
    masked = json.loads(json.dumps(config))
    if masked.get("email"):
        masked["email"] = masked["email"]
    if masked.get("auth_code"):
        value = masked["auth_code"]
        if len(value) <= 4:
            masked["auth_code"] = "*" * len(value)
        else:
            masked["auth_code"] = f"{value[:2]}{'*' * (len(value) - 4)}{value[-2:]}"
    model = masked.get("model") or {}
    if model.get("api_key"):
        key = model["api_key"]
        if len(key) <= 4:
            model["api_key"] = "*" * len(key)
        else:
            model["api_key"] = f"{key[:4]}{'*' * (len(key) - 8)}{key[-4:]}"
    return masked


def get_meta() -> dict:
    return {
        "email_providers": json.loads(json.dumps(EMAIL_PROVIDERS)),
        "model_providers": json.loads(json.dumps(MODEL_PROVIDERS)),
    }


def _merge(base: dict, update: dict) -> dict:
    result = json.loads(json.dumps(base))
    for key, value in update.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = value
    return result
