from typing import Any

from app.graphs.hr_state import HRState
from app.orchestrator import (
    PROFILE_STAGES,
    Intent,
    Stage,
    _is_meta_complaint_or_confusion,
    _is_safe_clarification_response,
    detect_intent_and_risk,
)


def _is_explicit_question(message: str) -> bool:
    """Keep profile-stage answers from being misrouted as RAG."""
    raw = message or ""
    return "?" in raw or "¿" in raw


def _apply_clarification_followup_detection(
    detection: dict[str, Any],
    *,
    current_stage: str | None,
    message: str,
) -> dict[str, Any]:
    """
    Resolve the second half of ambiguous slang clarification.

    Mirrors the legacy behavior:
    - safe clarification goes back to profile flow
    - risky clarification goes to human handoff
    - meta/confused response goes back to profile flow with ASK_CITY recovery
    """
    if current_stage != Stage.CLARIFY_AMBIGUOUS_SLANG.value:
        return detection

    if _is_safe_clarification_response(message):
        return {
            "intent": Intent.SLANG_SAFE.value,
            "risk_level": "low",
            "requires_human": False,
            "requires_rag": False,
            "requires_clarification": False,
            "reason": "jerga_aclarada_segura",
            "route": "profile",
            "clarification_followup": "safe",
        }

    if _is_meta_complaint_or_confusion(message):
        return {
            "intent": Intent.CANDIDATE_ANSWER.value,
            "risk_level": "low",
            "requires_human": False,
            "requires_rag": False,
            "requires_clarification": False,
            "reason": "aclaracion_no_riesgosa_o_confusion",
            "route": "profile",
            "clarification_followup": "confused_or_meta",
            "current_stage_override": Stage.ASK_CITY.value,
        }

    return {
        "intent": Intent.SLANG_RISKY.value,
        "risk_level": "high",
        "requires_human": True,
        "requires_rag": False,
        "requires_clarification": False,
        "reason": "jerga_aclarada_con_riesgo",
        "route": "human_handoff",
        "clarification_followup": "risky",
    }


def _route_from_detection(
    detection: dict[str, Any],
    *,
    current_stage: str | None = None,
    message: str = "",
) -> str:
    """
    Convert orchestrator-style detection flags into a graph route.

    Priority matters:
    - explicit override from clarification follow-up wins first
    - human handoff wins over RAG and profile
    - clarification wins before RAG/profile
    - active profile-stage answers win over keyword-based RAG when not questions
    - RAG handles explicit document/policy questions
    - profile is the default candidate-data route
    """
    if detection.get("route"):
        return str(detection["route"])

    if detection.get("requires_human"):
        return "human_handoff"

    if detection.get("requires_clarification"):
        return "clarification"

    # When the conversation is already asking for profile data, answers such as
    # "Sí tengo licencia federal tipo B" or "tengo 5 años" may contain words
    # that also appear in RAG keywords. In that case, profile flow must win.
    if (
        current_stage in PROFILE_STAGES
        and not _is_explicit_question(message)
        and detection.get("risk_level", "low") == "low"
    ):
        return "profile"

    if detection.get("requires_rag"):
        return "rag"

    return "profile"


def route_message_node(state: HRState) -> dict[str, Any]:
    """
    Detect intent/risk and select the next high-level graph route.

    This is the first extraction from app/orchestrator.py's decision logic.
    It does not write to DB; it only updates state.
    """
    message = state.get("message") or ""
    current_stage = state.get("current_stage") or "START"
    detection = detect_intent_and_risk(message)
    detection = _apply_clarification_followup_detection(
        detection,
        current_stage=current_stage,
        message=message,
    )

    effective_stage = detection.get("current_stage_override") or current_stage
    route = _route_from_detection(
        detection,
        current_stage=effective_stage,
        message=message,
    )

    requires_rag = bool(detection.get("requires_rag", False))
    intent = detection.get("intent") or "candidate_answer"
    risk_level = detection.get("risk_level") or "low"
    requires_human = bool(detection.get("requires_human", False))

    if route == "profile":
        requires_rag = False
        intent = intent or "candidate_answer"

    return {
        "intent": intent,
        "risk_level": risk_level,
        "requires_human": requires_human,
        "requires_rag": requires_rag,
        "requires_clarification": bool(detection.get("requires_clarification", False)),
        "reason": detection.get("reason"),
        "route": route,
        "route_detection": detection,
        "current_stage": effective_stage,
    }
