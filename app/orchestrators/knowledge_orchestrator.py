from __future__ import annotations

import os
import re
import time
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from app.db import get_conversation_state, log_event, make_conversation_key, save_message, update_stage, upsert_conversation
from app.indexer import call_llm
from app.knowledge.context_builder import build_generation_prompt, estimate_llm_cost, retrieve_preferred_context
from app.knowledge.neo4j_client import resolve_message
from app.knowledge.text_normalizer import normalize_text
from app.lead_memory.repository import (
    get_lead_memory,
    log_lead_event,
    save_lead_message,
    update_lead_summary,
    upsert_lead_fact,
    upsert_lead_identity,
)


CONTROLLED_CLARIFICATION_REPLY = (
    "Para responderte bien, ¿me puedes explicar a qué te refieres? "
    "Así evitamos malinterpretar tu mensaje."
)

CONTROLLED_FALLBACK_REPLY = (
    "No quiero darte información incorrecta. Puedo ayudarte con pago, documentos, "
    "requisitos, ubicación, licencia, apto médico o disponibilidad."
)

NO_CONTEXT_REPLY = (
    "No encontré información interna suficiente para responder eso con seguridad. "
    "Lo correcto es que Capital Humano lo valide antes de confirmarte el dato."
)

DOCUMENT_ACK_REPLY = (
    "Perfecto, gracias por avisar. Lo dejo registrado para que Capital Humano pueda "
    "validarlo y darte el siguiente paso del proceso."
)

FAREWELL_REPLY = (
    "Gracias a usted. Que tenga buen día y maneje con cuidado. Dejamos su seguimiento abierto; "
    "cuando guste retomar el proceso, por aquí lo apoyamos."
)

GENERIC_CLOSING_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\s*Si tienes (m[aá]s |alguna )?(otra )?duda[s]?,? puedo ayudarte\.?\s*$", re.IGNORECASE),
    re.compile(r"\s*Si necesitas m[aá]s informaci[oó]n,? puedo ayudarte[^.?!]*(\.|!|\?)?\s*$", re.IGNORECASE),
    re.compile(r"\s*Estoy aqu[ií] para ayudarte\.?\s*$", re.IGNORECASE),
    re.compile(r"\s*¿?Tienes alguna otra duda\??\s*$", re.IGNORECASE),
)

PROFILE_ACK_HINTS = (
    "ya mande", "ya mandé", "ya envie", "ya envié", "ya subi", "ya subí",
    "ya cargue", "ya cargué", "ya lo mande", "ya lo mandé", "ya los mande",
    "ya los mandé", "ya quedo", "ya quedó", "listo", "ahi esta", "ahí está",
)

DOCUMENT_WORDS = (
    "documento", "documentos", "doc", "docs", "papel", "papeles", "informacion",
    "información", "datos", "licencia", "apto", "ine", "curp", "comprobante", "cartas",
)

BUSINESS_QUESTION_TERMS = (
    "pago", "pagan", "sueldo", "salario", "documento", "documentos", "papeles",
    "requisitos", "licencia", "apto", "ruta", "rutas", "vacante", "vacantes",
    "antidoping", "prueba", "orina", "base", "bases",
)

FAREWELL_HINTS = (
    "gracias señor", "gracias senor", "gracias muy amable", "muchas gracias",
    "gracias", "pase buen dia", "pase buen día",
    "hasta luego", "nos vemos", "saludos", "que este bien", "que esté bien",
    "luego le escribo", "luego le marco", "lo retomo luego",
)

# "buen dia" / "buen día" alone are ambiguous (greeting OR farewell).
# Block farewell detection when the message opens with a clear greeting word.
GREETING_GUARD_TERMS = (
    "hola", "ola", "holaa", "hey", "ei",
    "buenos dias", "buenos días", "buenas tardes", "buenas noches", "buenas",
    "buen dia", "buen día",
)

DISALLOWED_FREE_CHAT_TERMS = (
    "droga", "drogas", "mota", "marihuana", "mariguana", "cristal", "perico",
    "cocaina", "cocaína", "metanfetamina", "huachicol", "robo", "arma",
    "licencia falsa", "documento falso", "evadir", "burlar",
)


