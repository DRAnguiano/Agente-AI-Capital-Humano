from typing import Any

from app.graphs.hr_state import HRState
from app.indexer import call_llm, retrieve_context_for_guardrail
from app.orchestrator import orchestrate_message
from app.persona_config import SYSTEM_PROMPT


MIN_RELEVANCE_SCORE = 0.30
PROFILE_PENDING_STAGES = {"ASK_CITY", "ASK_LICENSE", "ASK_EXPERIENCE", "ASK_APTO", "ASK_AVAILABILITY"}
SIDE_QUESTION_SOFT_CLOSE = "Si le interesa, con gusto podemos continuar con su proceso."
GENERATION_ERROR_MARKERS = {
    "tuve un problema al generar la respuesta",
    "por favor intenta de nuevo",
    "error al generar",
    "internal_error",
    "exception",
}


def _source_payload(item: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "source": item.get("source"),
        "score": round(item.get("score") or 0, 4),
    }
    if item.get("rerank_score") is not None:
        payload["rerank_score"] = round(item.get("rerank_score") or 0, 4)
    if item.get("chroma_score") is not None:
        payload["chroma_score"] = round(item.get("chroma_score") or 0, 4)
    if item.get("id"):
        payload["id"] = item.get("id")
    return payload


def _effective_question(state: HRState) -> str:
    rewrite = state.get("contextual_rewrite") or {}
    if rewrite.get("should_use_rewrite") and rewrite.get("rewritten"):
        return str(rewrite.get("rewritten") or "").strip()
    return str(state.get("question") or state.get("message") or "").strip()


def _expand_retrieval_query(question: str) -> str:
    """
    Make short candidate side-questions more retrievable in HR documents.

    This does not change the candidate-facing question. It only expands the
    vector search query with domain terms so Chroma can find the right internal
    policy chunk for terse messages like "¿Cómo pagan el viaje?".
    """
    text = (question or "").strip()
    lower = text.lower()
    if not text:
        return ""

    pay_terms = ("pagan", "pago", "sueldo", "salario", "kilometro", "kilómetro", "viaje", "compensación")
    route_terms = ("ruta", "rutas", "base", "bases", "foráneo", "foraneo")
    requirement_terms = ("requisito", "requisitos", "licencia", "apto", "documento", "documentos")

    if any(term in lower for term in pay_terms):
        return (
            f"{text}\n"
            "esquema de pago operador quinta rueda tractocamión viaje sueldo base pago variable por kilómetro "
            "prestaciones bonos full semanal neto Capital Humano"
        )

    if any(term in lower for term in route_terms):
        return (
            f"{text}\n"
            "rutas bases operación operador quinta rueda tractocamión foráneo local base trabajo Transmontes"
        )

    if any(term in lower for term in requirement_terms):
        return (
            f"{text}\n"
            "requisitos operador quinta rueda licencia federal apto médico documentos experiencia disponibilidad viaje"
        )

    return text


def _is_profile_side_question(state: HRState) -> bool:
    current_stage = state.get("current_stage") or "START"
    route = state.get("route")
    classifier = state.get("classifier") or {}
    intent = state.get("intent") or classifier.get("classifier_intent")

    if current_stage not in PROFILE_PENDING_STAGES:
        return False
    if route != "rag":
        return False
    return intent not in {"profile_answer", "candidate_interest"}


def _append_side_question_close(answer: str, state: HRState) -> str:
    if not _is_profile_side_question(state):
        return answer

    cleaned = (answer or "").strip()
    if not cleaned:
        return SIDE_QUESTION_SOFT_CLOSE
    if SIDE_QUESTION_SOFT_CLOSE.lower() in cleaned.lower():
        return cleaned
    return f"{cleaned}\n\n{SIDE_QUESTION_SOFT_CLOSE}"


def _looks_like_generation_error(answer: str) -> bool:
    normalized = (answer or "").strip().lower()
    return any(marker in normalized for marker in GENERATION_ERROR_MARKERS)


def normalize_input_node(state: HRState) -> dict[str, Any]:
    message = (state.get("message") or "").strip()
    channel = (state.get("channel") or "chatwoot").strip().lower()
    channel_user_id = str(
        state.get("channel_user_id")
        or state.get("phone")
        or state.get("chatwoot_contact_id")
        or state.get("chatwoot_conversation_id")
        or "unknown"
    ).strip()
    return {
        "message": message,
        "question": message,
        "channel": channel,
        "channel_user_id": channel_user_id,
    }


def legacy_orchestrator_node(state: HRState) -> dict[str, Any]:
    result = orchestrate_message(
        channel=state["channel"],
        channel_user_id=state["channel_user_id"],
        username=state.get("username"),
        phone=state.get("phone"),
        message=state["message"],
        external_message_id=state.get("external_message_id"),
    )
    reply = (result.get("reply") or result.get("text") or "").strip()
    return {
        "legacy_result": result,
        "status": result.get("status", "ok"),
        "conversation_key": result.get("conversation_key"),
        "reply": reply,
        "text": reply,
        "current_stage": result.get("current_stage"),
        "next_stage": result.get("current_stage"),
        "requires_human": bool(result.get("requires_human", False)),
        "risk_level": result.get("risk_level", "low"),
        "intent": result.get("intent"),
        "sources": result.get("sources", []),
        "route": "legacy_orchestrator",
    }


