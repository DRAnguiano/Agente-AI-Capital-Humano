from typing import Any

from app.graphs.hr_state import HRState


MAX_MEMORY_TURNS = 8
SHORT_FOLLOWUP_MAX_CHARS = 80
FOLLOWUP_HINTS = {
    "como ve",
    "cómo ve",
    "y entonces",
    "entonces",
    "y ahora",
    "ahora que",
    "que procede",
    "qué procede",
    "ya no",
    "si puedo",
    "puedo seguir",
    "lo que dije",
    "le dije",
    "eso que dije",
}


def _compact_message(row: dict[str, Any]) -> dict[str, str]:
    return {
        "role": str(row.get("role") or "").strip(),
        "message": str(row.get("message") or "").strip(),
    }


def _last_message_by_role(turns: list[dict[str, str]], role: str) -> str | None:
    for item in reversed(turns):
        if item.get("role") == role and item.get("message"):
            return item["message"]
    return None


def _looks_like_followup(message: str) -> bool:
    text = (message or "").strip().lower()
    if not text:
        return False

    if len(text) <= SHORT_FOLLOWUP_MAX_CHARS and any(hint in text for hint in FOLLOWUP_HINTS):
        return True

    # Short questions such as "como ve?" or "y ya no podré?" are often
    # dependent on the previous user turn and should not be classified alone.
    if len(text) <= 35 and ("?" in text or "¿" in text):
        return True

    return False


def _build_brief_summary(turns: list[dict[str, str]]) -> str:
    if not turns:
        return "No hay historial conversacional previo."

    readable = []
    for item in turns[-MAX_MEMORY_TURNS:]:
        role = "Candidato" if item.get("role") == "user" else "Asistente"
        message = item.get("message") or ""
        if message:
            readable.append(f"{role}: {message}")

    if not readable:
        return "No hay historial conversacional previo utilizable."

    return " | ".join(readable)


def build_conversation_memory_node(state: HRState) -> dict[str, Any]:
    """
    Build compact conversational memory before classifying the new message.

    This node does not write to DB and does not decide routing. It only turns the
    loaded message history into a compact memory object so the classifier can
    interpret short follow-ups such as "como ve?" using the previous turn.
    """
    raw_history = state.get("history_messages") or []
    turns = [_compact_message(row) for row in raw_history if isinstance(row, dict)]
    turns = [row for row in turns if row.get("message")]
    recent_turns = turns[-MAX_MEMORY_TURNS:]

    previous_user_message = _last_message_by_role(recent_turns, "user")
    previous_assistant_message = _last_message_by_role(recent_turns, "assistant")
    current_message = state.get("message") or ""
    current_may_reference_previous = bool(previous_user_message) and _looks_like_followup(current_message)

    memory = {
        "summary": _build_brief_summary(recent_turns),
        "recent_turns": recent_turns,
        "previous_user_message": previous_user_message,
        "previous_assistant_message": previous_assistant_message,
        "current_may_reference_previous": current_may_reference_previous,
        "classifier_instruction": (
            "Si current_may_reference_previous es true, clasifica el mensaje actual junto con "
            "previous_user_message y el historial reciente. No trates el mensaje actual como aislado."
        ),
    }

    return {
        "conversation_memory": memory,
        "events": [
            {
                "type": "conversation_memory_built",
                "turns_count": len(recent_turns),
                "current_may_reference_previous": current_may_reference_previous,
            }
        ],
    }
