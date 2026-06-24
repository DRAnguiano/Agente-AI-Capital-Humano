from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb

from app.db import get_conn, make_conversation_key


STAGE_ORDER: dict[str, int] = {
    "new": 10,
    "interested": 20,
    "vacancy_info_shared": 30,
    "profile_hint_collected": 40,
    "documents_pending": 50,
    "documents_received": 60,
    "apto_pending_update": 70,
    "safety_review": 80,
    "followup_pending": 90,
    "human_review": 95,
    "lost": 100,
    "closed": 110,
}

RISK_ORDER: dict[str, int] = {"low": 1, "medium": 2, "high": 3}


def _safe_text(value: Any, default: str = "") -> str:
    text = str(value or default or "").strip()
    return text or default


def _normalize_risk(value: str | None) -> str:
    risk = _safe_text(value, "low").lower()
    return risk if risk in RISK_ORDER else "low"


def _max_risk(left: str | None, right: str | None) -> str:
    lval = _normalize_risk(left)
    rval = _normalize_risk(right)
    return lval if RISK_ORDER[lval] >= RISK_ORDER[rval] else rval


def _ranked_stage(current: str | None, candidate: str | None) -> str:
    current_stage = _safe_text(current, "new")
    candidate_stage = _safe_text(candidate, current_stage)
    return candidate_stage if STAGE_ORDER.get(candidate_stage, 0) >= STAGE_ORDER.get(current_stage, 0) else current_stage


def make_lead_key(channel: str, channel_user_id: str) -> str:
    return make_conversation_key(channel, channel_user_id)


def upsert_lead_identity(
    *,
    channel: str,
    channel_user_id: str,
    username: str | None = None,
    phone: str | None = None,
    chatwoot_account_id: str | int | None = None,
    chatwoot_inbox_id: str | int | None = None,
    chatwoot_conversation_id: str | int | None = None,
    chatwoot_contact_id: str | int | None = None,
    external_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create/update lead identity and its channel conversation.

    This is memory plumbing, not conversation routing. The lead_key currently maps
    1:1 to the channel identity; future merges can point multiple conversations
    to the same lead_key.
    """
    lead_key = make_lead_key(channel, channel_user_id)
    conversation_key = lead_key

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO rh_leads_v2 (
                    lead_key,
                    display_name,
                    phone,
                    source_channel,
                    last_seen_at,
                    updated_at
                )
                VALUES (
                    %(lead_key)s,
                    %(display_name)s,
                    %(phone)s,
                    %(source_channel)s,
                    now(),
                    now()
                )
                ON CONFLICT (lead_key)
                DO UPDATE SET
                    display_name = COALESCE(EXCLUDED.display_name, rh_leads_v2.display_name),
                    phone = COALESCE(EXCLUDED.phone, rh_leads_v2.phone),
                    source_channel = COALESCE(EXCLUDED.source_channel, rh_leads_v2.source_channel),
                    last_seen_at = now(),
                    updated_at = now()
                RETURNING *;
                """,
                {
                    "lead_key": lead_key,
                    "display_name": username,
                    "phone": phone,
                    "source_channel": channel,
                },
            )
            lead = cur.fetchone()

            cur.execute(
                """
                INSERT INTO rh_lead_conversations_v2 (
                    lead_key,
                    conversation_key,
                    channel,
                    channel_user_id,
                    chatwoot_account_id,
                    chatwoot_inbox_id,
                    chatwoot_conversation_id,
                    chatwoot_contact_id,
                    external_metadata,
                    updated_at
                )
                VALUES (
                    %(lead_key)s,
                    %(conversation_key)s,
                    %(channel)s,
                    %(channel_user_id)s,
                    %(chatwoot_account_id)s,
                    %(chatwoot_inbox_id)s,
                    %(chatwoot_conversation_id)s,
                    %(chatwoot_contact_id)s,
                    %(external_metadata)s,
                    now()
                )
                ON CONFLICT (conversation_key)
                DO UPDATE SET
                    channel = EXCLUDED.channel,
                    channel_user_id = EXCLUDED.channel_user_id,
                    chatwoot_account_id = COALESCE(EXCLUDED.chatwoot_account_id, rh_lead_conversations_v2.chatwoot_account_id),
                    chatwoot_inbox_id = COALESCE(EXCLUDED.chatwoot_inbox_id, rh_lead_conversations_v2.chatwoot_inbox_id),
                    chatwoot_conversation_id = COALESCE(EXCLUDED.chatwoot_conversation_id, rh_lead_conversations_v2.chatwoot_conversation_id),
                    chatwoot_contact_id = COALESCE(EXCLUDED.chatwoot_contact_id, rh_lead_conversations_v2.chatwoot_contact_id),
                    external_metadata = rh_lead_conversations_v2.external_metadata || EXCLUDED.external_metadata,
                    updated_at = now()
                RETURNING *;
                """,
                {
                    "lead_key": lead_key,
                    "conversation_key": conversation_key,
                    "channel": channel,
                    "channel_user_id": channel_user_id,
                    "chatwoot_account_id": str(chatwoot_account_id) if chatwoot_account_id is not None else None,
                    "chatwoot_inbox_id": str(chatwoot_inbox_id) if chatwoot_inbox_id is not None else None,
                    "chatwoot_conversation_id": str(chatwoot_conversation_id) if chatwoot_conversation_id is not None else None,
                    "chatwoot_contact_id": str(chatwoot_contact_id) if chatwoot_contact_id is not None else None,
                    "external_metadata": Jsonb(external_metadata or {}),
                },
            )
            conversation = cur.fetchone()

    return {"lead": dict(lead), "conversation": dict(conversation), "lead_key": lead_key, "conversation_key": conversation_key}