def retrieve_documents_node(state: HRState) -> dict[str, Any]:
    question = _effective_question(state)
    retrieval_query = _expand_retrieval_query(question)
    docs = retrieve_context_for_guardrail(retrieval_query or question, top_k=5)
    return {
        "question": question,
        "retrieval_query": retrieval_query,
        "retrieved_docs": docs,
        "sources": [_source_payload(item) for item in docs],
        "events": [
            {
                "type": "rag_documents_retrieved",
                "question": question,
                "retrieval_query": retrieval_query,
                "retrieved_docs_count": len(docs),
            }
        ],
    }


def grade_documents_node(state: HRState) -> dict[str, Any]:
    docs = state.get("retrieved_docs", [])
    relevant_docs = [item for item in docs if (item.get("score") or 0) >= MIN_RELEVANCE_SCORE]
    return {
        "relevant_docs": relevant_docs,
        "docs_are_relevant": bool(relevant_docs),
        "sources": [_source_payload(item) for item in relevant_docs],
    }


def fallback_no_context_node(state: HRState) -> dict[str, Any]:
    reply = (
        "No tengo información confirmada en los documentos internos para responder eso con seguridad. "
        "Capital Humano debe validarlo directamente antes de darte una respuesta final."
    )
    reply = _append_side_question_close(reply, state)
    return {
        "reply": reply,
        "text": reply,
        "requires_human": True,
        "risk_level": state.get("risk_level", "medium"),
        "next_stage": state.get("current_stage") or "HUMAN_REVIEW_REQUIRED",
        "labels": ["requiere_humano", "sin_contexto_confirmado"],
        "events": [
            {
                "type": "rag_side_question_preserved_stage",
                "current_stage": state.get("current_stage"),
                "side_question": _is_profile_side_question(state),
            }
        ],
    }


def generate_answer_node(state: HRState) -> dict[str, Any]:
    question = state.get("question") or state.get("message") or ""
    relevant_docs = state.get("relevant_docs", [])
    context_text = "\n\n---\n\n".join(item.get("text", "") for item in relevant_docs)
    current_stage = state.get("current_stage") or "START"
    side_question = _is_profile_side_question(state)

    side_question_instruction = ""
    if side_question:
        side_question_instruction = f"""
IMPORTANTE SOBRE FLUJO DE FORMULARIO:
- La conversación está en etapa pendiente: {current_stage}.
- El candidato hizo una pregunta lateral, no respondió el campo pendiente.
- Responde su pregunta con naturalidad.
- No avances el formulario.
- No hagas la siguiente pregunta del formulario.
- No repitas agresivamente la pregunta pendiente.
- Cierra suavemente con: "{SIDE_QUESTION_SOFT_CLOSE}"
""".strip()

    prompt = f"""
{SYSTEM_PROMPT}

=== CONTEXTO INTERNO CONFIRMADO ===
{context_text}

=== MENSAJE DEL CANDIDATO ===
{question}

=== ESTADO CONVERSACIONAL ===
current_stage: {current_stage}
side_question_during_profile: {side_question}

{side_question_instruction}

INSTRUCCIONES:
1. Responde únicamente con base en el contexto interno.
2. No inventes sueldo, prestaciones, rutas, descansos, pago por kilómetro, contratación ni condiciones.
3. Si falta información, indica que Capital Humano debe confirmarlo.
4. Responde breve, natural y en español.
5. No cierres con frases genéricas como "si tienes otra duda", "puedo ayudarte" o similares.
6. Si es una pregunta lateral durante formulario, no empujes el proceso ni hagas preguntas del formulario.

RESPUESTA:
"""

    events = []
    try:
        answer = call_llm(prompt).strip()
    except Exception as exc:
        answer = ""
        events.append({"type": "rag_generation_exception", "error": f"{type(exc).__name__}: {exc}"})

    answer = _append_side_question_close(answer, state)
    return {"draft_answer": answer, "events": events}


def hallucination_check_node(state: HRState) -> dict[str, Any]:
    draft = (state.get("draft_answer") or "").strip()
    relevant_docs = state.get("relevant_docs", [])

    if not draft or not relevant_docs:
        return {"hallucination_check": "FAIL"}
    if _looks_like_generation_error(draft):
        return {"hallucination_check": "FAIL"}
    return {"hallucination_check": "PASS"}


def answer_check_node(state: HRState) -> dict[str, Any]:
    draft = (state.get("draft_answer") or "").strip()

    if state.get("hallucination_check") != "PASS" or len(draft) < 10 or _looks_like_generation_error(draft):
        reply = (
            "No tengo información confirmada suficiente para responder eso con seguridad. "
            "Capital Humano debe validarlo directamente."
        )
        reply = _append_side_question_close(reply, state)
        return {
            "answer_check": "FAIL",
            "reply": reply,
            "text": reply,
            "requires_human": True,
            "next_stage": state.get("current_stage"),
            "labels": ["requiere_humano", "respuesta_no_validada"],
            "events": [
                {
                    "type": "rag_answer_rejected",
                    "reason": "generation_error_or_invalid_answer",
                    "draft_preview": draft[:120],
                }
            ],
        }

    return {
        "answer_check": "PASS",
        "reply": draft,
        "text": draft,
        "next_stage": state.get("current_stage") if _is_profile_side_question(state) else state.get("next_stage"),
        "events": [
            {
                "type": "rag_answered_side_question" if _is_profile_side_question(state) else "rag_answered",
                "current_stage": state.get("current_stage"),
                "stage_preserved": _is_profile_side_question(state),
            }
        ],
    }


def save_output_node(state: HRState) -> dict[str, Any]:
    reply = (state.get("reply") or state.get("text") or "").strip()
    return {"reply": reply, "text": reply, "status": state.get("status", "ok")}
