import os
from contextlib import contextmanager
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


def _db_config() -> dict[str, Any]:
    return {
        "host": os.getenv("POSTGRES_HOST", "postgres"),
        "port": int(os.getenv("POSTGRES_PORT", "5432")),
        "dbname": os.getenv("POSTGRES_DB", "hrdb"),
        "user": os.getenv("POSTGRES_USER", "hr_david"),
        "password": os.getenv("POSTGRES_PASSWORD", ""),
    }


@contextmanager
def get_conn():
    conn = psycopg.connect(**_db_config(), row_factory=dict_row)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def make_conversation_key(channel: str, channel_user_id: str) -> str:
    channel = (channel or "unknown").strip().lower()
    channel_user_id = (channel_user_id or "unknown").strip()
    return f"{channel}:{channel_user_id}"


def upsert_conversation(
    channel: str,
    channel_user_id: str,
    username: str | None = None,
    phone: str | None = None,
) -> dict[str, Any]:
    conversation_key = make_conversation_key(channel, channel_user_id)

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO rh_conversations (
                    channel,
                    channel_user_id,
                    conversation_key,
                    candidate_name,
                    current_stage,
                    status,
                    last_message_at,
                    updated_at
                )
                VALUES (
                    %(channel)s,
                    %(channel_user_id)s,
                    %(conversation_key)s,
                    %(candidate_name)s,
                    'START',
                    'OPEN',
                    now(),
                    now()
                )
                ON CONFLICT (conversation_key)
                DO UPDATE SET
                    updated_at = now(),
                    last_message_at = now()
                RETURNING *;
                """,
                {
                    "channel": channel,
                    "channel_user_id": channel_user_id,
                    "conversation_key": conversation_key,
                    "candidate_name": username,
                },
            )
            conversation = cur.fetchone()

            cur.execute(
                """
                INSERT INTO rh_candidate_profile (
                    conversation_key,
                    telefono,
                    source,
                    updated_at
                )
                VALUES (
                    %(conversation_key)s,
                    %(phone)s,
                    %(source)s,
                    now()
                )
                ON CONFLICT (conversation_key)
                DO UPDATE SET
                    telefono = COALESCE(EXCLUDED.telefono, rh_candidate_profile.telefono),
                    source = COALESCE(EXCLUDED.source, rh_candidate_profile.source),
                    updated_at = now()
                RETURNING *;
                """,
                {
                    "conversation_key": conversation_key,
                    "phone": phone,
                    "source": channel,
                },
            )
            profile = cur.fetchone()

            cur.execute(
                """
                INSERT INTO rh_channel_identities (
                    conversation_key,
                    channel,
                    channel_user_id,
                    phone,
                    username,
                    updated_at
                )
                VALUES (
                    %(conversation_key)s,
                    %(channel)s,
                    %(channel_user_id)s,
                    %(phone)s,
                    %(username)s,
                    now()
                )
                ON CONFLICT (channel, channel_user_id)
                DO UPDATE SET
                    phone = COALESCE(EXCLUDED.phone, rh_channel_identities.phone),
                    username = COALESCE(EXCLUDED.username, rh_channel_identities.username),
                    updated_at = now()
                RETURNING *;
                """,
                {
                    "conversation_key": conversation_key,
                    "channel": channel,
                    "channel_user_id": channel_user_id,
                    "phone": phone,
                    "username": username,
                },
            )

            return {
                "conversation": conversation,
                "profile": profile,
                "conversation_key": conversation_key,
            }


def get_conversation_state(conversation_key: str) -> dict[str, Any]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM rh_conversations
                WHERE conversation_key = %(conversation_key)s;
                """,
                {"conversation_key": conversation_key},
            )
            conversation = cur.fetchone()

            cur.execute(
                """
                SELECT *
                FROM rh_candidate_profile
                WHERE conversation_key = %(conversation_key)s;
                """,
                {"conversation_key": conversation_key},
            )
            profile = cur.fetchone()

            cur.execute(
                """
                SELECT role, message, created_at
                FROM rh_messages
                WHERE conversation_key = %(conversation_key)s
                ORDER BY created_at DESC
                LIMIT 8;
                """,
                {"conversation_key": conversation_key},
            )
            messages = list(reversed(cur.fetchall()))

            return {
                "conversation": conversation,
                "profile": profile,
                "messages": messages,
            }


def save_message(conversation_key: str, role: str, message: str) -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO rh_messages (
                    conversation_key,
                    role,
                    message,
                    created_at
                )
                VALUES (
                    %(conversation_key)s,
                    %(role)s,
                    %(message)s,
                    now()
                );
                """,
                {
                    "conversation_key": conversation_key,
                    "role": role,
                    "message": message,
                },
            )


def log_event(
    conversation_key: str,
    event_type: str,
    stage_from: str | None = None,
    stage_to: str | None = None,
    intent: str | None = None,
    risk_level: str = "low",
    requires_human: bool = False,
    metadata: dict[str, Any] | None = None,
) -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO rh_candidate_events (
                    conversation_key,
                    event_type,
                    stage_from,
                    stage_to,
                    intent,
                    risk_level,
                    requires_human,
                    metadata,
                    created_at
                )
                VALUES (
                    %(conversation_key)s,
                    %(event_type)s,
                    %(stage_from)s,
                    %(stage_to)s,
                    %(intent)s,
                    %(risk_level)s,
                    %(requires_human)s,
                    %(metadata)s,
                    now()
                );
                """,
                {
                    "conversation_key": conversation_key,
                    "event_type": event_type,
                    "stage_from": stage_from,
                    "stage_to": stage_to,
                    "intent": intent,
                    "risk_level": risk_level,
                    "requires_human": requires_human,
                    "metadata": Jsonb(metadata or {}),
                },
            )


