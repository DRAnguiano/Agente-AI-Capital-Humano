from typing import Any

from app.graphs.hr_state import HRState
from app.indexer import call_llm


ANALYTICS_SAFE_ACK = "Gracias por comentarlo. Por seguridad operativa, ese punto debe revisarlo directamente Capital Humano. La empresa maneja política de cero tolerancia y puede realizar pruebas toxicológicas; por este medio no puedo confirmar continuidad ni descarte del proceso."
RESTRICTIVE_REVIEW_ACK = (
    "Nuestra empresa tiene política de 0 tolerancia. "
    "Capital Humano debe revisar este punto antes de continuar."
)


def _clean_text(value: Any, max_len: int = 700) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return text[:max_len]


def _profile_plan(state: HRState) -> dict[str, Any]:
    return state.get("profile_followup_plan") or {}


def _analysis(state: HRState) -> dict[str, Any]:
    return state.get("substance_disclosure_analysis") or {}


def _should_guard_profile_reply(state: HRState) -> bool:
    plan = _profile_plan(state)
    analysis = _analysis(state)
    if not plan and not analysis:
        return False
    return bool(
        plan.get("has_substance_analytics_signal")
        or plan.get("has_restrictive_substance_signal")
        or analysis.get("analytics_flag")
        or analysis.get("requires_review")
    )


def _controlled_reply_from_plan(state: HRState) -> str:
    plan = _profile_plan(state)
    exact_question = _clean_text(plan.get("exact_question"), 220)

    if plan.get("has_restrictive_substance_signal"):
        base = _clean_text(plan.get("review_message"), 350) or RESTRICTIVE_REVIEW_ACK
        return base

    base = _clean_text(plan.get("review_message"), 350) or ANALYTICS_SAFE_ACK
    if plan.get("should_ask") and exact_question:
        return f"{base}\n\n{exact_question}".strip()
    return base


def _guard_prompt(state: HRState) -> str:
    plan = _profile_plan(state)
    analysis = _analysis(state)
    reply = state.get("reply") or state.get("text") or ""

    return f"""
You are a response quality guard for an HR recruiting graph.
Do not answer the candidate directly. Return JSON only.

Evaluate whether the assistant reply follows the graph plan.
The graph plan is the source of truth.

Rules:
- If the plan has an analytics-only sensitive signal, the reply may briefly acknowledge and continue with the exact graph question.
- The reply must not request extra sensitive details not requested by the graph.
- The reply must not answer operational test-outcome questions or give avoidance guidance.
- If should_ask=true, the reply must end with exact_question and no other question.
- If the plan has a restrictive signal, the reply must not continue profile capture.

GRAPH_PLAN:
{plan}

STRUCTURED_ANALYSIS:
{analysis}

ASSISTANT_REPLY:
{reply}

Return JSON:
{{
  "check": "PASS | FAIL",
  "reason": "short internal reason",
  "use_controlled_reply": false
}}
""".strip()


def _parse_guard_result(raw: str) -> dict[str, Any]:
    import json
    import re

    text = (raw or "").strip()
    try:
        data = json.loads(text)
    except Exception:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            return {"check": "FAIL", "reason": "guard_parse_failed", "use_controlled_reply": True}
        try:
            data = json.loads(match.group(0))
        except Exception:
            return {"check": "FAIL", "reason": "guard_parse_failed", "use_controlled_reply": True}

    check = str(data.get("check") or "FAIL").strip().upper()
    if check not in {"PASS", "FAIL"}:
        check = "FAIL"

    use_controlled_reply = True if check == "FAIL" else bool(data.get("use_controlled_reply", False))

    return {
        "check": check,
        "reason": _clean_text(data.get("reason"), 240) or "guard_checked",
        "use_controlled_reply": use_controlled_reply,
    }


def profile_response_guard_node(state: HRState) -> dict[str, Any]:
    if not _should_guard_profile_reply(state):
        return {
            "profile_response_guard": {"check": "SKIP", "reason": "no_sensitive_profile_guard_needed"},
            "events": [{"type": "profile_response_guard_skipped", "reason": "no_sensitive_profile_guard_needed"}],
        }

    try:
        guard = _parse_guard_result(call_llm(_guard_prompt(state)))
    except Exception as exc:
        guard = {"check": "FAIL", "reason": f"guard_exception:{type(exc).__name__}", "use_controlled_reply": True}

    reply = state.get("reply") or state.get("text") or ""
    if guard.get("use_controlled_reply"):
        reply = _controlled_reply_from_plan(state)
        guard["controlled_reply_used"] = True
    else:
        guard["controlled_reply_used"] = False

    return {
        "reply": reply,
        "text": reply,
        "profile_response_guard": guard,
        "events": [
            {
                "type": "profile_response_guard_checked",
                "check": guard.get("check"),
                "reason": guard.get("reason"),
                "controlled_reply_used": guard.get("controlled_reply_used"),
            }
        ],
    }
