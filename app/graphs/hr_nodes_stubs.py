from typing import Any

from app.graphs.hr_state import HRState


_ROUTE_REPLY = {
    "profile": "Ruta de perfil detectada. En producción, este flujo extraerá datos del candidato y avanzará etapa.",
    "human_handoff": "Ruta de revisión humana detectada. En producción, este flujo creará handoff para Capital Humano.",
    "clarification": "Ruta de aclaración detectada. En producción, este flujo pedirá una aclaración breve antes de continuar.",
    "fallback": "Ruta fallback detectada. En producción, este flujo responderá de forma segura sin inventar información.",
}


def route_stub_response_node(state: HRState) -> dict[str, Any]:
    """
    Produce a controlled placeholder response for non-RAG routes.

    This is only for diagnostic full-router testing. It avoids calling the legacy
    orchestrator after the graph has already persisted the incoming message,
    preventing duplicate writes.
    """
    route = state.get("route") or "fallback"
    reply = _ROUTE_REPLY.get(route, _ROUTE_REPLY["fallback"])

    return {
        "reply": reply,
        "text": reply,
        "route_stub_used": True,
        "events": [
            {
                "type": "route_stub_response_generated",
                "route": route,
            }
        ],
    }
