"""Orquestador de acciones multi-intent (Fase 3).

Toma la clasificación enriquecida (intent_enricher) + los facts conocidos del lead
y produce:
  - recommended_action_order
  - facts_to_persist (listos para que la Fase 4 los escriba)
  - response_text (genera RAG para preguntas + siguiente pregunta del funnel)

Aislado: NO persiste en Postgres ni envía a Chatwoot. Solo planea y genera texto.
La conexión real al flujo es la Fase 4 (detrás de feature flag).

El funnel de 6 preguntas es la fuente única definida en
docs/esquema_perfilamiento_v1.md (§1). Reemplaza la lógica dispersa de
_FUNNEL_STEPS, next_question_from_missing_facts y el SYSTEM_PROMPT.
"""
from __future__ import annotations

from typing import Any

from app.indexer import call_llm
from app.knowledge.context_builder import build_generation_prompt, retrieve_preferred_context

# ── Funnel de 6 preguntas (esquema v1 §1) ────────────────────────────────────
# Cada paso: la pregunta canónica + función que decide si el campo está completo.

def _has(facts: dict[str, Any], key: str) -> bool:
    return bool(facts.get(key))


FUNNEL_STEPS: list[dict[str, Any]] = [
    {
        "field": "candidate.city",
        "question": "¿Desde qué ciudad o estado nos escribe?",
        "complete": lambda f: _has(f, "candidate.city"),
    },
    {
        "field": "experience.vehicle_type",
        "question": "¿Ha manejado sencillo, full o ambos?",
        "complete": lambda f: _has(f, "experience.vehicle_type"),
    },
    {
        "field": "license",
        "question": "¿Qué tipo de licencia federal tiene y está vigente?",
        "complete": lambda f: _has(f, "license.type") and f.get("license.status") == "vigente",
    },
    {
        "field": "medical.apto_status",
        "question": "¿Su apto médico está vigente?",
        "complete": lambda f: f.get("medical.apto_status") == "vigente",
    },
    {
        "field": "experience.years",
        "question": "¿Cuántos años tiene manejando?",
        "complete": lambda f: _has(f, "experience.years"),
    },
    {
        "field": "documents.proof",
        "question": "¿Cuenta con 2 cartas laborales o su documento de semanas cotizadas del IMSS?",
        "complete": lambda f: f.get("documents.proof") in {"cartas", "semanas_imss"},
    },
]


def next_funnel_question(facts: dict[str, Any]) -> str | None:
    """Devuelve la siguiente pregunta del funnel, o None si el núcleo está completo."""
    for step in FUNNEL_STEPS:
        if not step["complete"](facts):
            return step["question"]
    return None


def core_completeness(facts: dict[str, Any]) -> int:
    """Cuántos de los 6 campos núcleo están completos (para el status del lead)."""
    return sum(1 for step in FUNNEL_STEPS if step["complete"](facts))


# ── Respuestas a signals (voz de equipo, esquema v1 §6) ──────────────────────

_SIGNAL_REPLIES: dict[str, str] = {
    "greeting": "Hola, soy Mundo del equipo de reclutamiento de Transmontes. "
                "¿Le interesa la vacante de operador de quinta rueda?",
    "on_route": "10-4, sin problema. Cuando tenga oportunidad seguimos por aquí.",
    "farewell": "Gracias, que tenga buen día y maneje con cuidado. Aquí seguimos cuando guste retomar.",
    "dropoff": "Gracias por avisarnos. Si más adelante quiere retomar, con gusto lo apoyamos.",
    "meta_confusion": "Claro, dígame qué parte no quedó clara y la repasamos.",
    "reingreso": "Los reingresos los revisamos directamente aquí. ¿Me da su nombre completo y el motivo por el que salió?",
    "out_of_scope": "Por este medio manejamos solo las vacantes de operador sencillo y full. Para otra área, le paso con un compañero.",
    "complaint": "Una disculpa por la demora, no debió pasar. ¿Sigue interesado en la vacante? Le damos seguimiento de inmediato.",
}