def save_lead_message(
    *,
    lead_key: str,
    conversation_key: str,
    role: str,
    message: str,
    source_message_id: str | int | None = None,
    external_metadata: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    if not lead_key or not conversation_key or not message:
        return None

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO rh_lead_messages_v2 (
                    lead_key,
                    conversation_key,
                    role,
                    message,
                    source_message_id,
                    external_metadata,
                    created_at
                )
                VALUES (
                    %(lead_key)s,
                    %(conversation_key)s,
                    %(role)s,
                    %(message)s,
                    %(source_message_id)s,
                    %(external_metadata)s,
                    now()
                )
                RETURNING *;
                """,
                {
                    "lead_key": lead_key,
                    "conversation_key": conversation_key,
                    "role": role,
                    "message": message,
                    "source_message_id": str(source_message_id) if source_message_id is not None else None,
                    "external_metadata": Jsonb(external_metadata or {}),
                },
            )
            row = cur.fetchone()

    return dict(row) if row else None


def upsert_lead_fact(
    *,
    lead_key: str,
    fact_group: str,
    fact_key: str,
    fact_value: str,
    confidence: float = 0.7,
    source: str = "conversation",
    source_message_id: int | None = None,
    source_text: str | None = None,
    fact_value_json: dict[str, Any] | list[Any] | None = None,
) -> dict[str, Any] | None:
    if not lead_key or not fact_group or not fact_key or not fact_value:
        return None

    confidence = max(0.0, min(float(confidence or 0.7), 1.0))

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO rh_lead_facts_v2 (
                    lead_key,
                    fact_group,
                    fact_key,
                    fact_value,
                    fact_value_json,
                    confidence,
                    source,
                    source_message_id,
                    source_text,
                    is_active,
                    observed_at,
                    updated_at
                )
                VALUES (
                    %(lead_key)s,
                    %(fact_group)s,
                    %(fact_key)s,
                    %(fact_value)s,
                    %(fact_value_json)s,
                    %(confidence)s,
                    %(source)s,
                    %(source_message_id)s,
                    %(source_text)s,
                    true,
                    now(),
                    now()
                )
                ON CONFLICT (lead_key, fact_group, fact_key, is_active)
                DO UPDATE SET
                    fact_value = EXCLUDED.fact_value,
                    fact_value_json = COALESCE(EXCLUDED.fact_value_json, rh_lead_facts_v2.fact_value_json),
                    confidence = GREATEST(rh_lead_facts_v2.confidence, EXCLUDED.confidence),
                    source = EXCLUDED.source,
                    source_message_id = COALESCE(EXCLUDED.source_message_id, rh_lead_facts_v2.source_message_id),
                    source_text = COALESCE(EXCLUDED.source_text, rh_lead_facts_v2.source_text),
                    observed_at = now(),
                    updated_at = now()
                RETURNING *;
                """,
                {
                    "lead_key": lead_key,
                    "fact_group": fact_group,
                    "fact_key": fact_key,
                    "fact_value": fact_value,
                    "fact_value_json": Jsonb(fact_value_json) if fact_value_json is not None else None,
                    "confidence": confidence,
                    "source": source,
                    "source_message_id": source_message_id,
                    "source_text": source_text,
                },
            )
            row = cur.fetchone()

    return dict(row) if row else None


