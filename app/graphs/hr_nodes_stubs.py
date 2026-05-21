from typing import Any

from app.graphs.hr_nodes_profile import (
    extract_profile_fields_node,
    update_profile_and_stage_node,
)
from app.graphs.hr_state import HRState


_ROUTE_REPLY = {
    "human_handoff": "Ruta de revisión humana detectada. En producción, este flujo creará handoff para Capital Humano.",
    "clarification": "Ruta de aclaración detectada. En producción, este flujo pedirá una aclaración breve antes de continuar.",
    "fallback": "Ruta fallback detectada. En producción, este flujo responderá de forma segura sin inventar información.",
}


def route_stub_response_node(state: HRState) -> dict[str, Any]:
    """
    Produce a controlled response for non-RAG routes.

    Current behavior:
    - profile: runs the real profile extraction/stage update branch.
    - human_handoff/clarification/fallback: still use controlled placeholders.

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
        }

    reply = _ROUTE_REPLY.get(route, _ROUTE_REPLY["fallback"])

    return {
        "reply": reply,
        "text": reply,
        "route_stub_used": True,
        "profile_real_flow_used": False,
        "events": [
            {
                "type": "route_stub_response_generated",
                "route": route,
            }
        ],
    }