_HANDOFF_REPLY = "Ese punto lo revisa nuestro equipo directamente. Lo dejo anotado para que le den seguimiento."

# Signals que NO deben continuar con la pregunta del funnel.
# greeting incluido: la presentación ya invita ("¿le interesa la vacante?"); no
# encimar una pregunta de perfil en el primer contacto.
_NO_FUNNEL_SIGNALS = {"greeting", "on_route", "farewell", "dropoff", "out_of_scope", "complaint", "reingreso"}


def _generate_rag_answer(question: dict[str, Any], message: str) -> str:
    """Genera la respuesta a una pregunta usando el RAG existente."""
    context = retrieve_preferred_context(
        message, preferred_sources=question.get("preferred_sources") or []
    )
    if not context.get("items"):
        return ("Para ese dato le recomiendo llamarnos de 8:00 a 17:30 hrs y se lo confirmamos.")

    contract = {
        "intent": question.get("intent"),
        "route": "rag",
        "risk_level": question.get("risk_level", "low"),
        "recognized_terms": [question.get("intent")],
        "preferred_sources": question.get("preferred_sources") or [],
        "policies": [],
    }
    prompt = build_generation_prompt(
        message=message,
        knowledge_contract=contract,
        context_text=context.get("context_text") or "",
    )
    return (call_llm(prompt) or "").strip()


def plan_and_respond(
    enriched: dict[str, Any],
    message: str,
    known_facts: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Planea acciones y genera el texto de respuesta. No persiste ni envía."""
    known_facts = dict(known_facts or {})
    primary = enriched.get("primary_intent")
    questions = enriched.get("questions") or []
    answers = enriched.get("answers_to_persist") or []

    action_order: list[str] = []
    response_parts: list[str] = []

    # facts proyectados (multi-intent registra en silencio → afectan el funnel)
    merged = {**known_facts, **{a["field"]: a["value"] for a in answers}}
    if answers:
        action_order.append("persist_answers_silently")

    # 1. Handoff (riesgo / escalamiento) — corta el flujo
    if enriched.get("requires_human") or primary in {"reingreso", "out_of_scope", "complaint"}:
        action_order.append("human_handoff")
        reply = _SIGNAL_REPLIES.get(primary, _HANDOFF_REPLY)
        return {
            "recommended_action_order": action_order,
            "facts_to_persist": answers,
            "response_text": reply,
            "core_completeness": core_completeness(merged),
            "handoff": True,
        }

    # 2. Responder preguntas (RAG) — prioriza la primera; ofrece la segunda
    if questions:
        action_order.append("answer_primary_question")
        response_parts.append(_generate_rag_answer(questions[0], message))
        if len(questions) > 1:
            action_order.append("offer_secondary_question")
            response_parts.append("Si gusta, también le platico sobre lo otro que preguntó.")

    # 3. Signal sin pregunta (saludo, on_route, etc.)
    elif primary in _SIGNAL_REPLIES:
        response_parts.append(_SIGNAL_REPLIES[primary])

    # 4. Siguiente pregunta del funnel (salvo signals que no deben continuar)
    if primary not in _NO_FUNNEL_SIGNALS:
        nq = next_funnel_question(merged)
        if nq:
            action_order.append("emit_funnel_question")
            response_parts.append(nq)
        else:
            action_order.append("mark_profile_ready")
            if not response_parts:
                response_parts.append(
                    "Con eso ya tenemos su información completa. Nuestro equipo la revisa "
                    "y le contactamos para continuar."
                )

    # Fallback si nada produjo texto (ej. acknowledgement con núcleo completo)
    if not response_parts:
        response_parts.append("Anotado, aquí seguimos con su proceso.")

    return {
        "recommended_action_order": action_order,
        "facts_to_persist": answers,
        "response_text": "\n\n".join(p for p in response_parts if p),
        "core_completeness": core_completeness(merged),
        "handoff": False,
    }
