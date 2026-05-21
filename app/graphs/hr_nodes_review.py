import json
import re
from typing import Any

from app.graphs.hr_state import HRState
from app.indexer import call_llm


DEFAULT_REVIEW = {
    "review_route": "fallback",
    "risk_level": "low",
    "requires_human": False,
    "requires_clarification": False,
    "safe_reply_mode": "fallback",
    "reply": "No quiero darte información incorrecta. Este punto debe revisarlo Capital Humano para darte una respuesta segura.",
    "reason": "review_default_fallback",
    "confidence": 0.0,
}

ALLOWED_REVIEW_ROUTES = {
    "policy_boundary",
    "clarification",
    "human_handoff",
    "fallback",
}


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


def _normalize_review(payload: dict[str, Any]) -> dict[str, Any]:
    data = {**DEFAULT_REVIEW, **(payload or {})}

    route = str(data.get("review_route") or "fallback").strip().lower()
    if route not in ALLOWED_REVIEW_ROUTES:
        route = "fallback"

    risk_level = str(data.get("risk_level") or "low").strip().lower()
    if risk_level not in {"low", "medium", "high"}:
        risk_level = "low"

    requires_human = bool(data.get("requires_human", False)) or risk_level == "high" or route == "human_handoff"
    requires_clarification = bool(data.get("requires_clarification", False)) or route == "clarification"

    if requires_human:
        route = "human_handoff"
        requires_clarification = False

    try:
        confidence = float(data.get("confidence", 0.0))
    except Exception:
        confidence = 0.0

    reply = str(data.get("reply") or DEFAULT_REVIEW["reply"]).strip()
    if not reply:
        reply = DEFAULT_REVIEW["reply"]

    return {
        "review_route": route,
        "risk_level": risk_level,
        "requires_human": requires_human,
        "requires_clarification": requires_clarification,
        "safe_reply_mode": str(data.get("safe_reply_mode") or "fallback").strip().lower(),
        "reply": reply,
        "reason": str(data.get("reason") or "review_no_reason").strip().lower(),
        "confidence": max(0.0, min(1.0, confidence)),
    }


def review_new_information_node(state: HRState) -> dict[str, Any]:
    """
    Review Tavily results before any candidate-facing response.

    This node converts external context into a safe route and a controlled reply.
    Tavily output is never sent directly to the candidate.
    """
    message = state.get("message") or ""
    current_stage = state.get("current_stage") or "START"
    classifier = state.get("classifier") or {}
    web_results = state.get("web_results") or []
    web_answer = state.get("web_answer")

    compact_results = []
    for item in web_results[:5]:
        compact_results.append(
            {
                "title": item.get("title"),
                "url": item.get("url"),
                "content": item.get("content"),
            }
        )

    prompt = f"""
You are a safety review node for a Mexican trucking recruiting assistant.
Do not answer with Markdown. Return JSON only.

Your task:
- Use the classifier result and web context only to decide a safe route.
- Never provide instructions, workarounds, or details about substances, impairment, or testing evasion.
- If the message suggests alcohol, substances, stimulants, medication affecting driving, or using anything to endure driving, route to human_handoff or policy_boundary.
- If the term is ambiguous but may be harmless, route to clarification.
- If web results are weak, route to fallback.

Return JSON:
{{
  "review_route": "policy_boundary | clarification | human_handoff | fallback",
  "risk_level": "low | medium | high",
  "requires_human": false,
  "requires_clarification": false,
  "safe_reply_mode": "policy_boundary | clarification | handoff_boundary | fallback",
  "reply": "candidate-facing Spanish reply, short and safe",
  "reason": "short snake_case reason",
  "confidence": 0.0
}}

=== CURRENT STAGE ===
{current_stage}

=== CANDIDATE MESSAGE ===
{message}

=== CLASSIFIER ===
{json.dumps(classifier, ensure_ascii=False, default=str)}

=== WEB ANSWER ===
{web_answer}

=== WEB RESULTS ===
{json.dumps(compact_results, ensure_ascii=False, default=str)}
""".strip()

    try:
        raw = call_llm(prompt)
        review = _normalize_review(_json_from_text(raw))
    except Exception as exc:
        review = {
            **DEFAULT_REVIEW,
            "reason": "review_exception",
            "error": f"{type(exc).__name__}: {exc}",
        }

    return {
        "new_information_review": review,
        "route": review["review_route"],
        "intent": classifier.get("classifier_intent") or "new_information_review",
        "risk_level": review["risk_level"],
        "requires_human": review["requires_human"],
        "requires_clarification": review["requires_clarification"],
        "requires_rag": False,
        "reason": review["reason"],
        "reply": review["reply"],
        "text": review["reply"],
        "policy_boundary_real_flow_used": review["review_route"] == "policy_boundary",
        "events": [
            {
                "type": "new_information_review_completed",
                "review_route": review["review_route"],
                "risk_level": review["risk_level"],
                "reason": review["reason"],
                "confidence": review["confidence"],
            }
        ],
    }
