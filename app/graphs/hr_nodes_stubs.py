from typing import Any

from app.graphs.hr_nodes_clarification import request_clarification_node
from app.graphs.hr_nodes_fallback import fallback_response_node
from app.graphs.hr_nodes_greeting import greeting_response_node
from app.graphs.hr_nodes_handoff import (
    create_handoff_node,
    generate_handoff_reply_node,
    update_handoff_stage_node,
)
from app.graphs.hr_nodes_profile import (
    extract_profile_fields_node,
    update_profile_and_stage_node,
)
from app.graphs.hr_state import HRState


POLICY_BOUNDARY_FALLBACK_REPLY = (
    "Por seguridad operativa, ese punto debe revisarlo Capital Humano antes de continuar. "
    "No puedo confirmarlo por aquí ni avanzar el proceso con ese tema abierto."
)


def policy_boundary_response_node(state: HRState) -> dict[str, Any]:
    review = state.get("new_information_review") or {}
    reply = (state.get("reply") or review.get("reply") or POLICY_BOUNDARY_FALLBACK_REPLY).strip()
    return {
        "reply": reply,
        "text": reply,
        "next_stage": state.get("current_stage") or "START",
        "route_stub_used": False,
        "greeting_real_flow_used": False,
        "profile_real_flow_used": False,
        "human_handoff_real_flow_used": False,
        "clarification_real_flow_used": False,
        "fallback_real_flow_used": False,
        "policy_boundary_real_flow_used": True,
        "events": [
            {
                "type": "policy_boundary_answered",
                "reason": state.get("reason") or review.get("reason"),
                "risk_level": state.get("risk_level"),
            }
        ],
    }


def route_stub_response_node(state: HRState) -> dict[str, Any]:
    """
    Produce a controlled response for non-RAG routes.

    Current behavior:
    - greeting: answers first contact without advancing profile.
    - profile: runs the real profile extraction/stage update branch.
    - human_handoff: creates real handoff, updates stage, generates controlled reply.
    - clarification: updates stage and asks for a real clarification.
    - policy_boundary: responds with a safety boundary and does not advance profile.
    - fallback: generates a real safe fallback reply and logs it.
    """
    route = state.get("route") or "fallback"

    if route == "greeting":
        return greeting_response_node(state)

    if route == "profile":
        extracted_update = extract_profile_fields_node(state)
        merged_state: HRState = {
            **state,
            **extracted_update,
        }
        profile_update = update_profile_and_stage_node(merged_state)

        return {
            **extracted_update,
            **profile_update,
            "route_stub_used": False,
            "greeting_real_flow_used": False,
            "profile_real_flow_used": True,
            "human_handoff_real_flow_used": False,
            "clarification_real_flow_used": False,
            "fallback_real_flow_used": False,
            "policy_boundary_real_flow_used": False,
        }

    if route == "human_handoff":
        handoff_update = create_handoff_node(state)
        stage_state: HRState = {
            **state,
            **handoff_update,
        }
        stage_update = update_handoff_stage_node(stage_state)
        reply_state: HRState = {
            **stage_state,
            **stage_update,
        }
        reply_update = generate_handoff_reply_node(reply_state)

        return {
            **handoff_update,
            **stage_update,
            **reply_update,
            "route_stub_used": False,
            "greeting_real_flow_used": False,
            "profile_real_flow_used": False,
            "human_handoff_real_flow_used": True,
            "clarification_real_flow_used": False,
            "fallback_real_flow_used": False,
            "policy_boundary_real_flow_used": False,
        }

    if route == "clarification":
        clarification_update = request_clarification_node(state)

        return {
            **clarification_update,
            "route_stub_used": False,
            "greeting_real_flow_used": False,
            "profile_real_flow_used": False,
            "human_handoff_real_flow_used": False,
            "clarification_real_flow_used": True,
            "fallback_real_flow_used": False,
            "policy_boundary_real_flow_used": False,
        }

    if route == "policy_boundary":
        return policy_boundary_response_node(state)

    fallback_update = fallback_response_node(state)

    return {
        **fallback_update,
        "route_stub_used": False,
        "greeting_real_flow_used": False,
        "profile_real_flow_used": False,
        "human_handoff_real_flow_used": False,
        "clarification_real_flow_used": False,
        "fallback_real_flow_used": True,
        "policy_boundary_real_flow_used": False,
    }
