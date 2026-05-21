from typing import Any

from app.graphs.hr_state import HRState
from app.orchestrator import detect_intent_and_risk


def _route_from_detection(detection: dict[str, Any]) -> str:
    """
    Convert orchestrator-style detection flags into a graph route.

    Priority matters:
    - human handoff wins over RAG and profile
    - clarification wins before RAG/profile
    - RAG handles document/policy questions
    - profile is the default candidate-data route
    """
    if detection.get("requires_human"):
        return "human_handoff"

    if detection.get("requires_clarification"):
        return "clarification"

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
    detection = detect_intent_and_risk(message)
    route = _route_from_detection(detection)

    return {
        "intent": detection.get("intent") or "candidate_answer",
        "risk_level": detection.get("risk_level") or "low",
        "requires_human": bool(detection.get("requires_human", False)),
        "requires_rag": bool(detection.get("requires_rag", False)),
        "requires_clarification": bool(detection.get("requires_clarification", False)),
        "reason": detection.get("reason"),
        "route": route,
        "route_detection": detection,
    }