STAGE_LABELS = {
    "new": "Nuevo lead",
    "interested": "Interesado",
    "vacancy_info_shared": "Información de vacante compartida",
    "profile_hint_collected": "Perfil preliminar detectado",
    "documents_pending": "Documentos pendientes",
    "documents_received": "Documentos recibidos / por validar",
    "apto_pending_update": "Apto médico por actualizar",
    "safety_review": "Revisión de seguridad",
    "followup_pending": "Seguimiento pendiente",
    "human_review": "Revisión humana",
    "lost": "Perdido / abandonó",
    "closed": "Cerrado",
}


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _route_flags(route: str, risk_level: str) -> dict[str, bool]:
    route = route or "fallback"
    risk = (risk_level or "low").lower()
    return {
        "requires_rag": route == "rag",
        "requires_human": route in {"human_handoff", "policy_boundary"} or risk == "high",
        "requires_clarification": route == "clarification",
    }


def _clean_reply(text: str) -> str:
    clean = (text or "").strip()
    clean = re.sub(r"<think>.*?</think>", "", clean, flags=re.IGNORECASE | re.DOTALL)
    clean = re.sub(r"</?think>", "", clean, flags=re.IGNORECASE).strip()
    for pattern in GENERIC_CLOSING_PATTERNS:
        clean = pattern.sub("", clean).strip()
    return clean


def _controlled_reply_from_contract(contract: dict[str, Any]) -> str:
    template = contract.get("reply_template")
    if isinstance(template, dict) and template.get("text"):
        return str(template["text"])
    if contract.get("requires_clarification"):
        return CONTROLLED_CLARIFICATION_REPLY
    if contract.get("requires_human"):
        return "Ese punto debe revisarlo Capital Humano antes de continuar. Lo dejo anotado para seguimiento."
    return CONTROLLED_FALLBACK_REPLY


def _message_has_any(message: str, terms: tuple[str, ...]) -> bool:
    text = normalize_text(message)
    return any(normalize_text(term) in text for term in terms)


def _is_time_question(message: str) -> bool:
    text = normalize_text(message)
    return any(
        phrase in text
        for phrase in (
            "que hora es", "qué hora es", "hora es", "me dices la hora",
            "tiene la hora", "sabes la hora",
        )
    )


def _time_reply() -> str:
    now = datetime.now(ZoneInfo("America/Mexico_City"))
    time_text = now.strftime("%-I:%M %p").lower().replace("am", "a. m.").replace("pm", "p. m.")
    return f"En Torreón son las {time_text}; es la misma zona horaria del centro de México."


def _looks_like_farewell(message: str) -> bool:
    text = normalize_text(message)
    if not text:
        return False
    if not any(normalize_text(hint) in text for hint in FAREWELL_HINTS):
        return False
    if "?" in message or "¿" in message:
        return False
    # A message that opens with a greeting word is not a farewell.
    # Use startswith so "pase buen dia" (farewell) is not confused with
    # "buen dia" / "hola buen dia" (greetings).
    if any(text.startswith(normalize_text(g)) for g in GREETING_GUARD_TERMS):
        return False
    if _message_has_any(message, BUSINESS_QUESTION_TERMS) and len(text) > 80:
        return False
    return True


def _looks_like_profile_ack(message: str, contract: dict[str, Any]) -> bool:
    has_ack = _message_has_any(message, PROFILE_ACK_HINTS)
    has_document_word = _message_has_any(message, DOCUMENT_WORDS)
    return bool(has_ack and has_document_word)


def _apply_profile_guards(message: str, contract: dict[str, Any]) -> dict[str, Any]:
    if _looks_like_profile_ack(message, contract):
        guarded = dict(contract)
        guarded.update(
            {
                "recognized_terms": list(dict.fromkeys(list(guarded.get("recognized_terms") or []) + ["document_ack"])),
                "intent": "document_submission_ack",
                "route": "profile",
                "risk_level": "low",
                "requires_rag": False,
                "requires_human": False,
                "requires_clarification": False,
                "preferred_sources": [],
                "reply_template": {"id": "document_ack", "text": DOCUMENT_ACK_REPLY},
                "reason": "profile_guard_document_submission_ack",
                "profile_guard_applied": True,
            }
        )
        return guarded
    return contract


