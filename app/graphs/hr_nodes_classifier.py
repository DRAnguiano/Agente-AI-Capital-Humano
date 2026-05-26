import json
import os
import re
from pathlib import Path
from typing import Any

from app.graphs.hr_state import HRState
from app.indexer import call_llm


POLICY_PATH = Path(__file__).resolve().parents[1] / "policies" / "conversation_policy.md"
MIN_REWRITE_CONFIDENCE = 0.75

DEFAULT_ROUTE = {
    "datasource": "vectorstore",
    "recommended_route": "rag",
    "requires_rag": True,
    "requires_web_lookup": False,
    "requires_human": False,
    "requires_clarification": False,
    "risk_level": "low",
    "reason": "default_vectorstore_route",
    "confidence": 0.0,
}

ALLOWED_ROUTES = {
    "greeting",
    "profile",
    "rag",
    "web_review",
    "clarification",
    "human_handoff",
    "fallback",
    "policy_boundary",
}

DATASOURCE_TO_ROUTE = {
    "vectorstore": "rag",
    "websearch": "web_review",
    "web_search": "web_review",
    "direct": "greeting",
    "profile": "profile",
    "fallback": "fallback",
}

WEB_DATASOURCES = {"websearch", "web_search"}
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
    "toxicol",
    "doping",
    "dooping",
    "horario",
    "turno",
)


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _load_policy() -> str:
    try:
        return POLICY_PATH.read_text(encoding="utf-8")
    except Exception:
        return ""


def _json_from_text(text: str) -> dict[str, Any]:
    raw = (text or "").strip()
    if not raw:
        return {}

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
    if not match:
        return {}

    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return {}


def _clean_text(value: Any, max_len: int = 600) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text[:max_len]


def _clean_float(value: Any, default: float = 0.0) -> float:
    try:
        score = float(value)
    except Exception:
        score = default
    return max(0.0, min(1.0, score))


def _clean_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "si", "sí", "y", "on"}
    return bool(value)


def _clean_route(value: Any) -> str:
    route = str(value or "rag").strip().lower()
    return route if route in ALLOWED_ROUTES else "rag"


def _message_has_explicit_question(message: str) -> bool:
    text = (message or "").strip().lower()
    if "?" in text or "¿" in text:
        return True
    question_starters = (
        "cuanto",
        "cuánto",
        "cuales",
        "cuáles",
        "donde",
        "dónde",
        "que ",
        "qué ",
        "como ",
        "cómo ",
        "sabe ",
        "me podria decir",
        "me podría decir",
        "quisiera saber",
        "quiero saber",
    )
    return any(term in text for term in question_starters)


def _conversation_tail(state: HRState, max_items: int = 8) -> list[dict[str, Any]]:
    memory = state.get("conversation_memory") or {}
    turns = memory.get("turns") or memory.get("messages") or state.get("history_messages") or []
    if not isinstance(turns, list):
        return []
    return turns[-max_items:]


def _conversation_tail_text(state: HRState, max_chars: int = 1800) -> str:
    tail = _conversation_tail(state)
    parts: list[str] = []
    for item in tail:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or item.get("sender") or item.get("type") or "").strip()
        text = str(item.get("content") or item.get("message") or item.get("text") or "").strip()
        if text:
            parts.append(f"{role}: {text}" if role else text)
    return "\n".join(parts)[-max_chars:]


def _default_rewrite(message: str, reason: str = "no_rewrite_needed") -> dict[str, Any]:
    return {
        "original": message,
        "rewritten": message,
        "corrections": [],
        "intent_preserved": True,
        "confidence": 0.0,
        "should_use_rewrite": False,
        "should_retry_routing": False,
        "reason": reason,
    }