def log_lead_event(
    *,
    lead_key: str,
    conversation_key: str | None,
    event_type: str,
    intent: str | None = None,
    route: str | None = None,
    stage_from: str | None = None,
    stage_to: str | None = None,
    risk_level: str = "low",
    requires_human: bool = False,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    if not lead_key or not event_type:
        return None

    risk_level = _normalize_risk(risk_level)

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO rh_lead_events_v2 (
                    lead_key,
                    conversation_key,
                    event_type,
                    intent,
                    route,
                    stage_from,
                    stage_to,
                    risk_level,
                    requires_human,
                    metadata,
                    created_at
                )
                VALUES (
                    %(lead_key)s,
                    %(conversation_key)s,
                    %(event_type)s,
                    %(intent)s,
                    %(route)s,
                    %(stage_from)s,
                    %(stage_to)s,
                    %(risk_level)s,
                    %(requires_human)s,
                    %(metadata)s,
                    now()
                )
                RETURNING *;
                """,
                {
                    "lead_key": lead_key,
                    "conversation_key": conversation_key,
                    "event_type": event_type,
                    "intent": intent,
                    "route": route,
                    "stage_from": stage_from,
                    "stage_to": stage_to,
                    "risk_level": risk_level,
                    "requires_human": requires_human,
                    "metadata": Jsonb(metadata or {}),
                },
            )
            row = cur.fetchone()

    return dict(row) if row else None


def update_lead_summary(
    *,
    lead_key: str,
    funnel_stage: str | None = None,
    lead_status: str | None = None,
    next_best_action: str | None = None,
    memory_summary: str | None = None,
    facts_summary: dict[str, Any] | None = None,
    risk_level: str | None = None,
    requires_human: bool | None = None,
) -> dict[str, Any] | None:
    if not lead_key:
        return None

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT funnel_stage, risk_level, requires_human
                FROM rh_leads_v2
                WHERE lead_key = %(lead_key)s;
                """,
                {"lead_key": lead_key},
            )
            current = cur.fetchone()
            if not current:
                return None

            next_stage = _ranked_stage(current.get("funnel_stage"), funnel_stage)
            next_risk = _max_risk(current.get("risk_level"), risk_level)
            next_requires_human = bool(current.get("requires_human")) or bool(requires_human)
            next_status = lead_status
            if not next_status:
                if next_requires_human:
                    next_status = "human_review"
                elif next_stage == "followup_pending":
                    next_status = "followup_pending"
                else:
                    next_status = "open"

            cur.execute(
                """
                UPDATE rh_leads_v2
                SET
                    funnel_stage = %(funnel_stage)s,
                    lead_status = %(lead_status)s,
                    next_best_action = COALESCE(%(next_best_action)s, next_best_action),
                    memory_summary = COALESCE(%(memory_summary)s, memory_summary),
                    facts_summary = CASE
                        WHEN %(facts_summary)s IS NULL THEN facts_summary
                        ELSE facts_summary || %(facts_summary)s
                    END,
                    risk_level = %(risk_level)s,
                    requires_human = %(requires_human)s,
                    last_seen_at = now(),
                    updated_at = now()
                WHERE lead_key = %(lead_key)s
                RETURNING *;
                """,
                {
                    "lead_key": lead_key,
                    "funnel_stage": next_stage,
                    "lead_status": next_status,
                    "next_best_action": next_best_action,
                    "memory_summary": memory_summary,
                    "facts_summary": Jsonb(facts_summary) if facts_summary is not None else None,
                    "risk_level": next_risk,
                    "requires_human": next_requires_human,
                },
            )
            row = cur.fetchone()

    return dict(row) if row else None


def get_lead_memory(*, lead_key: str | None = None, conversation_key: str | None = None, limit_messages: int = 8) -> dict[str, Any]:
    if not lead_key and conversation_key:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT lead_key
                    FROM rh_lead_conversations_v2
                    WHERE conversation_key = %(conversation_key)s;
                    """,
                    {"conversation_key": conversation_key},
                )
                row = cur.fetchone()
                lead_key = row.get("lead_key") if row else None

    if not lead_key:
        return {"lead": None, "facts": [], "messages": [], "events": []}

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM v_rh_lead_memory_v2 WHERE lead_key = %(lead_key)s;", {"lead_key": lead_key})
            lead = cur.fetchone()

            cur.execute(
                """
                SELECT fact_group, fact_key, fact_value, confidence, source_text, observed_at
                FROM rh_lead_facts_v2
                WHERE lead_key = %(lead_key)s
                  AND is_active = true
                ORDER BY updated_at DESC;
                """,
                {"lead_key": lead_key},
            )
            facts = cur.fetchall()

            cur.execute(
                """
                SELECT role, message, created_at
                FROM rh_lead_messages_v2
                WHERE lead_key = %(lead_key)s
                ORDER BY created_at DESC
                LIMIT %(limit)s;
                """,
                {"lead_key": lead_key, "limit": int(limit_messages)},
            )
            messages = list(reversed(cur.fetchall()))

            cur.execute(
                """
                SELECT event_type, intent, route, stage_to, risk_level, created_at
                FROM rh_lead_events_v2
                WHERE lead_key = %(lead_key)s
                ORDER BY created_at DESC
                LIMIT 10;
                """,
                {"lead_key": lead_key},
            )
            events = cur.fetchall()

    return {
        "lead": dict(lead) if lead else None,
        "facts": [dict(row) for row in facts],
        "messages": [dict(row) for row in messages],
        "events": [dict(row) for row in events],
    }
