from typing import Any

from app.graphs.hr_state import HRState
from app.orchestrator import PROFILE_STAGES, detect_intent_and_risk


def _is_explicit_question(message: str) -> bool:
    """Keep profile-stage answers from being misrouted as RAG."""
    raw = message or ""
    return "?" in raw or "¿" in raw


def _route_from_detection(
    detection: dict[str, Any],
    *,
    current_stage: str | None = None,
    message: str = "",
) -> str:
    """
    Convert orchestrator-style detection flags into a graph route.

    Priority matters:
    - human handoff wins over RAG and profile
    - clarification wins before RAG/profile
    - active profile-stage answers win over keyword-based RAG when not questions
    - RAG handles explicit document/policy questions
    - profile is the default candidate-data route
    """
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
    route = _route_from_detection(
        detection,
        current_stage=current_stage,
        message=message,
    )

    requires_rag = bool(detection.get("requires_rag", False))
    intent = detection.get("intent") or "candidate_answer"

    if route == "profile":
        requires_rag = False
        intent = "candidate_answer"

    return {
        "intent": intent,
        "risk_level": detection.get("risk_level") or "low",
        "requires_human": bool(detection.get("requires_human", False)),
        "requires_rag": requires_rag,
        "requires_clarification": bool(detection.get("requires_clarification", False)),
        "reason": detection.get("reason"),
        "route": route,
        "route_detection": detection,
    }