def _rewrite_prompt(state: HRState) -> str:
    message = state.get("message") or ""
    current_stage = state.get("current_stage") or "START"
    profile = state.get("profile_snapshot") or {}
    lead = state.get("lead_ingestion") or {}
    substance = state.get("substance_disclosure_analysis") or {}
    unknown_term_review = state.get("unknown_term_review") or {}
    history = _conversation_tail(state)

    return f"""
You are a contextual rewrite node for a Mexican trucking recruiting graph.
Do not answer the candidate. Return JSON only.

Task:
- Rewrite the candidate's current message into clear Spanish if spelling, slang, or missing context makes it ambiguous.
- Use conversation memory to infer the intended meaning.
- Keep the meaning and intent; do not add facts.
- The context is recruitment for operador/trailero de tractocamión / quinta rueda.
- Candidate spelling may be informal or incorrect: e.g. "save" can mean "sabe" if the conversation context supports it.
- Do not use a fixed dictionary as truth. Use context and confidence.
- If the message is already clear, return the same text and should_use_rewrite=false.
- If the current message is a short follow-up like "usted no sabe?", expand it with the immediately previous topic from the conversation. Example: if the previous topic was pay/trip compensation, rewrite it as "¿Usted no sabe cómo pagan el viaje?".
- If the current message is a follow-up to the previous candidate question, preserve that link.
- If the candidate asks about pay, routes, requirements, documents, toxicology process, bases, schedule, or travel, rewrite as a clear question suitable for RAG/router.
- Never answer whether a test would be positive/negative or provide evasion guidance; only rewrite the intent.

CURRENT_STAGE: {current_stage}
PROFILE_SNAPSHOT:
{json.dumps(profile, ensure_ascii=False, default=str)}

LEAD_INGESTION:
{json.dumps(lead, ensure_ascii=False, default=str)}

SUBSTANCE_ANALYSIS:
{json.dumps(substance, ensure_ascii=False, default=str)}

PRE_REWRITE_UNKNOWN_TERM_REVIEW:
{json.dumps(unknown_term_review, ensure_ascii=False, default=str)}

Critical rules for unknown terms:
- Use PRE_REWRITE_UNKNOWN_TERM_REVIEW before rewriting unclear words.
- If unknown_term_review says a term is ambiguous, low-confidence, or needs clarification, preserve the original term.
- Do NOT convert unclear words into substances, alcohol, crimes, diagnoses, addictions or serious misconduct unless the candidate explicitly wrote that meaning.
- If web evidence is weak or ambiguous, lower confidence and keep ambiguity.
- If a single unclear word changes the meaning of the whole message, keep the word and let the clarification node ask the candidate.

CONVERSATION_TAIL:
{json.dumps(history, ensure_ascii=False, default=str)}

CURRENT_MESSAGE:
{message}

Return JSON:
{{
  "original": "current message",
  "rewritten": "clear Spanish rewrite",
  "corrections": [
    {{"from": "token", "to": "correction", "reason": "brief reason"}}
  ],
  "intent_preserved": true,
  "confidence": 0.0,
  "should_use_rewrite": false,
  "should_retry_routing": false,
  "reason": "short internal reason"
}}
""".strip()


def _rewrite_is_underexpanded_followup(message: str, rewritten: str) -> bool:
    original = (message or "").strip().lower()
    clean = (rewritten or "").strip().lower()
    if not clean:
        return False
    compact_followups = {
        "¿usted no sabe?",
        "usted no sabe?",
        "usted no sabe",
        "¿no sabe?",
        "no sabe?",
        "no sabe",
    }
    return clean in compact_followups or ("save" in original and "sabe" in clean and len(clean.split()) <= 4)


def _infer_recent_topic_question(state: HRState) -> str | None:
    history = _conversation_tail_text(state).lower()
    if any(term in history for term in ("pagan", "pago", "sueldo", "salario", "kilometro", "kilómetro", "viaje")):
        return "¿Usted no sabe cómo pagan el viaje?"
    if any(term in history for term in ("ruta", "rutas", "base", "bases")):
        return "¿Usted no sabe cuáles son las rutas o bases de trabajo?"
    if any(term in history for term in ("licencia", "apto", "documento", "documentos", "requisito")):
        return "¿Usted no sabe cuáles son los requisitos para la vacante?"
    return None


