from __future__ import annotations

from typing import Any

from app.db import log_event, update_stage
from app.graphs.hr_state import HRState


RECOVERY_REPLY = (
    "Entiendo, una disculpa por la demora. Si aún estás abierto a escuchar la propuesta, "
    "podemos explicarte la vacante en una llamada rápida para que compares y decidas qué opción te conviene más. "
    "¿Te gustaría que te agendemos?"
)

CLOSE_REPLY = (
    "Gracias por avisarnos. Entendemos si ya decidiste avanzar con otra opción; "
    "te agradecemos el tiempo y dejamos la puerta abierta por si más adelante deseas revisar otra vacante."
)

CLOSE_TERMS = (
    "ya no me interesa",
    "no me interesa",
    "ya encontre trabajo",
    "ya encontré trabajo",
    "ya consegui trabajo",
    "ya conseguí trabajo",
    "ya acepte otro",
    "ya acepté otro",
    "gracias ya no",
)


def _candidate_text(state: HRState) -> str:
    rewrite = state.get("contextual_rewrite") or {}
    if rewrite.get("should_use_rewrite") and rewrite.get("rewritten"):
        return str(rewrite.get("rewritten") or "")
    return str(state.get("message") or "")


def _should_close(text: str) -> bool:
    normalized = text.lower().strip()
    return any(term in normalized for term in CLOSE_TERMS)


def dropoff_recovery_response_node(state: HRState) -> dict[str, Any]:
    """Controlled conversational recovery for candidates who may leave the funnel."""
    conversation_key = state.get("conversation_key")
    current_stage = state.get("current_stage") or "START"
    message = _candidate_text(state)
    should_close = _should_close(message)
    reply = CLOSE_REPLY if should_close else RECOVERY_REPLY

    event_type = "candidate_dropoff_closed" if should_close else "candidate_dropoff_recovery_answered"
    stage_updated = False
    event_logged = False

    if conversation_key:
        update_stage(
            conversation_key=conversation_key,
            stage_to=current_stage,
            intent="candidate_dropoff_risk",
            risk_level="medium",
            requires_human=False,
        )
        stage_updated = True

        log_event(
            conversation_key=conversation_key,
            event_type=event_type,
            stage_from=current_stage,
            stage_to=current_stage,
            intent="candidate_dropoff_risk",
            risk_level="medium",
            requires_human=False,
            metadata={
                "reason": state.get("reason") or "candidate_dropoff_risk",
                "graph_route": "candidate_dropoff_recovery",
                "candidate_message": state.get("message"),
                "should_close": should_close,
            },
        )
        event_logged = True

    return {
        "intent": "candidate_dropoff_risk",
        "risk_level": "medium",
        "requires_human": False,
        "requires_rag": False,
        "requires_clarification": False,
        "next_stage": current_stage,
        "reply": reply,
        "text": reply,
        "route_stub_used": False,
        "dropoff_recovery_real_flow_used": True,
        "stage_updated": stage_updated,
        "dropoff_event_logged": event_logged,
        "events": [
            {
                "type": event_type,
                "stage_from": current_stage,
                "stage_to": current_stage,
                "reason": state.get("reason") or "candidate_dropoff_risk",
                "should_close": should_close,
            }
        ],
    }
