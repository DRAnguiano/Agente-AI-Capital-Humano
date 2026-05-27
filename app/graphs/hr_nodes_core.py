import re
from typing import Any

from app.db import get_conversation_state, make_conversation_key, save_message, upsert_conversation
from app.graphs.hr_state import HRState
from app.graphs.hr_output_guard import apply_output_guard


DEFAULT_STAGE = "START"


def normalize_input_node(state: HRState) -> dict[str, Any]:
    """
    Normalize inbound fields before DB work.

    This node is safe to run at the beginning of every graph execution. It only
    touches primitive input fields and does not perform side effects.
    """
    message = (state.get("message") or "").strip()
    channel = (state.get("channel") or "chatwoot").strip().lower()
    channel_user_id = str(
        state.get("channel_user_id")
        or state.get("phone")
        or state.get("chatwoot_contact_id")
        or state.get("chatwoot_conversation_id")
        or "unknown"
    ).strip()

    return {
        "message": message,
        "question": message,
        "channel": channel,
        "channel_user_id": channel_user_id,
        "conversation_key": make_conversation_key(channel, channel_user_id),
    }


def load_conversation_node(state: HRState) -> dict[str, Any]:
    """
    Create/update the conversation and load DB state.

    Side effects:
    - upserts rh_conversations
    - upserts rh_candidate_profile
    - upserts rh_channel_identities

    It intentionally does NOT save the incoming message. That belongs to
    save_incoming_message_node so the graph keeps each responsibility small.
    """
    setup = upsert_conversation(
        channel=state["channel"],
        channel_user_id=state["channel_user_id"],
        username=state.get("username"),
        phone=state.get("phone"),
    )

    conversation_key = setup["conversation_key"]
    db_state = get_conversation_state(conversation_key)
    conversation = db_state.get("conversation") or {}
    profile = db_state.get("profile") or {}

    return {
        "conversation_key": conversation_key,
        "conversation_id": conversation.get("id"),
        "candidate_id": profile.get("id"),
        "current_stage": conversation.get("current_stage") or DEFAULT_STAGE,
        "next_stage": conversation.get("current_stage") or DEFAULT_STAGE,
        "conversation_snapshot": conversation,
        "profile_snapshot": profile,
        "history_messages": db_state.get("messages", []),
    }


def save_incoming_message_node(state: HRState) -> dict[str, Any]:
    """
    Persist the inbound candidate message.

    This node is not yet wired into the active production route because the
    legacy orchestrator still saves the incoming message internally. It is used
    by diagnostic/replacement graphs where we avoid the legacy setup path.
    """
    conversation_key = state.get("conversation_key")
    message = (state.get("message") or "").strip()

    if not conversation_key or not message:
        return {
            "incoming_message_saved": False,
        }

    save_message(conversation_key, "user", message)

    return {
        "incoming_message_saved": True,
        "events": [
            {
                "type": "incoming_message_saved",
                "conversation_key": conversation_key,
                "external_message_id": state.get("external_message_id"),
            }
        ],
    }



def _strip_rag_profile_continuation(reply: str) -> str:
    """
    Remove profile-capture continuations that should not appear at the end of a
    RAG answer. RAG must answer the candidate's question first and should not
    advance the form unless the graph explicitly routes to profile.
    """
    text = (reply or "").strip()
    if not text:
        return text

    # Remove complete paragraphs that try to continue profiling from a RAG answer.
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    clean_parts = []

    for paragraph in paragraphs:
        normalized = paragraph.lower()

        is_profile_push = (
            ("si quieres aplicar" in normalized or "podemos continuar con el proceso" in normalized)
            and (
                "nombre completo" in normalized
                or "cuál es tu nombre" in normalized
                or "cual es tu nombre" in normalized
                or "me confirmas tu nombre" in normalized
            )
        )

        is_bad_lead_ack = (
            "ya registré tus datos principales" in normalized
            or "ya registre tus datos principales" in normalized
        )

        is_generic_close = (
            "si tienes más dudas" in normalized
            or "si tienes mas dudas" in normalized
            or "estoy aquí para" in normalized
            or "estoy aqui para" in normalized
            or "puedo ayudarte" in normalized
        )

        if is_profile_push or is_bad_lead_ack or is_generic_close:
            continue

        clean_parts.append(paragraph)

    return "\n\n".join(clean_parts).strip()


def _final_guard_is_ambiguous_cachimba(state: HRState) -> bool:
    analysis = state.get("substance_disclosure_analysis") or {}
    raw = str(analysis.get("raw_mention") or "")
    message = str(state.get("message") or "")
    rewrite = str((state.get("contextual_rewrite") or {}).get("rewritten") or "")

    haystack = f"{raw} {message} {rewrite}".lower()

    has_cachimba = any(
        term in haystack
        for term in ("cachimba", "cachimbear", "cachimbr", "cachimb")
    )

    return bool(
        has_cachimba
        and analysis.get("detected") is True
        and str(analysis.get("status") or "").upper() == "AMBIGUOUS"
    )


def _final_guard_sources_support_zero_tolerance(state: HRState) -> bool:
    sources = state.get("sources") or []
    retrieved_docs = state.get("relevant_docs") or state.get("retrieved_docs") or []

    all_items = []
    if isinstance(sources, list):
        all_items.extend(sources)
    if isinstance(retrieved_docs, list):
        all_items.extend(retrieved_docs)

    for item in all_items:
        if not isinstance(item, dict):
            continue

        source = str(
            item.get("source")
            or item.get("id")
            or item.get("metadata", {}).get("source")
            or ""
        ).lower()

        text = str(item.get("text") or item.get("content") or "").lower()

        combined = f"{source} {text}"

        if any(term in combined for term in (
            "03_seguridad_antidoping",
            "00_politicas_generales",
            "seguridad_antidoping",
            "politicas_generales",
            "cero tolerancia",
            "0 tolerancia",
            "toxicológica",
            "toxicologica",
            "antidoping",
            "sustancias",
            "alcohol",
        )):
            return True

    return False


def _final_guard_has_zero_tolerance_branch(reply: str) -> bool:
    text = (reply or "").lower()
    return any(term in text for term in (
        "cero tolerancia",
        "0 tolerancia",
        "toxicológica",
        "toxicologica",
        "antidoping",
        "sustancias",
        "alcohol",
    ))


def _apply_final_output_guard(reply: str, state: HRState) -> str:
    return apply_output_guard(reply, state)

def save_assistant_message_node(state: HRState) -> dict[str, Any]:
    """
    Persist the generated assistant reply.

    This is the first output persistence node used by the RAG replacement
    diagnostic graph. It intentionally does not update stages or handoff state.
    Those responsibilities will get their own nodes later.
    """
    conversation_key = state.get("conversation_key")
    reply = (state.get("reply") or state.get("text") or "").strip()
    reply = _apply_final_output_guard(reply, state)

    if not conversation_key or not reply:
        return {
            "assistant_message_saved": False,
        }

    save_message(conversation_key, "assistant", reply)

    return {
        "assistant_message_saved": True,
        "events": [
            {
                "type": "assistant_message_saved",
                "conversation_key": conversation_key,
            }
        ],
    }