def _normalize_rewrite(payload: dict[str, Any], message: str, state: HRState | None = None) -> dict[str, Any]:
    data = payload.get("contextual_rewrite") if isinstance(payload.get("contextual_rewrite"), dict) else payload
    rewritten = _clean_text(data.get("rewritten"), 600) or message
    confidence = _clean_float(data.get("confidence"), 0.0)
    intent_preserved = _clean_bool(data.get("intent_preserved", True))
    should_use = _clean_bool(data.get("should_use_rewrite", False))

    corrections = data.get("corrections") if isinstance(data.get("corrections"), list) else []
    clean_corrections: list[dict[str, str]] = []
    for item in corrections[:8]:
        if not isinstance(item, dict):
            continue
        clean_corrections.append(
            {
                "from": _clean_text(item.get("from"), 80) or "",
                "to": _clean_text(item.get("to"), 80) or "",
                "reason": _clean_text(item.get("reason"), 180) or "",
            }
        )

    if state is not None and _rewrite_is_underexpanded_followup(message, rewritten):
        inferred = _infer_recent_topic_question(state)
        if inferred:
            rewritten = inferred
            confidence = max(confidence, 0.85)
            should_use = True
            clean_corrections.append(
                {
                    "from": message,
                    "to": inferred,
                    "reason": "Se expandió la pregunta corta usando el tema reciente de la conversación.",
                }
            )

    blocked_sensitive_rewrite, blocked_term = _unknown_term_review_blocks_sensitive_rewrite(state, message, rewritten)
    if blocked_sensitive_rewrite:
        rewritten = message
        confidence = min(confidence, 0.49)
        should_use = False
        intent_preserved = True
        clean_corrections.append(
            {
                "from": blocked_term or "unknown_term",
                "to": "preserve_original",
                "reason": "Término ambiguo revisado antes del rewrite; no se permite inferir sustancias/hechos sensibles sin evidencia clara.",
            }
        )

    if rewritten.strip() != (message or "").strip() and confidence >= MIN_REWRITE_CONFIDENCE and intent_preserved:
        should_use = True

    return {
        "original": _clean_text(data.get("original"), 600) or message,
        "rewritten": _protect_ambiguous_slang_rewrite(message, rewritten),
        "corrections": clean_corrections,
        "intent_preserved": intent_preserved,
        "confidence": confidence,
        "should_use_rewrite": bool(should_use and confidence >= MIN_REWRITE_CONFIDENCE and intent_preserved),
        "should_retry_routing": bool(_clean_bool(data.get("should_retry_routing", should_use)) and confidence >= MIN_REWRITE_CONFIDENCE),
        "reason": _clean_text(data.get("reason"), 300) or "contextual_rewrite_checked",
    }




def _unknown_term_review_blocks_sensitive_rewrite(state: HRState | None, message: str, rewritten: str) -> tuple[bool, str | None]:
    """
    Hard safety gate:
    If pre-rewrite web review found an unclear term and evidence is weak/ambiguous,
    contextual rewrite cannot convert that term into substances/alcohol/crimes/etc.
    """
    if state is None:
        return False, None

    review = state.get("unknown_term_review") or {}
    if not review.get("has_unclear_terms"):
        return False, None

    sensitive_terms = (
        "marihuana",
        "mariguana",
        "cannabis",
        "droga",
        "drogas",
        "sustancia",
        "sustancias",
        "alcohol",
        "cocaína",
        "cocaina",
        "cristal",
        "perico",
        "adicto",
        "adicción",
        "adiccion",
        "delito",
        "robo",
    )

    rewritten_l = (rewritten or "").lower()
    if not any(term in rewritten_l for term in sensitive_terms):
        return False, None

    message_l = (message or "").lower()
    # If candidate explicitly wrote the sensitive word, do not block it.
    if any(term in message_l for term in sensitive_terms):
        return False, None

    terms = review.get("terms") or []
    if not terms:
        terms = (review.get("extraction") or {}).get("terms") or []

    reviewed_terms = []
    for item in terms:
        if isinstance(item, dict):
            term = str(item.get("term") or "").strip()
            if term:
                reviewed_terms.append(term)

    for item in review.get("terms", []) or []:
        if isinstance(item, dict):
            try:
                confidence = float(item.get("confidence") or 0.0)
            except Exception:
                confidence = 0.0

            if item.get("needs_clarification") or item.get("do_not_infer_sensitive_fact") or confidence < 0.70:
                return True, str(item.get("term") or None)

    # If there are unclear terms but synthesis did not give per-term confidence,
    # still block sensitive inference. This is intentional.
    if reviewed_terms or review.get("has_unclear_terms"):
        return True, reviewed_terms[0] if reviewed_terms else None

    return False, None


