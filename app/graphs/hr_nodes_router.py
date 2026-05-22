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


def _route_from_classifier(classifier: dict) -> str:
    recommended = str(classifier.get("recommended_route") or "").strip().lower()
    datasource = str(classifier.get("datasource") or "").strip().lower()
    return ROUTE_MAP.get(recommended) or ROUTE_MAP.get(datasource) or "rag"


def route_message_node(state: HRState) -> dict:
    classifier = state.get("classifier") or {}
    route = _route_from_classifier(classifier)

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
        "reason": classifier.get("reason"),
        "route": route,
        "route_detection": {"source": "question_router", **classifier},
        "current_stage": state.get("current_stage") or "START",
    }
