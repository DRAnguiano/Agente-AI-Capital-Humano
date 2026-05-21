from typing import Any

from app.db import log_event, update_stage
from app.graphs.hr_state import HRState
from app.orchestrator import Intent, Stage


GENERIC_CLARIFICATION_REPLY = (
    "Para no malinterpretarte, ¿puedes explicarme un poco más a qué te refieres "
    "y cómo se relaciona con la vacante o el proceso?"
)


def _build_clarification_reply(state: HRState) -> str:
    """
    Build a neutral clarification prompt.

    Do not assume a specific slang meaning here. The router/review layer decides
    the risk and route; this node only asks the candidate for more context.
    """
    return GENERIC_CLARIFICATION_REPLY


def request_clarification_node(state: HRState) -> dict[str, Any]:
    """
    Persist and generate a controlled clarification request.

    This node is intentionally generic. Specific slang/policy interpretation
    belongs in retrieval, web review or later strict-rule layers, not here.
    """
    conversation_key = state.get("conversation_key")
    current_stage = state.get("current_stage") or Stage.START.value
    intent = state.get("intent") or Intent.AMBIGUOUS_SLANG.value
    risk_level = state.get("risk_level") or "medium"
    reason = state.get("reason") or "needs_clarification"
    next_stage = Stage.CLARIFY_AMBIGUOUS_SLANG.value
    reply = _build_clarification_reply(state)

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