def _protect_ambiguous_slang_rewrite(original: str, rewritten: str) -> str:
    """
    Prevent contextual rewrite from turning ambiguous trucking slang into an
    explicit substance confession.

    Example:
    BAD: "cachimbr" -> "marihuana"
    GOOD: keep "cachimbear" and let substance_disclosure_analysis/RAG answer both possibilities.
    """
    original_l = (original or "").lower()
    rewritten_l = (rewritten or "").lower()

    has_cachimba = any(
        term in original_l
        for term in ("cachimba", "cachimbear", "cachimbr", "cachimb")
    )

    if not has_cachimba:
        return rewritten

    explicit_substance_terms = (
        "marihuana",
        "mariguana",
        "droga",
        "drogas",
        "cocaína",
        "cocaina",
        "cristal",
        "perico",
        "metanfetamina",
        "sustancias",
        "alcohol",
    )

    if not any(term in rewritten_l for term in explicit_substance_terms):
        return rewritten

    # Preserve the candidate's actual ambiguity instead of creating a confession.
    return "¿Sabe si puedo continuar el proceso si antes me gustaba cachimbear, pero ya cambié?"


def contextual_rewrite_node(state: HRState) -> dict[str, Any]:
    message = state.get("message") or ""
    if not message.strip():
        rewrite = _default_rewrite(message, "empty_message")
        return {"contextual_rewrite": rewrite, "events": [{"type": "contextual_rewrite_skipped", "reason": "empty_message"}]}

    try:
        raw = call_llm(_rewrite_prompt(state))
        parsed = _json_from_text(raw)
        rewrite = _normalize_rewrite(parsed, message, state)
    except Exception as exc:
        rewrite = _default_rewrite(message, f"rewrite_exception:{type(exc).__name__}")

    update: dict[str, Any] = {
        "contextual_rewrite": rewrite,
        "events": [
            {
                "type": "contextual_rewrite_checked",
                "should_use_rewrite": rewrite.get("should_use_rewrite"),
                "confidence": rewrite.get("confidence"),
                "rewritten": rewrite.get("rewritten"),
                "reason": rewrite.get("reason"),
            }
        ],
    }

    if rewrite.get("should_use_rewrite"):
        update["question"] = rewrite.get("rewritten") or message

    return update


def _lead_requested_callback(state: HRState) -> bool:
    lead = state.get("lead_ingestion") or {}
    extracted = lead.get("extracted") or {}
    return bool(extracted.get("callback_requested", False))


def _lead_has_profile_facts(state: HRState) -> bool:
    lead = state.get("lead_ingestion") or {}
    if not lead.get("updated"):
        return False
    updated_fields = set(lead.get("updated_fields") or [])
    profile_fields = {
        "nombre_completo",
        "edad",
        "telefono",
        "ciudad",
        "ciudad_raw",
        "licencia_federal",
        "tipo_licencia",
        "experiencia_quinta_rueda",
        "apto_medico",
        "disponibilidad_viajar",
    }
    return bool(updated_fields & profile_fields)