def _apply_deterministic_overrides(message: str, contract: dict[str, Any]) -> dict[str, Any]:
    if _looks_like_farewell(message):
        updated = dict(contract)
        updated.update(
            {
                "recognized_terms": ["farewell"],
                "matched_aliases": ["farewell"],
                "intent": "farewell",
                "route": "profile",
                "risk_level": "low",
                "requires_rag": False,
                "requires_human": False,
                "requires_clarification": False,
                "preferred_sources": [],
                "reply_template": {"id": "farewell", "text": FAREWELL_REPLY},
                "reason": "deterministic_farewell_reply",
            }
        )
        return updated

    if _is_time_question(message):
        updated = dict(contract)
        updated.update(
            {
                "recognized_terms": ["local_time"],
                "matched_aliases": ["hora"],
                "intent": "local_time",
                "route": "friendly_smalltalk",
                "risk_level": "low",
                "requires_rag": False,
                "requires_human": False,
                "requires_clarification": False,
                "preferred_sources": [],
                "reason": "deterministic_local_time_reply",
            }
        )
        return updated

    return contract


def _is_safe_for_friendly_llm(message: str, contract: dict[str, Any]) -> bool:
    if contract.get("requires_human") or str(contract.get("risk_level") or "low") == "high":
        return False
    if _message_has_any(message, DISALLOWED_FREE_CHAT_TERMS):
        return False
    return True


def _should_use_friendly_llm(message: str, contract: dict[str, Any]) -> bool:
    if not _env_bool("KNOWLEDGE_FRIENDLY_LLM_ENABLED", True):
        return False
    if not _is_safe_for_friendly_llm(message, contract):
        return False

    route = str(contract.get("route") or "fallback")
    intent = str(contract.get("intent") or "unknown")
    if route == "friendly_smalltalk" or intent in {"friendly_smalltalk", "casual_recruiter_reply"}:
        return True
    if route == "fallback" and intent == "unknown":
        return True
    return False


def _format_lead_memory_for_prompt(memory: dict[str, Any] | None) -> str:
    if not memory:
        return "Sin memoria previa útil."
    lead = memory.get("lead") or {}
    facts = memory.get("facts") or []
    messages = memory.get("messages") or []

    fact_text = "; ".join(
        f"{row.get('fact_group')}.{row.get('fact_key')}={row.get('fact_value')}"
        for row in facts[:8]
        if isinstance(row, dict)
    ) or "Sin hechos activos."

    recent = []
    for row in messages[-4:]:
        if not isinstance(row, dict):
            continue
        role = "Candidato" if row.get("role") == "user" else "Asistente"
        msg = str(row.get("message") or "")[:180]
        recent.append(f"{role}: {msg}")

    return (
        f"Etapa RH: {lead.get('funnel_stage_label') or lead.get('funnel_stage') or 'N/D'}. "
        f"Siguiente acción: {lead.get('next_best_action') or 'N/D'}. "
        f"Resumen: {lead.get('memory_summary') or 'N/D'}. "
        f"Hechos: {fact_text}. "
        f"Historial reciente: {' | '.join(recent) if recent else 'Sin historial previo útil.'}"
    )


