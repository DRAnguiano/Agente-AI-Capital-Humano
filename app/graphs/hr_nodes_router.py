from app.graphs.hr_state import HRState


ROUTE_MAP = {
    "greeting": "greeting",
    "direct": "greeting",
    "profile": "profile",
    "rag": "rag",
    "vectorstore": "rag",
    "web_review": "web_review",
    "websearch": "web_review",
    "clarification": "clarification",
    "human_handoff": "human_handoff",
    "fallback": "fallback",
    "policy_boundary": "policy_boundary",
}

SIDE_QUESTION_TERMS = (
    "pagan",
    "pago",
    "sueldo",
    "salario",
    "kilometro",
    "kilómetro",
    "viaje",
    "ruta",
    "rutas",
    "base",
    "prestaciones",
    "beneficios",
    "requisito",
    "requisitos",
    "licencia",
    "apto",
    "horario",
    "turno",
)


def _route_from_classifier(classifier: dict) -> str:
    recommended = str(classifier.get("recommended_route") or "").strip().lower()
    datasource = str(classifier.get("datasource") or "").strip().lower()
    return ROUTE_MAP.get(recommended) or ROUTE_MAP.get(datasource) or "rag"


def _message_has_question_shape(message: str) -> bool:
    text = (message or "").strip().lower()
    if "?" in text or "¿" in text:
        return True
    return any(
        term in text
        for term in (
            "cuanto",
            "cuánto",
            "como",
            "cómo",
            "cuales",
            "cuáles",
            "donde",
            "dónde",
            "sabe",
            "quiero saber",
            "quisiera saber",
        )
    )


def _effective_routing_message(state: HRState) -> str:
    rewrite = state.get("contextual_rewrite") or {}
    if rewrite.get("should_use_rewrite") and rewrite.get("rewritten"):
        return str(rewrite.get("rewritten") or "")
    return str(state.get("message") or "")


def _is_side_question(state: HRState) -> bool:
    text = _effective_routing_message(state).strip().lower()
    if not _message_has_question_shape(text):
        return False
    return any(term in text for term in SIDE_QUESTION_TERMS)


def route_message_node(state: HRState) -> dict:
    classifier = state.get("classifier") or {}
    route = _route_from_classifier(classifier)
    reason = classifier.get("reason")

    # Consistency guard: if the classifier understood a candidate side-question
    # but still returned fallback/profile, recover into RAG. This keeps the graph
    # adaptive without relying on a single LLM routing decision.
    if route in {"fallback", "profile"} and _is_side_question(state):
        route = "rag"
        reason = "router_side_question_overrode_non_rag_route"

    requires_human = bool(classifier.get("requires_human", False)) or route == "human_handoff"
    requires_clarification = bool(classifier.get("requires_clarification", False)) or route == "clarification"
    requires_rag = bool(classifier.get("requires_rag", False)) or route == "rag"

    if route in {"greeting", "profile", "human_handoff", "clarification", "fallback", "policy_boundary"}:
        requires_rag = False
    if route == "web_review":
        requires_rag = False

    return {
        "intent": classifier.get("classifier_intent") or "route_question",
        "risk_level": classifier.get("risk_level") or "low",
        "requires_human": requires_human,
        "requires_rag": requires_rag,
        "requires_clarification": requires_clarification,
        "reason": reason,
        "route": route,
        "route_detection": {"source": "question_router", **classifier},
        "current_stage": state.get("current_stage") or "START",
        "events": [
            {
                "type": "route_message_decided",
                "route": route,
                "reason": reason,
                "side_question_override": route == "rag" and reason == "router_side_question_overrode_non_rag_route",
            }
        ],
    }