def _lead_has_expiring_document_facts(state: HRState) -> bool:
    lead = state.get("lead_ingestion") or {}
    extracted = lead.get("extracted") or {}
    if not lead.get("updated"):
        return False
    return bool(
        extracted.get("license_expiry_text")
        or extracted.get("license_needs_review")
        or extracted.get("medical_expiry_text")
    )


def _substance_analysis(state: HRState | None) -> dict[str, Any]:
    if state is None:
        return {}
    return state.get("substance_disclosure_analysis") or {}


def _has_restrictive_substance_signal(state: HRState | None) -> bool:
    analysis = _substance_analysis(state)
    return bool(
        analysis.get("detected")
        and (
            analysis.get("status") == "ACTIVE_OR_INTENDED_USE"
            or analysis.get("operational_risk") == "high"
            or analysis.get("requires_review") is True
        )
    )


def _has_analytics_only_substance_signal(state: HRState | None) -> bool:
    analysis = _substance_analysis(state)
    return bool(
        analysis.get("detected")
        and analysis.get("analytics_flag") is True
        and not _has_restrictive_substance_signal(state)
    )


def _effective_message_for_routing(state: HRState | None, fallback_message: str) -> str:
    if state is None:
        return fallback_message
    rewrite = state.get("contextual_rewrite") or {}
    if rewrite.get("should_use_rewrite") and rewrite.get("rewritten"):
        return str(rewrite.get("rewritten"))
    return fallback_message


def _is_side_question(message: str) -> bool:
    text = (message or "").strip().lower()
    return _message_has_explicit_question(text) and any(term in text for term in SIDE_QUESTION_TERMS)


