import json
import os
import re
from pathlib import Path
from typing import Any

from app.graphs.hr_state import HRState
from app.indexer import call_llm


POLICY_PATH = Path(__file__).resolve().parents[1] / "policies" / "conversation_policy.md"

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


def _clean_route(value: Any) -> str:
    route = str(value or "rag").strip().lower()
    return route if route in ALLOWED_ROUTES else "rag"


def _normalize_route(payload: dict[str, Any]) -> dict[str, Any]:
    data = {**DEFAULT_ROUTE, **(payload or {})}

    datasource = str(data.get("datasource") or "").strip().lower()
    recommended_route = data.get("recommended_route")
    route = _clean_route(recommended_route or DATASOURCE_TO_ROUTE.get(datasource, "rag"))

    if datasource in WEB_DATASOURCES:
        route = "web_review"

    risk_level = str(data.get("risk_level") or "low").strip().lower()
    if risk_level not in {"low", "medium", "high"}:
        risk_level = "low"

    try:
        confidence = float(data.get("confidence", 0.0))
    except Exception:
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))

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
    """
    Plaban-style question router.

    This node does not try to maintain a hand-written intent taxonomy. It only
    decides the next datasource/route for the graph: vectorstore, websearch,
    direct greeting, profile, fallback or review paths.
    """
    if not _env_bool("MESSAGE_CLASSIFIER_ENABLED", True):
        route = {**DEFAULT_ROUTE, "reason": "router_disabled"}
        return {
            "classifier": route,
            "classifier_intent": "route_question",
            "classifier_confidence": 0.0,
            "events": [{"type": "question_router_skipped", "reason": "disabled"}],
        }

    policy = _load_policy()
    message = state.get("message") or ""
    current_stage = state.get("current_stage") or "START"
    profile_snapshot = state.get("profile_snapshot") or {}
    conversation_memory = state.get("conversation_memory") or {}

    prompt = f"""
You are a routing node for a Mexican trucking recruiting assistant.
Do not answer the candidate. Return JSON only.

Your job is only to choose the next graph route, similar to a RAG router:
- vectorstore: use internal documents/RAG
- websearch: use web search when internal context is likely insufficient or the term is external/unknown
- direct: use a direct non-RAG node for greetings or first-contact intent discovery
- profile: use profile flow only when the candidate clearly answers the pending profile field or asks to continue the process
- clarification: ask a clarification when the message cannot be safely interpreted
- human_handoff: human review is needed
- fallback: unsupported/no actionable message
- policy_boundary: controlled safety boundary

If datasource is websearch, set recommended_route to web_review.
Do not choose clarification before websearch for unknown terms; web review can decide later if clarification is needed.
Avoid rigid keyword matching. Use the conversation memory and current stage.
Do not force the profile flow when the candidate is asking a side question.

=== POLICY CONTEXT ===
{policy}

=== CURRENT STATE ===
current_stage: {current_stage}
profile_snapshot: {json.dumps(profile_snapshot, ensure_ascii=False, default=str)}
conversation_memory: {json.dumps(conversation_memory, ensure_ascii=False, default=str)}

=== CANDIDATE MESSAGE ===
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
        route = _normalize_route(parsed)
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
            }
        ],
    }