def _answer_friendly_message(message: str, contract: dict[str, Any], lead_memory: dict[str, Any] | None = None) -> dict[str, Any]:
    started = time.perf_counter()
    memory_text = _format_lead_memory_for_prompt(lead_memory)
    prompt = f"""
Eres Mundo, asistente de Capital Humano de Transmontes para reclutamiento de operadores de quinta rueda.

Responde al candidato de forma breve, humana y natural.
Puedes usar humor ligero si queda bien.
No inventes datos internos de la empresa.
No digas cuánto gana el reclutador o personal interno.
No prometas contratación.
No hables de drogas, sustancias, delitos, evasión de pruebas ni temas ilegales si el candidato no lo menciona.
No des asesoría médica, legal ni financiera.
Haz máximo una pregunta por respuesta.
Usa la memoria del lead solo como recordatorio; no la conviertas en interrogatorio.
Después de responder, regresa suavemente al proceso de reclutamiento si aplica.

Memoria del lead: {memory_text}
Mensaje del candidato: {message!r}
""".strip()

    if not _env_bool("KNOWLEDGE_FRIENDLY_LLM_GENERATION_ENABLED", True):
        debug_reply = "Puedo salirme tantito del guion, pero sin inventarte datos. ¿Quieres que revisemos pago, documentos o requisitos?"
        return {
            "reply": debug_reply,
            "llm_prompt_chars": len(prompt),
            "llm_reply_chars": len(debug_reply),
            "llm_cost_estimate": estimate_llm_cost(prompt, debug_reply),
            "timings": {"friendly_total_ms": round((time.perf_counter() - started) * 1000, 2), "friendly_generate_ms": 0.0},
            "friendly_generation_used": False,
            "friendly_generation_skipped_reason": "generation_disabled",
        }

    gen_started = time.perf_counter()
    raw_reply = call_llm(prompt)
    generate_ms = round((time.perf_counter() - gen_started) * 1000, 2)
    reply = _clean_reply(raw_reply)

    if not reply:
        reply = "Aquí ando, listo para ayudarte sin inventarte datos. ¿Revisamos pago, documentos o requisitos?"

    return {
        "reply": reply,
        "llm_prompt_chars": len(prompt),
        "llm_reply_chars": len(reply),
        "llm_cost_estimate": estimate_llm_cost(prompt, reply),
        "timings": {"friendly_total_ms": round((time.perf_counter() - started) * 1000, 2), "friendly_generate_ms": generate_ms},
        "friendly_generation_used": True,
        "friendly_generation_skipped_reason": None,
    }


def _answer_rag_message(message: str, contract: dict[str, Any]) -> dict[str, Any]:
    started = time.perf_counter()
    rag_enabled = _env_bool("KNOWLEDGE_RAG_GENERATION_ENABLED", True)

    context = retrieve_preferred_context(message, preferred_sources=contract.get("preferred_sources") or [])

    if not context.get("items"):
        return {
            "reply": NO_CONTEXT_REPLY,
            "rag_context": context,
            "llm_prompt_chars": 0,
            "llm_reply_chars": len(NO_CONTEXT_REPLY),
            "llm_cost_estimate": estimate_llm_cost("", NO_CONTEXT_REPLY),
            "timings": {"rag_total_ms": round((time.perf_counter() - started) * 1000, 2), "retrieve_context_ms": context.get("timing_ms"), "generate_answer_ms": 0.0},
            "rag_generation_used": False,
            "rag_generation_skipped_reason": context.get("error") or "no_relevant_context",
        }

    prompt = build_generation_prompt(
        message=message,
        knowledge_contract=contract,
        context_text=context.get("context_text") or "",
    )

    if not rag_enabled:
        debug_reply = "RAG detectado y contexto interno recuperado, pero la generación LLM está desactivada por KNOWLEDGE_RAG_GENERATION_ENABLED=false."
        return {
            "reply": debug_reply,
            "rag_context": context,
            "llm_prompt_chars": len(prompt),
            "llm_reply_chars": len(debug_reply),
            "llm_cost_estimate": estimate_llm_cost(prompt, debug_reply),
            "timings": {"rag_total_ms": round((time.perf_counter() - started) * 1000, 2), "retrieve_context_ms": context.get("timing_ms"), "generate_answer_ms": 0.0},
            "rag_generation_used": False,
            "rag_generation_skipped_reason": "generation_disabled",
        }

    gen_started = time.perf_counter()
    raw_reply = call_llm(prompt)
    generate_ms = round((time.perf_counter() - gen_started) * 1000, 2)
    reply = _clean_reply(raw_reply)

    return {
        "reply": reply,
        "rag_context": context,
        "llm_prompt_chars": len(prompt),
        "llm_reply_chars": len(reply),
        "llm_cost_estimate": estimate_llm_cost(prompt, reply),
        "timings": {"rag_total_ms": round((time.perf_counter() - started) * 1000, 2), "retrieve_context_ms": context.get("timing_ms"), "generate_answer_ms": generate_ms},
        "rag_generation_used": True,
        "rag_generation_skipped_reason": None,
    }


