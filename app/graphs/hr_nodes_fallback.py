from typing import Any

from app.db import log_event, update_stage
from app.graphs.hr_state import HRState


DEFAULT_FALLBACK_REPLY = (
    "No quiero darte información incorrecta. Para ayudarte mejor, dime si tu mensaje es sobre "
    "documentos, requisitos, ubicación, licencia, experiencia, apto médico o disponibilidad."
)


def fallback_response_node(state: HRState) -> dict[str, Any]:
    """
    Generate and persist fallback graph state without inventing information.

    The fallback route keeps the conversation in its current stage, logs the
    event, and produces a safe assistant reply. This replaces the temporary
    diagnostic fallback stub.
    """
    conversation_key = state.get("conversation_key")
    current_stage = state.get("current_stage") or "START"
    intent = state.get("intent") or "fallback"
    risk_level = state.get("risk_level") or "low"
    reason = state.get("reason") or "fallback_no_route"
    reply = DEFAULT_FALLBACK_REPLY

    stage_updated = False
    fallback_event_logged = False

    if conversation_key:
        update_stage(
            conversation_key=conversation_key,
            stage_to=current_stage,
            intent=intent,
            risk_level=risk_level,
            requires_human=False,
        )
        stage_updated = True

        log_event(
            conversation_key=conversation_key,
            event_type="fallback_answered",
            stage_from=current_stage,
            stage_to=current_stage,
            intent=intent,
            risk_level=risk_level,
            requires_human=False,
            metadata={
                "reason": reason,
                "graph_route": "fallback",
                "candidate_message": state.get("message"),
            },
        )
        fallback_event_logged = True

    return {
        "next_stage": current_stage,
        "reply": reply,
        "text": reply,
        "route_stub_used": False,
        "fallback_real_flow_used": True,
        "stage_updated": stage_updated,
        "fallback_event_logged": fallback_event_logged,
        "events": [
            {
                "type": "fallback_answered",
                "stage_from": current_stage,
                "stage_to": current_stage,
                "reason": reason,
            }
        ],
    }
