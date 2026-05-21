from typing import Any

from app.db import create_handoff, log_event, update_candidate_profile, update_stage
from app.graphs.hr_state import HRState
from app.orchestrator import Intent, STATIC_REPLIES, Stage


HIGH_RISK_DEFAULT_REASON = "tema_sensible"
MEDIUM_RISK_DEFAULT_REASON = "requiere_validacion_rh"


def _handoff_reply_for_state(state: HRState) -> str:
    """
    Return the controlled reply used for human handoff routes.

    For now we keep parity with the legacy orchestrator: high-risk handoffs use
    the sensitive handoff message. Medium-risk handoff behavior can be refined
    once conditional availability and follow-up handoffs are migrated.
    """
    risk_level = state.get("risk_level") or "high"
    intent = state.get("intent") or "sensitive_handoff"

    if risk_level == "high":
        return STATIC_REPLIES[Intent.SENSITIVE_HANDOFF.value]

    if intent == Intent.CONDITIONAL_AVAILABILITY.value:
        return STATIC_REPLIES[Intent.CONDITIONAL_AVAILABILITY.value]

    return (
        "Gracias por compartirlo. Voy a dejar este punto marcado para revisión de Capital Humano "
        "antes de continuar con el proceso."
    )


def create_handoff_node(state: HRState) -> dict[str, Any]:
    """
    Persist a human handoff request for Capital Humano.

    This replaces the diagnostic stub for `human_handoff` routes. It creates an
    open handoff idempotently through db.create_handoff().
    """
    conversation_key = state.get("conversation_key")
    message = state.get("message") or ""
    reason = state.get("reason") or HIGH_RISK_DEFAULT_REASON
    risk_level = state.get("risk_level") or "high"

    handoff_created = False

    if conversation_key:
        create_handoff(
            conversation_key=conversation_key,
            reason=reason,
            risk_level=risk_level,
            summary=message,
        )
        handoff_created = True

    return {
        "handoff_created": handoff_created,
        "events": [
            {
                "type": "human_handoff_created",
                "conversation_key": conversation_key,
                "reason": reason,
                "risk_level": risk_level,
            }
        ],
    }


def update_handoff_stage_node(state: HRState) -> dict[str, Any]:
    """
    Move conversation into HUMAN_REVIEW_REQUIRED and mark profile risk flags.
    """
    conversation_key = state.get("conversation_key")
    current_stage = state.get("current_stage") or Stage.START.value
    intent = state.get("intent") or Intent.SENSITIVE_HANDOFF.value
    risk_level = state.get("risk_level") or "high"
    reason = state.get("reason") or HIGH_RISK_DEFAULT_REASON

    next_stage = Stage.HUMAN_REVIEW_REQUIRED.value if risk_level == "high" else current_stage
    stage_updated = False
    profile_updated = False
    event_logged = False

    if conversation_key:
        update_stage(
            conversation_key=conversation_key,
            stage_to=next_stage,
            intent=intent,
            risk_level=risk_level,
            requires_human=True,
        )
        stage_updated = True

        update_candidate_profile(
            conversation_key,
            {
                "last_detected_intent": intent,
                "risk_level": risk_level,
                "requires_human": True,
                "observaciones": f"Requiere revisión de Capital Humano. Motivo: {reason}",
            },
        )
        profile_updated = True

        log_event(
            conversation_key=conversation_key,
            event_type="human_handoff_graph_completed",
            stage_from=current_stage,
            stage_to=next_stage,
            intent=intent,
            risk_level=risk_level,
            requires_human=True,
            metadata={
                "reason": reason,
                "graph_route": "human_handoff",
            },
        )
        event_logged = True

    return {
        "next_stage": next_stage,
        "stage_updated": stage_updated,
        "handoff_profile_updated": profile_updated,
        "handoff_event_logged": event_logged,
        "requires_human": True,
        "events": [
            {
                "type": "human_handoff_stage_updated",
                "stage_from": current_stage,
                "stage_to": next_stage,
                "reason": reason,
                "risk_level": risk_level,
            }
        ],
    }


def generate_handoff_reply_node(state: HRState) -> dict[str, Any]:
    """
    Generate the controlled assistant reply for human handoff routes.
    """
    reply = _handoff_reply_for_state(state)

    return {
        "reply": reply,
        "text": reply,
        "route_stub_used": False,
        "human_handoff_real_flow_used": True,
        "events": [
            {
                "type": "human_handoff_reply_generated",
                "risk_level": state.get("risk_level") or "high",
                "reason": state.get("reason"),
            }
        ],
    }
