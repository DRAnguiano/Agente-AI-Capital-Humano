import os

from app.graphs.hr_state import HRState


INTERNAL_SIDE_QUESTION_TERMS = (
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


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _effective_question(state: HRState) -> str:
    rewrite = state.get("contextual_rewrite") or {}
    if rewrite.get("should_use_rewrite") and rewrite.get("rewritten"):
        return str(rewrite.get("rewritten") or "")
    return str(state.get("question") or state.get("message") or "")


def _is_internal_side_question(state: HRState) -> bool:
    text = _effective_question(state).strip().lower()
    if not text:
        return False

    has_question_shape = "?" in text or "¿" in text or any(
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
        )
    )

    return has_question_shape and any(term in text for term in INTERNAL_SIDE_QUESTION_TERMS)


def route_after_router(state: HRState) -> str:
    return state.get("route", "fallback")


def route_after_full_router(state: HRState) -> str:
    """
    Map semantic routes to technical graph nodes.

    Keep state["route"] as a business/semantic route. This function is the only
    place that translates it into LangGraph node names.
    """
    route = state.get("route")

    if route == "rag":
        return "rewrite_question"

    if route == "web_review":
        return "tavily_web_search"

    return "route_stub_response"


def route_after_grading(state: HRState) -> str:
    if state.get("docs_are_relevant"):
        return "generate_answer"
    return "fallback_no_context"


def route_after_grading_or_web(state: HRState) -> str:
    if state.get("docs_are_relevant"):
        return "generate_answer"

    # Pay, route, benefits, requirements and similar questions are internal HR
    # knowledge. If Chroma misses them, do not jump to web/handoff; keep the
    # flow in the internal RAG fallback so the candidate does not get an
    # unnecessary escalation for a normal recruiting question.
    if _is_internal_side_question(state):
        return "fallback_no_context"

    if _env_bool("WEB_SEARCH_ENABLED", False):
        return "tavily_web_search"

    return "fallback_no_context"


def route_after_answer_check(state: HRState) -> str:
    """
    Route after answer quality checks.

    A failed RAG answer is not automatically a human-handoff case. Most failures
    mean missing context or weak grounding, so the safe default is the controlled
    no-context fallback. Human handoff remains reserved for explicit high-risk
    routes decided before generation.
    """
    if state.get("answer_check") == "PASS":
        return "save_output"

    if state.get("requires_human") or state.get("risk_level") == "high":
        return "route_stub_response"

    return "fallback_no_context"

def route_after_web_review(state: HRState) -> str:
    """
    After Tavily/review, avoid dead-ending into fallback when the question is
    still clearly internal to recruiting/logistics.

    Tavily is used to understand unknown terms. If it returns no useful content,
    we still try internal RAG with the contextual rewrite instead of giving up.
    """
    web_count = int(state.get("web_results_count") or 0)
    web_error = state.get("web_search_error")
    review = state.get("new_information_review") or {}

    if web_count > 0 and review:
        return "route_stub_response"

    if web_error or web_count == 0:
        question = _effective_question(state).lower()
        internal_terms = (
            "operador",
            "quinta rueda",
            "tractocamión",
            "tractocamion",
            "trailero",
            "transporte",
            "ruta",
            "parada",
            "paradas",
            "parador",
            "carretera",
            "café",
            "cafe",
            "baño",
            "bano",
            "descanso",
            "licencia",
            "apto",
            "proceso",
            "contratación",
            "contratacion",
            "prueba",
            "toxicológica",
            "toxicologica",
            "orina",
            "sustancias",
            "alcohol",
            "puedo aplicar",
            "puedo entrar",
            "puedo continuar",
        )

        if any(term in question for term in internal_terms):
            return "rewrite_question"

    return "route_stub_response"

def route_after_semantic_uncertainty(state: HRState) -> str:
    """
    Respect the semantic uncertainty analyzer.

    If it says the graph is assuming too much, stop routing and ask a friendly
    clarification before RAG/web/policy boundary can run.
    """
    uncertainty = state.get("semantic_uncertainty") or {}

    if uncertainty.get("should_clarify") is True:
        return "semantic_clarification"

    return "rewrite_safety_guard"
