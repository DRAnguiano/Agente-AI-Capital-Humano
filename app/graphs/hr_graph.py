from __future__ import annotations

from typing import Any

from app.orchestrators.knowledge_orchestrator import handle_message as knowledge_handle_message


def run_hr_graph_message(
    *,
    channel: str,
    channel_user_id: str,
    message: str,
    username: str | None = None,
    phone: str | None = None,
    external_message_id: str | None = None,
    pre_extraction: Any = None,
    pre_validated: Any = None,
) -> dict[str, Any]:
    """Entry point used by app.py and tasks_chatwoot.py."""
    payload = {
        "channel": channel,
        "channel_user_id": channel_user_id,
        "username": username,
        "phone": phone,
        "message": message,
        "external_message_id": external_message_id,
        "_pre_extraction": pre_extraction,
        "_pre_validated": pre_validated,
    }
    result = knowledge_handle_message(payload)
    result.setdefault("selected_route", result.get("route") or result.get("selected_route"))
    return result
