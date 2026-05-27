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
    "candidate_dropoff_recovery": "candidate_dropoff_recovery",
}

DROPOFF_REASONS = {
    "candidate_dropoff_risk",
    "candidate_churn_risk",
    "candidate_loss_risk",
}

DROPOFF_INTENTS = {
    "candidate_dropoff_risk",
    "candidate_churn_risk",
    "candidate_loss_risk",
    "dropoff_risk",
}

DROPOFF_TEXT_SIGNALS = (
    "desde ayer estoy esperando",
    "desde ayer espero",
    "estoy esperando",
    "sigo esperando",
    "me dejaron en visto",
    "nadie me contesto",
    "nadie me contestó",
    "no me han contestado",
    "no me respondieron",
    "tardaron mucho",
    "ya me hablaron de otro lado",
    "me hablaron de otro lado",
    "ya me llamaron de otro lado",
    "me llamaron de otro lado",
    "ya fui a otra entrevista",
    "ya encontre trabajo",
    "ya encontré trabajo",
    "ya consegui trabajo",
    "ya conseguí trabajo",
    "ya no me interesa",
)


def _effective_message(state: HRState) -> str:
    rewrite = state.get("contextual_rewrite") or {}
    if rewrite.get("should_use_rewrite") and rewrite.get("rewritten"):
        return str(rewrite.get("rewritten") or "")
    return str(state.get("message") or state.get("question") or "")


def _has_dropoff_signal(text: str) -> bool:
    normalized = text.lower().strip()
    return any(signal in normalized for signal in DROPOFF_TEXT_SIGNALS)


def _route_from_classifier(classifier: dict, state: HRState | None = None) -> str:
    recommended = str(classifier.get("recommended_route") or "").strip().lower()
    datasource = str(classifier.get("datasource") or "").strip().lower()
    reason = str(classifier.get("reason") or "").strip().lower()
    intent = str(classifier.get("classifier_intent") or "").strip().lower()

    if reason in DROPOFF_REASONS or intent in DROPOFF_INTENTS:
        return "candidate_dropoff_recovery"

    if state is not None and _has_dropoff_signal(_effective_message(state)):
        return "candidate_dropoff_recovery"

    return ROUTE_MAP.get(recommended) or ROUTE_MAP.get(datasource) or "rag"


def route_message_node(state: HRState) -> dict:
    classifier = state.get("classifier") or {}
    route = _route_from_classifier(classifier, state)

    requires_human = bool(classifier.get("requires_human", False)) or route == "human_handoff"
    requires_clarification = bool(classifier.get("requires_clarification", False)) or route == "clarification"
    requires_rag = bool(classifier.get("requires_rag", False)) or route == "rag"

    if route in {
        "greeting",
        "profile",
        "human_handoff",
        "clarification",
        "fallback",
        "policy_boundary",
        "candidate_dropoff_recovery",
    }:
        requires_rag = False
    if route == "web_review":
        requires_rag = False

    return {
        "intent": "candidate_dropoff_risk" if route == "candidate_dropoff_recovery" else classifier.get("classifier_intent") or "route_question",
        "risk_level": "medium" if route == "candidate_dropoff_recovery" else classifier.get("risk_level") or "low",
        "requires_human": requires_human,
        "requires_rag": requires_rag,
        "requires_clarification": requires_clarification,
        "reason": "candidate_dropoff_risk" if route == "candidate_dropoff_recovery" else classifier.get("reason"),
        "route": route,
        "route_detection": {"source": "question_router", **classifier},
        "current_stage": state.get("current_stage") or "START",
    }
