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
    natural_lead_profile_response_node,
    update_profile_and_stage_node,
)
from app.graphs.hr_nodes_profile_followup import plan_profile_followup_node
from app.graphs.hr_state import HRState


POLICY_BOUNDARY_FALLBACK_REPLY = (
    "Nuestra empresa tiene política de 0 tolerancia. "
    "Por seguridad, Capital Humano debe revisar este punto antes de continuar con el proceso."
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


def _flow_flags(*, profile: bool = False, handoff: bool = False, clarification: bool = False, fallback: bool = False, policy: bool = False, greeting: bool = False) -> dict[str, bool]:
    return {
        "route_stub_used": False,
        "greeting_real_flow_used": greeting,
        "profile_real_flow_used": profile,
        "human_handoff_real_flow_used": handoff,
        "clarification_real_flow_used": clarification,
        "fallback_real_flow_used": fallback,
        "policy_boundary_real_flow_used": policy,
    }


def _merge_events(*updates: dict[str, Any]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for update in updates:
        events.extend(update.get("events") or [])
    return events


def route_stub_response_node(state: HRState) -> dict[str, Any]:
    """
    Produce a controlled response for non-RAG routes.

    For profile-like messages, prefer natural lead capture when lead_ingestion
    already extracted useful facts. Fall back to the legacy stage form only when
    no lead facts were captured.
    """
    route = state.get("route") or "fallback"

    if route == "greeting":
        return greeting_response_node(state)

    if route == "profile":
        lead = state.get("lead_ingestion") or {}
        if lead.get("updated"):
            followup_plan_update = plan_profile_followup_node(state)
            planned_state: HRState = {**state, **followup_plan_update}
            natural_update = natural_lead_profile_response_node(planned_state)
            return {
                **followup_plan_update,
                **natural_update,
                **_flow_flags(profile=True),
                "events": _merge_events(followup_plan_update, natural_update),
            }

        extracted_update = extract_profile_fields_node(state)
        merged_state: HRState = {**state, **extracted_update}
        profile_update = update_profile_and_stage_node(merged_state)

        return {
            **extracted_update,
            **profile_update,
            **_flow_flags(profile=True),
            "events": _merge_events(extracted_update, profile_update),
        }

    if route == "human_handoff":
        handoff_update = create_handoff_node(state)
        stage_state: HRState = {**state, **handoff_update}
        stage_update = update_handoff_stage_node(stage_state)
        reply_state: HRState = {**stage_state, **stage_update}
        reply_update = generate_handoff_reply_node(reply_state)

        return {
            **handoff_update,
            **stage_update,
            **reply_update,
            **_flow_flags(handoff=True),
            "events": _merge_events(handoff_update, stage_update, reply_update),
        }

    if route == "clarification":
        clarification_update = request_clarification_node(state)
        return {
            **clarification_update,
            **_flow_flags(clarification=True),
        }

    if route == "policy_boundary":
        policy_update = policy_boundary_response_node(state)
        return {
            **policy_update,
            **_flow_flags(policy=True),
        }

    fallback_update = fallback_response_node(state)
    return {
        **fallback_update,
        **_flow_flags(fallback=True),
    }
