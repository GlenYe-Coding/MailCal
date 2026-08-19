"""LangGraph agent that turns email batches into calendar events."""
from __future__ import annotations

from typing import TypedDict

from event_normalizer import normalize_event, valid_event_shape
from event_extractor import extract_with_model
from logger import get_logger
from model_catalog import fetch_available_models

try:
    from langgraph.graph import END, START, StateGraph
except ImportError:  # pragma: no cover
    StateGraph = None

log = get_logger("model_agent")


class AgentState(TypedDict):
    messages: list[dict]
    model_config: dict
    events: list[dict]
    error: str


def call_model(state: AgentState) -> dict:
    try:
        events = extract_with_model(state["messages"], state["model_config"])
        log.debug("model agent returned %s raw events", len(events))
        return {"events": events, "error": ""}
    except Exception as exc:
        log.exception("model agent call failed")
        return {"events": [], "error": str(exc)}


def validate_events(state: AgentState) -> dict:
    events = []
    for event in state.get("events", []):
        normalized = normalize_event(event)
        if not normalized or not valid_event_shape(normalized):
            continue
        normalized.setdefault("color", "#64748b")
        normalized.setdefault("status", "auto")
        events.append(normalized)
    return {"events": events}


def build_agent():
    if StateGraph is None:
        return None
    graph = StateGraph(AgentState)
    graph.add_node("call_model", call_model)
    graph.add_node("validate", validate_events)
    graph.add_edge(START, "call_model")
    graph.add_edge("call_model", "validate")
    graph.add_edge("validate", END)
    return graph.compile()


def extract_events(messages: list[dict], model_config: dict) -> list[dict]:
    if not model_config.get("enabled"):
        return []
    provider = model_config.get("provider") or "custom"
    if not model_config.get("api_key") and provider != "ollama":
        return []

    resolved = dict(model_config)
    available = fetch_available_models({"model": resolved}, refresh=False)
    models = available.get("models", [])
    if models:
        current = resolved.get("model_name") or ""
        if current not in models:
            resolved["model_name"] = models[0]
            log.info("model %s not in provider list, using %s", current or "unset", models[0])
    elif available.get("source") == "no_key":
        return []

    agent = build_agent()
    if agent is None:
        log.debug("langgraph unavailable, using direct model call")
        return extract_with_model(messages, resolved)
    try:
        result = agent.invoke(
            {
                "messages": messages,
                "model_config": resolved,
                "events": [],
                "error": "",
            }
        )
        events = result.get("events", [])
        log.debug("model agent finished with %s events", len(events))
        return events
    except Exception as exc:
        log.warning("model agent failed, falling back to direct call: %s", exc)
        return extract_with_model(messages, resolved)
