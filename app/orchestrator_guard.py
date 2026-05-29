from typing import Any

from .orchestrator import orchestrate_message as legacy_orchestrate_message
from .knowledge.current_turn import (
    build_current_turn_ack,
    extract_current_turn_facts,
    should_prioritize_current_turn,
)


def orchestrate_message(
    channel: str,
    channel_user_id: str,
    message: str,
    username: str | None = None,
    phone: str | None = None,
    external_message_id: str | None = None,
) -> dict[str, Any]:
    """
    Guard wrapper around the legacy orchestrator.

    Goal:
    - Keep existing persistence/events intact by still calling the current orchestrator.
    - Prevent RAG or stale memory from overriding clear profile facts in the current turn.

    Architecture rule:
    current_message_facts > memory_facts > RAG.
    """
    result = legacy_orchestrate_message(
        channel=channel,
        channel_user_id=channel_user_id,
        username=username,
        phone=phone,
        message=message,
        external_message_id=external_message_id,
    )

    if not should_prioritize_current_turn(message):
        return result

    current_facts = extract_current_turn_facts(message)
    guarded_reply = build_current_turn_ack(message)

    # Do not override restrictive/human-review cases.
    if result.get("requires_human") and result.get("risk_level") == "high":
        return result

    result = {
        **result,
        "reply": guarded_reply,
        "text": guarded_reply,
        "intent": result.get("intent") or "candidate_answer",
        "risk_level": "low",
        "requires_human": False,
        "current_turn_guard_applied": True,
        "current_turn_facts": current_facts,
    }

    return result