def _stage_for_contract(contract: dict[str, Any], message: str) -> str:
    intent = str(contract.get("intent") or "unknown")
    route = str(contract.get("route") or "fallback")
    text = normalize_text(message)

    if contract.get("requires_human"):
        return "human_review"
    if intent == "farewell" or route == "candidate_dropoff_recovery" or intent == "candidate_dropoff_risk":
        return "followup_pending"
    if intent == "document_submission_ack":
        return "documents_received"
    if intent == "requirements_documents":
        if "apto" in text and any(term in text for term in ("vence", "vencer", "venc", "renovar", "actualizo", "actualizar")):
            return "apto_pending_update"
        return "documents_pending"
    if intent in {"payment_compensation", "bases_routes_rest"}:
        return "vacancy_info_shared"
    if intent in {"driving_school", "on_route_safety", "callback_request"}:
        return "profile_hint_collected"
    if intent == "drug_testing_urine":
        return "safety_review"
    if intent in {"friendly_smalltalk", "local_time", "greeting"}:
        return "interested"
    return "interested" if route == "friendly_smalltalk" else "new"


def _next_action_for_stage(stage: str, contract: dict[str, Any]) -> str | None:
    intent = str(contract.get("intent") or "unknown")
    if stage == "apto_pending_update":
        return "Dar seguimiento cuando el candidato actualice apto médico."
    if stage == "documents_pending":
        return "Invitar al candidato a enviar documentos cuando tenga oportunidad, sin presionarlo."
    if stage == "documents_received":
        return "Capital Humano debe validar documentos recibidos."
    if stage == "followup_pending":
        return "Mantener seguimiento abierto para retomar conversación."
    if stage == "safety_review":
        return "Responder con política interna y validar con Capital Humano si escala."
    if intent == "payment_compensation":
        return "Resolver dudas de pago/ruta y luego avanzar suavemente a documentos."
    return None


def _memory_summary_for_stage(stage: str, message: str, contract: dict[str, Any]) -> str | None:
    intent = str(contract.get("intent") or "unknown")
    if stage == "apto_pending_update":
        return "El candidato mencionó que su apto médico está vencido o próximo a vencer."
    if stage == "documents_received":
        return "El candidato indicó que ya envió documentos o información para el proceso."
    if intent == "payment_compensation":
        return "El candidato preguntó por pago/compensación."
    if intent == "requirements_documents":
        return "El candidato preguntó por documentos o requisitos."
    if intent == "farewell":
        return "El candidato se despidió cordialmente; seguimiento queda abierto."
    return None


