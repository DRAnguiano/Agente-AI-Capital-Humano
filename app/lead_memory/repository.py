from __future__ import annotations

from typing import Any

from app.db import make_conversation_key


def make_lead_key(channel: str, channel_user_id: str) -> str:
    return make_conversation_key(channel, channel_user_id)


def upsert_lead_identity(**kwargs: Any) -> dict[str, Any]:
    channel = str(kwargs.get("channel") or "chatwoot")
    channel_user_id = str(kwargs.get("channel_user_id") or "unknown")
    key = make_lead_key(channel, channel_user_id)
    return {"lead_key": key, "conversation_key": key, "lead": {}, "conversation": {}}


def save_lead_message(**kwargs: Any) -> dict[str, Any] | None:
    return None


def upsert_lead_fact(**kwargs: Any) -> dict[str, Any] | None:
    return None


def log_lead_event(**kwargs: Any) -> dict[str, Any] | None:
    return None


def update_lead_summary(**kwargs: Any) -> dict[str, Any] | None:
    return None


def get_lead_memory(**kwargs: Any) -> dict[str, Any]:
    return {"lead": None, "facts": [], "messages": [], "events": []}
