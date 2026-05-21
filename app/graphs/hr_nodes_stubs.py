from typing import Any

from app.graphs.hr_nodes_clarification import request_clarification_node
from app.graphs.hr_nodes_fallback import fallback_response_node
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


def route_stub_response_node(state: HRState) -> dict[str, Any]:
    """
    Produce a controlled response for non-RAG routes.

    Current behavior:
    - profile: runs the real profile extraction/stage update branch.
    - human_handoff: creates real handoff, updates stage, generates controlled reply.
    - clarification: updates stage and asks for a real clarification.
    - fallback: generates a real safe fallback reply and logs it.

    This keeps the full-router/orchestrate-graph diagnostic paths legacy-free
    while progressively replacing stubs with real nodes.
    """
    route = state.get("route") or "fallback"

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
            "profile_real_flow_used": True,
            "human_handoff_real_flow_used": False,
            "clarification_real_flow_used": False,
            "fallback_real_flow_used": False,
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
            "profile_real_flow_used": False,
            "human_handoff_real_flow_used": True,
            "clarification_real_flow_used": False,
            "fallback_real_flow_used": False,
        }

    if route == "clarification":
        clarification_update = request_clarification_node(state)

        return {
            **clarification_update,
            "route_stub_used": False,
            "profile_real_flow_used": False,
            "human_handoff_real_flow_used": False,
            "clarification_real_flow_used": True,
            "fallback_real_flow_used": False,
        }

    fallback_update = fallback_response_node(state)

    return {
        **fallback_update,
        "route_stub_used": False,
        "profile_real_flow_used": False,
        "human_handoff_real_flow_used": False,
        "clarification_real_flow_used": False,
        "fallback_real_flow_used": True,
    }