def _store_lead_memory_updates(
    *,
    lead_key: str,
    conversation_key: str,
    message: str,
    contract: dict[str, Any],
    stage_from: str | None,
    stage_to: str,
    reply: str,
) -> dict[str, Any]:
    """Write useful memory to v2 without letting it govern the conversation."""
    facts_written: list[str] = []
    text = normalize_text(message)
    intent = str(contract.get("intent") or "unknown")
    route = str(contract.get("route") or "fallback")

    source_msg = save_lead_message(
        lead_key=lead_key,
        conversation_key=conversation_key,
        role="user",
        message=message,
    )
    source_message_id = source_msg.get("id") if source_msg else None

    save_lead_message(
        lead_key=lead_key,
        conversation_key=conversation_key,
        role="assistant",
        message=reply,
    )

    if any(term in text for term in ("quinta rueda", "5ta rueda", "5ta", "kinta rueda")):
        upsert_lead_fact(
            lead_key=lead_key,
            fact_group="role_fit",
            fact_key="operator_type",
            fact_value="operador_5ta_rueda",
            confidence=0.90,
            source_message_id=source_message_id,
            source_text=message,
        )
        facts_written.append("role_fit.operator_type")

    if "apto" in text and any(term in text for term in ("vence", "vencer", "venc", "vencido", "renovar", "actualizar", "dos meses", "2 meses")):
        value = "expires_in_2_months" if any(term in text for term in ("2 meses", "dos meses")) else "pending_update"
        upsert_lead_fact(
            lead_key=lead_key,
            fact_group="document",
            fact_key="apto_status",
            fact_value=value,
            confidence=0.90,
            source_message_id=source_message_id,
            source_text=message,
        )
        facts_written.append("document.apto_status")

    if intent == "document_submission_ack":
        upsert_lead_fact(
            lead_key=lead_key,
            fact_group="documents",
            fact_key="submission_status",
            fact_value="candidate_says_sent",
            confidence=0.85,
            source_message_id=source_message_id,
            source_text=message,
        )
        facts_written.append("documents.submission_status")

    if intent == "payment_compensation":
        upsert_lead_fact(
            lead_key=lead_key,
            fact_group="interest",
            fact_key="payment",
            fact_value="asked",
            confidence=0.80,
            source_message_id=source_message_id,
            source_text=message,
        )
        facts_written.append("interest.payment")

    if intent == "requirements_documents":
        upsert_lead_fact(
            lead_key=lead_key,
            fact_group="interest",
            fact_key="requirements_documents",
            fact_value="asked",
            confidence=0.80,
            source_message_id=source_message_id,
            source_text=message,
        )
        facts_written.append("interest.requirements_documents")

    event_type = f"intent_{intent}" if intent and intent != "unknown" else "message_processed"
    log_lead_event(
        lead_key=lead_key,
        conversation_key=conversation_key,
        event_type=event_type,
        intent=intent,
        route=route,
        stage_from=stage_from,
        stage_to=stage_to,
        risk_level=str(contract.get("risk_level") or "low"),
        requires_human=bool(contract.get("requires_human")),
        metadata={
            "reason": contract.get("reason"),
            "recognized_terms": contract.get("recognized_terms"),
            "matched_aliases": contract.get("matched_aliases"),
            "facts_written": facts_written,
        },
    )

    update_lead_summary(
        lead_key=lead_key,
        funnel_stage=stage_to,
        next_best_action=_next_action_for_stage(stage_to, contract),
        memory_summary=_memory_summary_for_stage(stage_to, message, contract),
        facts_summary={"last_intent": intent, "last_route": route, "last_stage": stage_to},
        risk_level=str(contract.get("risk_level") or "low"),
        requires_human=bool(contract.get("requires_human")),
    )

    memory = get_lead_memory(lead_key=lead_key)
    return {"facts_written": facts_written, "memory": memory}


