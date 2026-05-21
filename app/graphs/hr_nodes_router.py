import re
import unicodedata
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


PROFILE_START_SIGNALS = {
    "soy",
    "vivo",
    "radico",
    "estoy",
    "tengo",
    "licencia",
    "federal",
    "tipo",
    "experiencia",
    "anos",
    "años",
    "quinta",
    "rueda",
    "apto",
    "medico",
    "médico",
    "disponibilidad",
    "viajar",
    "ruta",
    "foraneo",
    "foráneo",
    "torreon",
    "torreón",
    "gomez",
    "gómez",
    "lerdo",
    "matamoros",
}

LOW_VALUE_NOISE = {
    "asdf",
    "qwer",
    "test",
    "prueba",
    "hola?",
    "???",
    "...",
}


def _norm_text(message: str) -> str:
    text = (message or "").strip().lower()
    text = "".join(
        ch
        for ch in unicodedata.normalize("NFD", text)
        if unicodedata.category(ch) != "Mn"
    )
    return re.sub(r"\s+", " ", text).strip()


def _tokenize(message: str) -> set[str]:
    return set(re.findall(r"[a-záéíóúñ0-9]+", (message or "").lower()))


def _is_explicit_question(message: str) -> bool:
    """Keep profile-stage answers from being misrouted as RAG."""
    raw = message or ""
    return "?" in raw or "¿" in raw


def _looks_like_noise_or_unsupported_start(message: str) -> bool:
    """
    Conservative fallback gate for START.

    We only route to fallback when the message has no useful recruiting/profile
    signal and looks like noise or unsupported text. Useful low-context profile
    starts such as "Soy de Torreón" or "Tengo licencia" must keep going to
    profile.
    """
    normalized = _norm_text(message)
    if not normalized:
        return True

    if _is_explicit_question(message):
        return False

    tokens = _tokenize(message)
    normalized_signal_tokens = {
        _norm_text(token)
        for token in PROFILE_START_SIGNALS
    }

    if tokens & normalized_signal_tokens:
        return False

    if normalized in LOW_VALUE_NOISE:
        return True

    if any(noise in tokens for noise in LOW_VALUE_NOISE):
        return True

    # Mostly punctuation/digits or very short unsupported fragments.
    alnum_chars = re.findall(r"[a-z0-9]", normalized)
    if len(alnum_chars) <= 2:
        return True

    # Several nonsense-looking tokens with no recruiting signal.
    if len(tokens) >= 2 and all(len(token) <= 5 for token in tokens):
        return True

    return False


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
    - conservative START noise goes to fallback
    - RAG handles explicit document/policy questions
    - profile is the default candidate-data route
    """
    if detection.get("route"):
        return str(detection["route"])

    if detection.get("requires_human"):
        return "human_handoff"

    if detection.get("requires_clarification"):
        return "clarification"

    if (
        current_stage in {Stage.START.value, None, ""}
        and not detection.get("requires_rag")
        and detection.get("risk_level", "low") == "low"
        and _looks_like_noise_or_unsupported_start(message)
    ):
        return "fallback"

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
    reason = detection.get("reason")

    if route == "profile":
        requires_rag = False
        intent = intent or "candidate_answer"

    if route == "fallback":
        requires_rag = False
        intent = "fallback"
        reason = reason or "noise_or_unsupported_start"

    return {
        "intent": intent,
        "risk_level": risk_level,
        "requires_human": requires_human,
        "requires_rag": requires_rag,
        "requires_clarification": bool(detection.get("requires_clarification", False)),
        "reason": reason,
        "route": route,
        "route_detection": detection,
        "current_stage": effective_stage,
    }
