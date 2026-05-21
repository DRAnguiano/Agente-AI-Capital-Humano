import json
import os
import re
import unicodedata
from pathlib import Path
from typing import Any

from app.graphs.hr_state import HRState
from app.indexer import call_llm


POLICY_PATH = Path(__file__).resolve().parents[1] / "policies" / "conversation_policy.md"

DEFAULT_CLASSIFICATION = {
    "classifier_intent": "fallback",
    "risk_level": "low",
    "recommended_route": "fallback",
    "requires_rag": False,
    "requires_web_lookup": False,
    "requires_human": False,
    "requires_clarification": False,
    "should_continue_profile": False,
    "safe_reply_mode": "fallback",
    "web_query": None,
    "reason": "classifier_default_fallback",
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

GREETING_INTENTS = {"greeting", "initial_greeting"}


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


def _norm_text(message: str) -> str:
    text = (message or "").strip().lower()
    text = "".join(
        ch
        for ch in unicodedata.normalize("NFD", text)
        if unicodedata.category(ch) != "Mn"
    )
    return re.sub(r"\s+", " ", text).strip()


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


def _clean_route(value: Any) -> str:
    route = str(value or "fallback").strip().lower()
    return route if route in ALLOWED_ROUTES else "fallback"


def _fallback_repair(message: str, conversation_memory: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """
    Conservative repair for obvious classifier misses.

    This is not a slang dictionary. It only catches broad, stable categories
    that should never become a generic fallback: greeting, pay question and
    explicit substance/safety admission. The LLM classifier remains the main
    decision maker.
    """
    text = _norm_text(message)
    memory = conversation_memory or {}
    previous_user = _norm_text(str(memory.get("previous_user_message") or ""))

    if text in {"hola", "buenas", "buen dia", "buenos dias", "buenas tardes", "buenas noches", "que tal"}:
        return {
            "classifier_intent": "greeting",
            "risk_level": "low",
            "recommended_route": "greeting",
            "requires_rag": False,
            "requires_web_lookup": False,
            "requires_human": False,
            "requires_clarification": False,
            "should_continue_profile": False,
            "safe_reply_mode": "greeting",
            "web_query": None,
            "reason": "fallback_repaired_greeting",
            "confidence": 0.95,
        }

    if any(term in text for term in {"cuanto pagan", "cuanto paga", "pago", "sueldo", "salario", "kilometro", "km"}):
        return {
            "classifier_intent": "pay_question",
            "risk_level": "low",
            "recommended_route": "rag",
            "requires_rag": True,
            "requires_web_lookup": False,
            "requires_human": False,
            "requires_clarification": False,
            "should_continue_profile": False,
            "safe_reply_mode": "answer_then_resume",
            "web_query": None,
            "reason": "fallback_repaired_pay_question",
            "confidence": 0.85,
        }

    explicit_substance = any(term in text for term in {"mota", "droga", "perico", "periquito", "cocaina", "cristal", "meto", "me meto"})
    previous_substance = any(term in previous_user for term in {"mota", "droga", "perico", "periquito", "cocaina", "cristal", "me meto"})
    followup_reference = bool(memory.get("current_may_reference_previous"))

    if explicit_substance or (followup_reference and previous_substance):
        return {
            "classifier_intent": "direct_safety_admission" if explicit_substance else "safety_sensitive_question",
            "risk_level": "high" if explicit_substance else "medium",
            "recommended_route": "human_handoff" if explicit_substance else "policy_boundary",
            "requires_rag": False,
            "requires_web_lookup": False,
            "requires_human": bool(explicit_substance),
            "requires_clarification": False,
            "should_continue_profile": False,
            "safe_reply_mode": "handoff_boundary" if explicit_substance else "policy_boundary",
            "web_query": None,
            "reason": "fallback_repaired_safety_sensitive_context",
            "confidence": 0.9,
        }

    return None


def _normalize_classification(payload: dict[str, Any]) -> dict[str, Any]:
    data = {**DEFAULT_CLASSIFICATION, **(payload or {})}

    classifier_intent = str(data.get("classifier_intent") or "fallback").strip().lower()
    route = _clean_route(data.get("recommended_route"))
    risk_level = str(data.get("risk_level") or "low").strip().lower()
    if risk_level not in {"low", "medium", "high"}:
        risk_level = "low"

    try:
        confidence = float(data.get("confidence", 0.0))
    except Exception:
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))

    if classifier_intent in GREETING_INTENTS:
        route = "greeting"

    requires_human = bool(data.get("requires_human", False)) or route == "human_handoff" or risk_level == "high"
    requires_clarification = bool(data.get("requires_clarification", False)) or route == "clarification"
    requires_web_lookup = bool(data.get("requires_web_lookup", False)) or route == "web_review"
    requires_rag = bool(data.get("requires_rag", False)) or route == "rag"

    if requires_human:
        route = "human_handoff"
        requires_rag = False
        requires_web_lookup = False
        requires_clarification = False

    if route in {"greeting", "policy_boundary"}:
        requires_rag = False
        requires_web_lookup = False
        requires_clarification = False

    return {
        "classifier_intent": classifier_intent,
        "risk_level": risk_level,
        "recommended_route": route,
        "requires_rag": requires_rag,
        "requires_web_lookup": requires_web_lookup,
        "requires_human": requires_human,
        "requires_clarification": requires_clarification,
        "should_continue_profile": bool(data.get("should_continue_profile", False)),
        "safe_reply_mode": str(data.get("safe_reply_mode") or "fallback").strip().lower(),
        "web_query": data.get("web_query") or None,
        "reason": str(data.get("reason") or "classifier_no_reason").strip().lower(),
        "confidence": confidence,
    }


