from typing import Any

from app.db import get_conversation_state, make_conversation_key, save_message, upsert_conversation
from app.graphs.hr_state import HRState


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


def save_assistant_message_node(state: HRState) -> dict[str, Any]:
    """
    Persist the generated assistant reply.

    This is the first output persistence node used by the RAG replacement
    diagnostic graph. It intentionally does not update stages or handoff state.
    Those responsibilities will get their own nodes later.
    """
    conversation_key = state.get("conversation_key")
    reply = (state.get("reply") or state.get("text") or "").strip()

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
