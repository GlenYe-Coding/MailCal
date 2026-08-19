"""Fetch the actual model list from the configured provider API."""
from __future__ import annotations

import json
import time
import urllib.request
from pathlib import Path

from config_store import MODEL_PROVIDERS, ROOT
from file_io import atomic_write_json
from logger import get_logger

CACHE_PATH = ROOT / "data" / "models_cache.json"
log = get_logger("model_catalog")


def _load_cache() -> dict:
    if not CACHE_PATH.exists():
        return {}
    try:
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_cache(payload: dict) -> None:
    atomic_write_json(CACHE_PATH, payload)


def fetch_available_models(config: dict, refresh: bool = False) -> dict:
    model = config.get("model", {})
    provider = model.get("provider") or "custom"
    provider_cfg = MODEL_PROVIDERS.get(provider, {})
    api_base = (model.get("api_base") or provider_cfg.get("api_base", "")).strip().rstrip("/")
    api_key = (model.get("api_key") or "").strip()
    cache_key = f"{provider}|{api_base}"
    cache = _load_cache()
    ttl_hours = int((config.get("cache") or {}).get("model_cache_ttl_hours", 24) or 24)
    ttl_seconds = max(300, ttl_hours * 3600)

    if (
        not refresh
        and cache.get("key") == cache_key
        and time.time() - cache.get("time", 0) < ttl_seconds
    ):
        log.debug("using cached model list for %s", provider)
        return {"source": "cache", "models": cache.get("models", [])}

    if provider == "ollama":
        url = api_base.replace("/v1", "") + "/api/tags"
        headers = {}
    else:
        if not api_key:
            return {"source": "no_key", "models": [], "message": "请先配置 API Key"}
        url = f"{api_base}/models"
        headers = {"Authorization": f"Bearer {api_key}"}

    try:
        request = urllib.request.Request(url, headers=headers, method="GET")
        with urllib.request.urlopen(request, timeout=20) as response:
            data = json.loads(response.read().decode("utf-8"))
        if provider == "ollama":
            models = sorted({m.get("name", "") for m in data.get("models", []) if m.get("name")})
        else:
            models = sorted(
                {
                    str(m.get("id") or m.get("name") or "")
                    for m in data.get("data", [])
                    if m.get("id") or m.get("name")
                }
            )
        _save_cache({"key": cache_key, "time": time.time(), "models": models})
        log.info("fetched %s models from %s", len(models), provider)
        return {"source": "api", "models": models}
    except Exception as exc:
        log.warning("failed to fetch models for %s: %s", provider, exc)
        return {"source": "error", "models": [], "message": str(exc)}


def clear_cache() -> dict:
    if CACHE_PATH.exists():
        CACHE_PATH.unlink()
    log.info("model cache cleared")
    return {"ok": True}