def _normalize_route(payload: dict[str, Any], state: HRState | None = None) -> dict[str, Any]:
    data = {**DEFAULT_ROUTE, **(payload or {})}

    datasource = str(data.get("datasource") or "").strip().lower()
    recommended_route = data.get("recommended_route")
    route = _clean_route(recommended_route or DATASOURCE_TO_ROUTE.get(datasource, "rag"))

    if datasource in WEB_DATASOURCES:
        route = "web_review"

    if _has_restrictive_substance_signal(state):
        route = "policy_boundary"
        datasource = "profile"
        data["reason"] = "substance_operational_safety_boundary"
        data["risk_level"] = "high"
        data["requires_human"] = True
        data["requires_clarification"] = False
    elif _has_analytics_only_substance_signal(state):
        route = "profile"
        datasource = "profile"
        data["reason"] = "substance_analytics_signal_captured"
        data["risk_level"] = "medium"
        data["requires_human"] = False
        data["requires_clarification"] = False
        data["requires_rag"] = False
        data["requires_web_lookup"] = False
    elif state is not None and _lead_requested_callback(state):
        route = "profile"
        datasource = "profile"
        data["reason"] = "callback_request_captured"
    elif (
        state is not None
        and _lead_has_expiring_document_facts(state)
        and not _message_has_explicit_question(_effective_message_for_routing(state, state.get("message") or ""))
    ):
        route = "profile"
        datasource = "profile"
        data["reason"] = "profile_facts_expiring_documents_captured"
        data["risk_level"] = "medium"
        data["requires_human"] = True
    elif state is not None:
        message = _effective_message_for_routing(state, state.get("message") or "")
        if route == "profile" and (_is_side_question(message) or (_message_has_explicit_question(message) and not _lead_has_profile_facts(state))):
            route = "rag"
            datasource = "vectorstore"
            data["reason"] = "profile_route_overridden_by_side_question"
        elif route == "profile" and _lead_has_profile_facts(state) and _message_has_explicit_question(message):
            route = "rag"
            datasource = "vectorstore"
            data["reason"] = "profile_facts_with_side_question"

    if state is not None:
        rewrite = state.get("contextual_rewrite") or {}
        message = _effective_message_for_routing(state, state.get("message") or "")

        if (
            rewrite.get("should_use_rewrite")
            and rewrite.get("confidence", 0) >= MIN_REWRITE_CONFIDENCE
            and _is_side_question(message)
            and route in {"clarification", "web_review", "fallback", "profile"}
        ):
            route = "rag"
            datasource = "vectorstore"
            data["reason"] = "contextual_rewrite_resolved_internal_question"
            data["requires_clarification"] = False
            data["requires_web_lookup"] = False
            data["requires_rag"] = True

        elif route == "clarification" and rewrite.get("should_use_rewrite") and rewrite.get("confidence", 0) >= MIN_REWRITE_CONFIDENCE:
            route = "rag"
            datasource = "vectorstore"
            data["reason"] = "contextual_rewrite_resolved_ambiguity"
            data["requires_clarification"] = False
            data["requires_rag"] = True

        elif route == "profile" and rewrite.get("should_use_rewrite") and _message_has_explicit_question(message):
            route = "rag"
            datasource = "vectorstore"
            data["reason"] = "contextual_rewrite_side_question"
            data["requires_clarification"] = False
            data["requires_rag"] = True

    risk_level = str(data.get("risk_level") or "low").strip().lower()
    if risk_level not in {"low", "medium", "high"}:
        risk_level = "low"

    confidence = _clean_float(data.get("confidence", 0.0), 0.0)

    requires_human = bool(data.get("requires_human", False)) or route == "human_handoff"
    requires_clarification = bool(data.get("requires_clarification", False)) and route != "web_review"
    requires_web_lookup = bool(data.get("requires_web_lookup", False)) or route == "web_review"
    requires_rag = bool(data.get("requires_rag", False)) or route == "rag"

    if route in {"greeting", "profile", "human_handoff", "clarification", "fallback", "policy_boundary"}:
        requires_rag = False
    if route == "web_review":
        requires_rag = False
        requires_web_lookup = True
        requires_clarification = False

    return {
        "datasource": datasource or "vectorstore",
        "classifier_intent": str(data.get("classifier_intent") or "route_question").strip().lower(),
        "risk_level": risk_level,
        "recommended_route": route,
        "requires_rag": requires_rag,
        "requires_web_lookup": requires_web_lookup,
        "requires_human": requires_human,
        "requires_clarification": requires_clarification,
        "should_continue_profile": bool(data.get("should_continue_profile", False)),
        "safe_reply_mode": str(data.get("safe_reply_mode") or "none").strip().lower(),
        "web_query": data.get("web_query") or None,
        "reason": str(data.get("reason") or "route_question").strip().lower(),
        "confidence": confidence,
    }


