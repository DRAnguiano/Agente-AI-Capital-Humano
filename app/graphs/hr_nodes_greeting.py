from typing import Any

from app.db import log_event, update_stage
from app.graphs.hr_state import HRState
from app.orchestrator import Stage


DEFAULT_GREETING_REPLY = (
    "Hola, soy Mundo, asistente de Capital Humano de Transmontes. "
    "¿Está interesado en nuestra vacante para operador de quinta rueda?"
)


def greeting_response_node(state: HRState) -> dict[str, Any]:
    """
    Answer greetings / first-contact intent discovery without advancing profile.

    A simple greeting is not consent to start the recruitment form. Keep the
    conversation at START and ask whether the person is interested in the role.
    """
    conversation_key = state.get("conversation_key")
    current_stage = state.get("current_stage") or Stage.START.value
    intent = state.get("intent") or state.get("classifier_intent") or "greeting"
    risk_level = state.get("risk_level") or "low"
    reason = state.get("reason") or "initial_greeting"
    reply = DEFAULT_GREETING_REPLY

    stage_updated = False
    event_logged = False

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
            event_type="greeting_answered",
            stage_from=current_stage,
            stage_to=current_stage,
            intent=intent,
            risk_level=risk_level,
            requires_human=False,
            metadata={
                "reason": reason,
                "graph_route": "greeting",
                "classifier": state.get("classifier"),
            },
        )
        event_logged = True

    return {
        "next_stage": current_stage,
        "reply": reply,
        "text": reply,
        "stage_updated": stage_updated,
        "greeting_event_logged": event_logged,
        "route_stub_used": False,
        "greeting_real_flow_used": True,
        "profile_real_flow_used": False,
        "human_handoff_real_flow_used": False,
        "clarification_real_flow_used": False,
        "fallback_real_flow_used": False,
        "policy_boundary_real_flow_used": False,
        "events": [
            {
                "type": "greeting_answered",
                "stage_from": current_stage,
                "stage_to": current_stage,
                "reason": reason,
            }
        ],
    }
