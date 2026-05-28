from __future__ import annotations

import os
from typing import Any

from app.orchestrator import orchestrate_message as legacy_orchestrate_message
from app.orchestrators.knowledge_orchestrator import handle_message as knowledge_handle_message


INPUT_TEST_CHANNEL = "test_input_nodes"
ROUTER_TEST_CHANNEL = "test_router_nodes"
RAG_TEST_CHANNEL = "test_rag_nodes"
RAG_REPLACEMENT_TEST_CHANNEL = "test_rag_replacement"
FULL_ROUTER_TEST_CHANNEL = "test_full_router"
ORCHESTRATE_GRAPH_TEST_CHANNEL = "test_orchestrate_graph"
KNOWLEDGE_TEST_CHANNEL = "test_knowledge_orchestrator"


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _graph_mode() -> str:
    return os.getenv("HR_GRAPH_MODE", "legacy").strip().lower()


def _legacy_payload(
    *,
    channel: str,
    channel_user_id: str,
    username: str | None,
    phone: str | None,
    message: str,
    external_message_id: str | None,
) -> dict[str, Any]:
    result = legacy_orchestrate_message(
        channel=channel,
        channel_user_id=channel_user_id,
        username=username,
        phone=phone,
        message=message,
        external_message_id=external_message_id,
    )
    result.setdefault("selected_route", result.get("route") or "legacy_orchestrator")
    result.setdefault("graph_trace", {"mode": "legacy", "route": result.get("selected_route")})
    result["graph"] = {
        "enabled": False,
        "route": "legacy_orchestrator",
        "hr_graph_mode": _graph_mode(),
        "use_langgraph_orchestrator": _env_bool("USE_LANGGRAPH_ORCHESTRATOR", False),
        "langgraph_bypassed": True,
    }
    return result


def _knowledge_payload(
    *,
    channel: str,
    channel_user_id: str,
    username: str | None,
    phone: str | None,
    message: str,
    external_message_id: str | None,
) -> dict[str, Any]:
    payload = {
        "channel": channel,
        "channel_user_id": channel_user_id,
        "username": username,
        "phone": phone,
        "message": message,
        "external_message_id": external_message_id,
    }
    result = knowledge_handle_message(payload)
    result.setdefault("selected_route", result.get("route") or result.get("selected_route"))
    result["graph"] = {
        "enabled": False,
        "route": "knowledge_orchestrator",
        "hr_graph_mode": _graph_mode(),
        "use_langgraph_orchestrator": _env_bool("USE_LANGGRAPH_ORCHESTRATOR", False),
        "langgraph_bypassed": True,
        "neo4j_knowledge_enabled": True,
        "rag_generation_enabled": False,
    }
    return result


def run_hr_graph_message(
    *,
    channel: str,
    channel_user_id: str,
    message: str,
    username: str | None = None,
    phone: str | None = None,
    external_message_id: str | None = None,
) -> dict[str, Any]:
    """Main compatibility entrypoint used by app.py.

    Phase 2.3 intentionally removes LangGraph from the main runtime path.

    - HR_GRAPH_MODE=knowledge: use Neo4j + controlled contract only.
    - HR_GRAPH_MODE=legacy/full_debug or anything else: use the old imperative
      orchestrator for compatibility while the knowledge path matures.

    The old LangGraph workflows are no longer built at import time, which keeps
    startup lighter and makes the active path easier to debug.
    """
    mode = _graph_mode()
    normalized_channel = (channel or "").strip().lower()

    if mode == "knowledge" or normalized_channel == KNOWLEDGE_TEST_CHANNEL:
        return _knowledge_payload(
            channel=channel,
            channel_user_id=channel_user_id,
            username=username,
            phone=phone,
            message=message,
            external_message_id=external_message_id,
        )

    return _legacy_payload(
        channel=channel,
        channel_user_id=channel_user_id,
        username=username,
        phone=phone,
        message=message,
        external_message_id=external_message_id,
    )