def update_stage(
    conversation_key: str,
    stage_to: str,
    intent: str | None = None,
    risk_level: str = "low",
    requires_human: bool = False,
) -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE rh_conversations
                SET
                    current_stage = CASE
                        WHEN current_stage = 'HUMAN_REVIEW_REQUIRED'
                        THEN 'HUMAN_REVIEW_REQUIRED'
                        ELSE %(stage_to)s
                    END,
                    last_intent = %(intent)s,
                    risk_level = CASE
                        WHEN current_stage = 'HUMAN_REVIEW_REQUIRED'
                        THEN 'high'
                        ELSE %(risk_level)s
                    END,
                    requires_human = CASE
                        WHEN current_stage = 'HUMAN_REVIEW_REQUIRED'
                        THEN true
                        ELSE %(requires_human)s
                    END,
                    updated_at = now()
                WHERE conversation_key = %(conversation_key)s;
                """,
                {
                    "conversation_key": conversation_key,
                    "stage_to": stage_to,
                    "intent": intent,
                    "risk_level": risk_level,
                    "requires_human": requires_human,
                },
            )


def update_candidate_profile(conversation_key: str, fields: dict[str, Any]) -> None:
    allowed = {
        "nombre_completo",
        "edad",
        "ciudad",
        "ciudad_raw",
        "estado_region",
        "pais_codigo",
        "pais_nombre",
        "city_group",
        "is_local_laguna",
        "is_foreign_country",
        "location_requires_ch_validation",
        "location_needs_travel_validation",
        "city_catalog_alias",
        "city_catalog_id",
        "telefono",
        "experiencia_quinta_rueda",
        "licencia_federal",
        "tipo_licencia",
        "apto_medico",
        "disponibilidad_viajar",
        "ultimo_empleo",
        "motivo_salida",
        "documentos",
        "perfil_status",
        "score",
        "observaciones",
        "source",
        "vacancy",
        "last_detected_intent",
        "risk_level",
        "requires_human",
    }

    clean_fields = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if not clean_fields:
        return

    set_sql = ", ".join([f"{key} = %({key})s" for key in clean_fields])
    params = {"conversation_key": conversation_key, **clean_fields}

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                UPDATE rh_candidate_profile
                SET {set_sql},
                    updated_at = now()
                WHERE conversation_key = %(conversation_key)s;
                """,
                params,
            )


def create_handoff(
    conversation_key: str,
    reason: str,
    risk_level: str = "high",
    summary: str | None = None,
) -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO rh_human_handoffs (
                    conversation_key,
                    reason,
                    risk_level,
                    status,
                    summary,
                    created_at
                )
                SELECT
                    %(conversation_key)s,
                    %(reason)s,
                    %(risk_level)s,
                    'OPEN',
                    %(summary)s,
                    now()
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM rh_human_handoffs
                    WHERE conversation_key = %(conversation_key)s
                      AND status = 'OPEN'
                      AND reason = %(reason)s
                );
                """,
                {
                    "conversation_key": conversation_key,
                    "reason": reason,
                    "risk_level": risk_level,
                    "summary": summary,
                },
            )


def save_rag_audit(
    conversation_key: str,
    user_message: str,
    answer: str,
    sources: list[dict[str, Any]],
    top_k: int | None,
    min_score: float | None,
) -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO rh_rag_audit (
                    conversation_key,
                    user_message,
                    answer,
                    sources,
                    top_k,
                    min_score,
                    created_at
                )
                VALUES (
                    %(conversation_key)s,
                    %(user_message)s,
                    %(answer)s,
                    %(sources)s,
                    %(top_k)s,
                    %(min_score)s,
                    now()
                );
                """,
                {
                    "conversation_key": conversation_key,
                    "user_message": user_message,
                    "answer": answer,
                    "sources": Jsonb(sources or []),
                    "top_k": top_k,
                    "min_score": min_score,
                },
            )


def find_city_catalog_match(city_text: str) -> dict[str, Any] | None:
    """
    Busca una ciudad/alias en rh_city_catalog.

    Intenta:
    - match exacto contra alias_norm
    - match contenido: "soy de nuevo laredo" contiene "nuevo laredo"

    Devuelve la mejor coincidencia o None.
    """
    raw = (city_text or "").strip()
    if not raw:
        return None

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                WITH q AS (
                    SELECT rh_norm_text(%(city_text)s) AS query_norm
                )
                SELECT
                    c.id,
                    c.alias_text,
                    c.alias_norm,
                    c.canonical_city,
                    c.state_region,
                    c.country_code,
                    c.country_name,
                    c.city_group,
                    c.is_local_laguna,
                    c.is_foreign_country,
                    c.requires_ch_validation,
                    c.needs_travel_validation,
                    c.notes
                FROM rh_city_catalog c
                CROSS JOIN q
                WHERE
                    c.alias_norm = q.query_norm
                    OR q.query_norm LIKE '%%' || c.alias_norm || '%%'
                ORDER BY
                    CASE
                        WHEN c.alias_norm = q.query_norm THEN 1
                        ELSE 2
                    END,
                    length(c.alias_norm) DESC,
                    c.alias_text ASC
                LIMIT 1;
                """,
                {"city_text": raw},
            )
            row = cur.fetchone()

    return dict(row) if row else None