def classify_message_node(state: HRState) -> dict[str, Any]:
    if not _env_bool("MESSAGE_CLASSIFIER_ENABLED", True):
        return {
            "classifier": {**DEFAULT_CLASSIFICATION, "reason": "classifier_disabled"},
            "classifier_intent": "fallback",
            "classifier_confidence": 0.0,
            "events": [{"type": "message_classifier_skipped", "reason": "disabled"}],
        }

    policy = _load_policy()
    message = state.get("message") or ""
    current_stage = state.get("current_stage") or "START"
    profile_snapshot = state.get("profile_snapshot") or {}
    history_messages = state.get("history_messages") or []
    recent_history = history_messages[-6:] if isinstance(history_messages, list) else []
    conversation_memory = state.get("conversation_memory") or {}

    prompt = f"""
You are a strict JSON classifier for a Mexican trucking recruiting assistant.
Return JSON only. Do not answer the candidate.

=== POLICY ===
{policy}

=== CURRENT STATE ===
current_stage: {current_stage}
profile_snapshot: {json.dumps(profile_snapshot, ensure_ascii=False, default=str)}
recent_history: {json.dumps(recent_history, ensure_ascii=False, default=str)}
conversation_memory: {json.dumps(conversation_memory, ensure_ascii=False, default=str)}

=== CANDIDATE MESSAGE ===
{message}

Classify this message according to the policy.
If conversation_memory.current_may_reference_previous is true, classify the current message together with conversation_memory.previous_user_message and conversation_memory.summary.
Return exactly the JSON contract.
""".strip()

    try:
        raw = call_llm(prompt)
        parsed = _json_from_text(raw)
        classification = _normalize_classification(parsed)
    except Exception as exc:
        classification = {
            **DEFAULT_CLASSIFICATION,
            "reason": "classifier_exception",
            "error": f"{type(exc).__name__}: {exc}",
        }

    repair = None
    if classification.get("recommended_route") == "fallback":
        repair = _fallback_repair(message, conversation_memory)
        if repair:
            classification = repair

    events = [
        {
            "type": "message_classified",
            "classifier_intent": classification["classifier_intent"],
            "recommended_route": classification["recommended_route"],
            "risk_level": classification["risk_level"],
            "reason": classification["reason"],
            "confidence": classification["confidence"],
        }
    ]
    if repair:
        events.append(
            {
                "type": "classifier_fallback_repaired",
                "classifier_intent": classification["classifier_intent"],
                "recommended_route": classification["recommended_route"],
                "reason": classification["reason"],
            }
        )

    return {
        "classifier": classification,
        "classifier_intent": classification["classifier_intent"],
        "classifier_confidence": classification["confidence"],
        "safe_reply_mode": classification["safe_reply_mode"],
        "requires_web_lookup": classification["requires_web_lookup"],
        "web_query": classification.get("web_query"),
        "events": events,
    }