def classify_message_node(state: HRState) -> dict[str, Any]:
    if not _env_bool("MESSAGE_CLASSIFIER_ENABLED", True):
        route = {**DEFAULT_ROUTE, "reason": "router_disabled"}
        return {
            "classifier": route,
            "classifier_intent": "route_question",
            "classifier_confidence": 0.0,
            "events": [{"type": "question_router_skipped", "reason": "disabled"}],
        }

    policy = _load_policy()
    original_message = state.get("message") or ""
    contextual_rewrite = state.get("contextual_rewrite") or {}
    message = _effective_message_for_routing(state, original_message)
    current_stage = state.get("current_stage") or "START"
    profile_snapshot = state.get("profile_snapshot") or {}
    conversation_memory = state.get("conversation_memory") or {}
    lead_ingestion = state.get("lead_ingestion") or {}
    substance_disclosure_analysis = state.get("substance_disclosure_analysis") or {}

    prompt = f"""
You are a routing node for a Mexican trucking recruiting assistant.
Do not answer the candidate. Return JSON only.

Your job is only to choose the next graph route, similar to a RAG router:
- vectorstore: use internal documents/RAG
- websearch: use web search when internal context is likely insufficient or the term is external/unknown
- direct: use a direct non-RAG node for greetings or first-contact intent discovery
- profile: use profile flow only when the candidate clearly answers the pending profile field, asks to continue the process, or requests callback/contact from Capital Humano
- clarification: ask a clarification only when ambiguity remains after contextual rewrite
- human_handoff: human review is needed
- fallback: unsupported/no actionable message
- policy_boundary: controlled safety boundary

If datasource is websearch, set recommended_route to web_review.
Do not choose clarification before websearch for unknown terms; web review can decide later if clarification is needed.
Avoid rigid keyword matching. Use the conversation memory, contextual rewrite, and current stage.
If contextual_rewrite.should_use_rewrite=true, route based on the rewritten message.
Do not force the profile flow when the candidate is asking a side question.
If the current message contains both profile facts and an explicit question about pay, benefits, bases, requirements, schedule, routes or policy, choose vectorstore/RAG for the response. Lead ingestion already saved the facts.
If lead_ingestion shows callback_requested=true, choose profile/natural lead response, not RAG.
If lead_ingestion captured license or medical-expiry facts and the current message is not an explicit question, choose profile/natural lead response, not RAG. The facts were already saved and Capital Humano must review them.
If substance_disclosure_analysis has ACTIVE_OR_INTENDED_USE or operational_risk=high, choose policy_boundary.
If substance_disclosure_analysis is RECENT_PAST_USE or PAST_USE with medium risk, choose profile and continue the capture flow; it is an analytics signal and must not block the process by itself.

=== POLICY CONTEXT ===
{policy}

=== CURRENT STATE ===
current_stage: {current_stage}
profile_snapshot: {json.dumps(profile_snapshot, ensure_ascii=False, default=str)}
conversation_memory: {json.dumps(conversation_memory, ensure_ascii=False, default=str)}
lead_ingestion: {json.dumps(lead_ingestion, ensure_ascii=False, default=str)}
substance_disclosure_analysis: {json.dumps(substance_disclosure_analysis, ensure_ascii=False, default=str)}
contextual_rewrite: {json.dumps(contextual_rewrite, ensure_ascii=False, default=str)}

=== ORIGINAL CANDIDATE MESSAGE ===
{original_message}

=== ROUTING MESSAGE ===
{message}

Return JSON:
{{
  "datasource": "vectorstore | websearch | direct | profile | clarification | human_handoff | fallback | policy_boundary",
  "recommended_route": "rag | web_review | greeting | profile | clarification | human_handoff | fallback | policy_boundary",
  "requires_rag": true,
  "requires_web_lookup": false,
  "requires_human": false,
  "requires_clarification": false,
  "risk_level": "low | medium | high",
  "reason": "short_reason",
  "confidence": 0.0,
  "web_query": null
}}
""".strip()

    try:
        raw = call_llm(prompt)
        parsed = _json_from_text(raw)
        route = _normalize_route(parsed, state)
    except Exception as exc:
        route = {
            **DEFAULT_ROUTE,
            "reason": "router_exception",
            "error": f"{type(exc).__name__}: {exc}",
        }

    return {
        "classifier": route,
        "classifier_intent": route.get("classifier_intent") or "route_question",
        "classifier_confidence": route["confidence"],
        "safe_reply_mode": route.get("safe_reply_mode") or "none",
        "requires_web_lookup": route["requires_web_lookup"],
        "web_query": route.get("web_query"),
        "events": [
            {
                "type": "question_routed",
                "datasource": route.get("datasource"),
                "recommended_route": route["recommended_route"],
                "risk_level": route["risk_level"],
                "reason": route["reason"],
                "confidence": route["confidence"],
                "original_message": original_message,
                "routing_message": message,
                "contextual_rewrite_used": bool(contextual_rewrite.get("should_use_rewrite")),
                "substance_status": substance_disclosure_analysis.get("status"),
                "substance_operational_risk": substance_disclosure_analysis.get("operational_risk"),
            }
        ],
    }
