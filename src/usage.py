"""Track model token usage and estimated cost per model."""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from config_store import MODEL_PROVIDERS, ROOT
from file_io import atomic_write_json
from logger import get_logger

USAGE_PATH = ROOT / "data" / "model_usage.json"
log = get_logger("usage")


def _empty() -> dict:
    return {"updated_at": "", "records": [], "totals": {}}


def load_usage() -> dict:
    if not USAGE_PATH.exists():
        return _empty()
    try:
        data = json.loads(USAGE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return _empty()
    return {
        "updated_at": data.get("updated_at", ""),
        "records": data.get("records", []),
        "totals": data.get("totals", {}),
    }


def pricing_for(provider: str, model: str) -> tuple[float, float]:
    provider_cfg = MODEL_PROVIDERS.get(provider, {})
    pricing = provider_cfg.get("pricing", {})
    item = pricing.get(model) or pricing.get("default") or {"input": 0, "output": 0}
    return float(item.get("input", 0)), float(item.get("output", 0))


def record_usage(
    provider: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int = 0,
) -> None:
    input_price, output_price = pricing_for(provider, model)
    prompt_tokens = int(prompt_tokens or 0)
    completion_tokens = int(completion_tokens or 0)
    total_tokens = int(total_tokens or prompt_tokens + completion_tokens)
    cost = (
        prompt_tokens / 1_000_000 * input_price
        + completion_tokens / 1_000_000 * output_price
    )

    data = load_usage()
    data["records"].append(
        {
            "id": f"{dt.datetime.now().timestamp():.3f}",
            "time": dt.datetime.now().astimezone().isoformat(),
            "provider": provider,
            "model": model,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "input_price_per_m": input_price,
            "output_price_per_m": output_price,
            "cost": round(cost, 8),
        }
    )

    key = f"{provider}/{model}"
    total = data["totals"].setdefault(
        key,
        {
            "provider": provider,
            "model": model,
            "calls": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "cost": 0.0,
        },
    )
    total["calls"] += 1
    total["prompt_tokens"] += prompt_tokens
    total["completion_tokens"] += completion_tokens
    total["total_tokens"] += total_tokens
    total["cost"] = round(total["cost"] + cost, 8)
    data["updated_at"] = dt.datetime.now().astimezone().isoformat()
    USAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(USAGE_PATH, data)
    log.debug(
        "recorded usage: %s/%s prompt=%s completion=%s cost=%s",
        provider,
        model,
        prompt_tokens,
        completion_tokens,
        round(cost, 8),
    )


def summarize() -> dict:
    data = load_usage()
    totals = sorted(
        data["totals"].values(),
        key=lambda item: item.get("cost", 0),
        reverse=True,
    )
    return {
        "updated_at": data.get("updated_at", ""),
        "models": totals,
        "total_calls": sum(item.get("calls", 0) for item in totals),
        "total_tokens": sum(item.get("total_tokens", 0) for item in totals),
        "total_cost": round(sum(item.get("cost", 0) for item in totals), 8),
        "currency": "USD",
        "records": data.get("records", [])[-100:],
    }


def reset_usage() -> dict:
    USAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(USAGE_PATH, _empty())
    return summarize()