def handle_message(payload: dict[str, Any]) -> dict[str, Any]:
    """Resolve a candidate message through Neo4j and optionally answer with controlled RAG."""
    started = time.perf_counter()
    channel = str(payload.get("channel") or "api").strip()
    channel_user_id = str(payload.get("channel_user_id") or "unknown").strip()
    username = payload.get("username")
    phone = payload.get("phone")
    message = str(payload.get("message") or "").strip()

    identity = upsert_conversation(channel=channel, channel_user_id=channel_user_id, username=username, phone=phone)
    conversation_key = identity.get("conversation_key") or make_conversation_key(channel, channel_user_id)
    state = get_conversation_state(conversation_key)
    conversation = state.get("conversation") or {}

    lead_identity = upsert_lead_identity(
        channel=channel,
        channel_user_id=channel_user_id,
        username=username,
        phone=phone,
        chatwoot_account_id=payload.get("account_id"),
        chatwoot_inbox_id=payload.get("chatwoot_inbox_id") or payload.get("inbox_id"),
        chatwoot_conversation_id=payload.get("chatwoot_conversation_id"),
        chatwoot_contact_id=payload.get("chatwoot_contact_id"),
        external_metadata={"source": "knowledge_orchestrator"},
    )
    lead_key = lead_identity["lead_key"]
    lead_memory_before = get_lead_memory(lead_key=lead_key)
    lead_stage_from = (lead_memory_before.get("lead") or {}).get("funnel_stage")

    save_message(conversation_key, "user", message)

    contract = resolve_message(message, conversation_state=conversation)
    contract = _apply_profile_guards(message, contract)
    contract = _apply_deterministic_overrides(message, contract)

    flags = _route_flags(str(contract.get("route") or "fallback"), str(contract.get("risk_level") or "low"))
    contract.update({**flags, "requires_rag": bool(contract.get("requires_rag")) and flags["requires_rag"]})

    current_stage = str(conversation.get("current_stage") or "START")
    next_stage = "HUMAN_REVIEW_REQUIRED" if contract.get("requires_human") else current_stage
    lead_stage_to = _stage_for_contract(contract, message)

    rag_result: dict[str, Any] | None = None
    friendly_result: dict[str, Any] | None = None

    if contract.get("intent") == "local_time":
        reply = _time_reply()
    elif contract.get("requires_rag"):
        rag_result = _answer_rag_message(message, contract)
        reply = rag_result["reply"]
    elif _should_use_friendly_llm(message, contract):
        if contract.get("route") == "fallback" and contract.get("intent") == "unknown":
            contract.update({"route": "friendly_smalltalk", "intent": "friendly_smalltalk", "reason": "safe_unknown_routed_to_friendly_llm"})
            lead_stage_to = _stage_for_contract(contract, message)
        friendly_result = _answer_friendly_message(message, contract, lead_memory_before)
        reply = friendly_result["reply"]
    else:
        reply = _controlled_reply_from_contract(contract)

    update_stage(
        conversation_key=conversation_key,
        stage_to=next_stage,
        intent=contract.get("intent"),
        risk_level=contract.get("risk_level") or "low",
        requires_human=bool(contract.get("requires_human")),
    )

    lead_write = _store_lead_memory_updates(
        lead_key=lead_key,
        conversation_key=conversation_key,
        message=message,
        contract=contract,
        stage_from=lead_stage_from,
        stage_to=lead_stage_to,
        reply=reply,
    )
    lead_memory_after = lead_write.get("memory") or {}

    metadata = {
        "route": contract.get("route"),
        "recognized_terms": contract.get("recognized_terms"),
        "matched_aliases": contract.get("matched_aliases"),
        "preferred_sources": contract.get("preferred_sources"),
        "reason": contract.get("reason"),
        "all_matches": contract.get("all_matches"),
        "profile_guard_applied": contract.get("profile_guard_applied"),
        "lead_memory_v2": {
            "lead_key": lead_key,
            "stage_from": lead_stage_from,
            "stage_to": lead_stage_to,
            "facts_written": lead_write.get("facts_written"),
        },
    }
    if rag_result:
        metadata.update(
            {
                "rag_generation_used": rag_result.get("rag_generation_used"),
                "rag_generation_skipped_reason": rag_result.get("rag_generation_skipped_reason"),
                "rag_sources": (rag_result.get("rag_context") or {}).get("sources"),
                "rag_source_filter_used": (rag_result.get("rag_context") or {}).get("source_filter_used"),
                "rag_items_count": len((rag_result.get("rag_context") or {}).get("items") or []),
                "llm_cost_estimate": rag_result.get("llm_cost_estimate"),
                "timings": rag_result.get("timings"),
            }
        )
    if friendly_result:
        metadata.update(
            {
                "friendly_generation_used": friendly_result.get("friendly_generation_used"),
                "friendly_generation_skipped_reason": friendly_result.get("friendly_generation_skipped_reason"),
                "llm_cost_estimate": friendly_result.get("llm_cost_estimate"),
                "timings": friendly_result.get("timings"),
            }
        )

    log_event(
        conversation_key=conversation_key,
        event_type="knowledge_contract_resolved",
        stage_from=current_stage,
        stage_to=next_stage,
        intent=contract.get("intent"),
        risk_level=contract.get("risk_level") or "low",
        requires_human=bool(contract.get("requires_human")),
        metadata=metadata,
    )

    save_message(conversation_key, "assistant", reply)

    timings = {"total_ms": round((time.perf_counter() - started) * 1000, 2)}
    if rag_result and isinstance(rag_result.get("timings"), dict):
        timings.update(rag_result["timings"])
    if friendly_result and isinstance(friendly_result.get("timings"), dict):
        timings.update(friendly_result["timings"])

    sources = []
    if rag_result:
        for item in (rag_result.get("rag_context") or {}).get("items") or []:
            sources.append({"source": item.get("source"), "score": round(float(item.get("score") or 0), 4), "id": item.get("id")})

    cost = rag_result.get("llm_cost_estimate") if rag_result else friendly_result.get("llm_cost_estimate") if friendly_result else None

    return {
        "status": "ok",
        "selected_route": contract.get("route"),
        "intent": contract.get("intent"),
        "risk_level": contract.get("risk_level"),
        "requires_rag": contract.get("requires_rag"),
        "requires_human": contract.get("requires_human"),
        "requires_clarification": contract.get("requires_clarification"),
        "reply": reply,
        "text": reply,
        "conversation_key": conversation_key,
        "lead_key": lead_key,
        "lead_memory": lead_memory_after,
        "sources": sources,
        "knowledge_contract": contract,
        "rag": {
            "used": bool(rag_result and rag_result.get("rag_generation_used")),
            "skipped_reason": rag_result.get("rag_generation_skipped_reason") if rag_result else None,
            "preferred_sources": contract.get("preferred_sources") or [],
            "retrieved_sources": (rag_result.get("rag_context") or {}).get("sources") if rag_result else [],
            "items_count": len((rag_result.get("rag_context") or {}).get("items") or []) if rag_result else 0,
        },
        "friendly": {
            "used": bool(friendly_result and friendly_result.get("friendly_generation_used")),
            "skipped_reason": friendly_result.get("friendly_generation_skipped_reason") if friendly_result else None,
        },
        "cost": cost,
        "timings": timings,
        "graph_trace": {
            "mode": "knowledge",
            "route": contract.get("route"),
            "intent": contract.get("intent"),
            "risk_level": contract.get("risk_level"),
            "requires_rag": contract.get("requires_rag"),
            "requires_human": contract.get("requires_human"),
            "requires_clarification": contract.get("requires_clarification"),
            "lead_memory_v2": {
                "lead_key": lead_key,
                "stage_from": lead_stage_from,
                "stage_to": lead_stage_to,
                "facts_written": lead_write.get("facts_written"),
            },
            "timings": timings,
            "cost": cost,
            "nodes": [
                {
                    "node": "neo4j_knowledge_node",
                    "decision": contract.get("route"),
                    "recognized_terms": contract.get("recognized_terms"),
                    "matched_aliases": contract.get("matched_aliases"),
                    "preferred_sources": contract.get("preferred_sources"),
                    "reason": contract.get("reason"),
                    "profile_guard_applied": contract.get("profile_guard_applied"),
                },
                {
                    "node": "lead_memory_v2_writer",
                    "decision": lead_stage_to,
                    "lead_key": lead_key,
                    "facts_written": lead_write.get("facts_written"),
                },
                {
                    "node": "controlled_rag_generation",
                    "decision": "used" if rag_result and rag_result.get("rag_generation_used") else "skipped",
                    "sources": (rag_result.get("rag_context") or {}).get("sources") if rag_result else [],
                    "items_count": len((rag_result.get("rag_context") or {}).get("items") or []) if rag_result else 0,
                    "skipped_reason": rag_result.get("rag_generation_skipped_reason") if rag_result else None,
                },
                {
                    "node": "friendly_llm_generation",
                    "decision": "used" if friendly_result and friendly_result.get("friendly_generation_used") else "skipped",
                    "skipped_reason": friendly_result.get("friendly_generation_skipped_reason") if friendly_result else None,
                },
            ],
        },
    }
