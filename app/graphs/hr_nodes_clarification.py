from typing import Any

from app.db import log_event, update_stage
from app.graphs.hr_state import HRState
from app.orchestrator import Intent, STATIC_REPLIES, Stage


def request_clarification_node(state: HRState) -> dict[str, Any]:
    """
    Persist and generate a controlled clarification request.

    This replaces the diagnostic clarification stub. It mirrors the legacy
    behavior for ambiguous slang: move the conversation to
    CLARIFY_AMBIGUOUS_SLANG and ask the candidate to clarify intent.
    """
    conversation_key = state.get("conversation_key")
    current_stage = state.get("current_stage") or Stage.START.value
    intent = state.get("intent") or Intent.AMBIGUOUS_SLANG.value
    risk_level = state.get("risk_level") or "medium"
    reason = state.get("reason") or "jerga_ambigua"
    next_stage = Stage.CLARIFY_AMBIGUOUS_SLANG.value
    reply = STATIC_REPLIES[Intent.AMBIGUOUS_SLANG.value]

    stage_updated = False
    event_logged = False

    if conversation_key:
        update_stage(
            conversation_key=conversation_key,
            stage_to=next_stage,
            intent=intent,
            risk_level=risk_level,
            requires_human=False,
        )
        stage_updated = True

        log_event(
            conversation_key=conversation_key,
            event_type="clarification_requested",
            stage_from=current_stage,
            stage_to=next_stage,
            intent=intent,
            risk_level=risk_level,
            requires_human=False,
            metadata={
                "reason": reason,
                "graph_route": "clarification",
                "candidate_message": state.get("message"),
            },
        )
        event_logged = True

    return {
        "next_stage": next_stage,
        "reply": reply,
        "text": reply,
        "stage_updated": stage_updated,
        "clarification_event_logged": event_logged,
        "clarification_real_flow_used": True,
        "route_stub_used": False,
        "events": [
            {
                "type": "clarification_requested",
                "stage_from": current_stage,
                "stage_to": next_stage,
                "reason": reason,
            }
        ],
    }
