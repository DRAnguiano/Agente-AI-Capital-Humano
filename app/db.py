import logging
import os
from contextlib import contextmanager
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool


log = logging.getLogger(__name__)

RISK_RANK = {"low": 1, "medium": 2, "high": 3}

# Tamaño del pool configurable via .env.
# min=2: siempre hay 2 conexiones listas; max=10: techo bajo carga.
_POOL_MIN = int(os.getenv("POSTGRES_POOL_MIN", "2"))
_POOL_MAX = int(os.getenv("POSTGRES_POOL_MAX", "10"))

_pool: ConnectionPool | None = None


def _db_conninfo() -> str:
    host     = os.getenv("POSTGRES_HOST", "postgres")
    port     = os.getenv("POSTGRES_PORT", "5432")
    dbname   = os.getenv("POSTGRES_DB", "hrdb")
    user     = os.getenv("POSTGRES_USER", "hr_david")
    password = os.getenv("POSTGRES_PASSWORD", "")
    timeout  = os.getenv("POSTGRES_CONNECT_TIMEOUT", "5")
    return (
        f"host={host} port={port} dbname={dbname} "
        f"user={user} password={password} connect_timeout={timeout}"
    )


def _get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(
            conninfo=_db_conninfo(),
            min_size=_POOL_MIN,
            max_size=_POOL_MAX,
            kwargs={"row_factory": dict_row},
            open=True,
        )
        log.info("[DB_POOL] Pool inicializado min=%d max=%d", _POOL_MIN, _POOL_MAX)
    return _pool


@contextmanager
def get_conn():
    # Pool de conexiones: sin overhead TCP por llamada.
    # La interfaz es idéntica al get_conn() anterior — todos los callers
    # siguen usando "with get_conn() as conn:" sin cambios.
    with _get_pool().connection() as conn:
        yield conn


def _db_config() -> dict[str, Any]:
    # Mantenido por compatibilidad con cualquier código que lo llame directamente.
    return {
        "host": os.getenv("POSTGRES_HOST", "postgres"),
        "port": int(os.getenv("POSTGRES_PORT", "5432")),
        "dbname": os.getenv("POSTGRES_DB", "hrdb"),
        "user": os.getenv("POSTGRES_USER", "hr_david"),
        "password": os.getenv("POSTGRES_PASSWORD", ""),
        "connect_timeout": int(os.getenv("POSTGRES_CONNECT_TIMEOUT", "5")),
    }


def make_conversation_key(channel: str, channel_user_id: str) -> str:
    channel = (channel or "unknown").strip().lower()
    channel_user_id = (channel_user_id or "unknown").strip()
    return f"{channel}:{channel_user_id}"


def _normalize_risk_level(value: str | None, default: str = "low") -> str:
    risk = (value or default or "low").strip().lower()
    return risk if risk in RISK_RANK else default


def _max_risk_level(left: str | None, right: str | None) -> str:
    left_norm = _normalize_risk_level(left)
    right_norm = _normalize_risk_level(right)
    return left_norm if RISK_RANK[left_norm] >= RISK_RANK[right_norm] else right_norm


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


def release_human_review(conversation_key: str, stage_to: str = "START") -> None:
    """Vía explícita de liberación de HUMAN_REVIEW (acción humana/operativa).

    `update_stage` pin-ea `HUMAN_REVIEW_REQUIRED` a propósito para que el bot NO
    auto-regrese por mensajes del candidato. Esta función es la ÚNICA vía de salida:
    debe invocarse solo desde una acción humana/operativa explícita (agente que
    resuelve/reasigna en Chatwoot, o un endpoint admin), nunca desde el flujo
    automático del turno. Así se evita el bloqueo permanente sin reabrir el handoff
    por sí solo. El WHERE acota el efecto a conversaciones realmente en revisión humana.
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE rh_conversations
                SET
                    current_stage = %(stage_to)s,
                    requires_human = false,
                    risk_level = 'low',
                    updated_at = now()
                WHERE conversation_key = %(conversation_key)s
                  AND current_stage = 'HUMAN_REVIEW_REQUIRED';
                """,
                {
                    "conversation_key": conversation_key,
                    "stage_to": stage_to,
                },
            )


def sync_conversation_risk_from_profile(
    conversation_key: str,
    *,
    risk_level: str | None = None,
    requires_human: bool | None = None,
    intent: str | None = None,
) -> dict[str, Any] | None:
    """
    Synchronize aggregate conversation risk from candidate profile facts.

    This helper never downgrades risk or clears requires_human. It only promotes
    the conversation aggregate state when lead/profile ingestion discovers a
    higher-risk condition such as expiring documents or callback/handoff needs.
    """
    if not conversation_key:
        return None

    requested_risk = _normalize_risk_level(risk_level, default="low")
    requested_requires_human = bool(requires_human)

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT risk_level, requires_human
                FROM rh_conversations
                WHERE conversation_key = %(conversation_key)s;
                """,
                {"conversation_key": conversation_key},
            )
            current = cur.fetchone()
            if not current:
                return None

            next_risk = _max_risk_level(current.get("risk_level"), requested_risk)
            next_requires_human = bool(current.get("requires_human", False)) or requested_requires_human

            cur.execute(
                """
                UPDATE rh_conversations
                SET
                    risk_level = %(risk_level)s,
                    requires_human = %(requires_human)s,
                    last_intent = COALESCE(%(intent)s, last_intent),
                    updated_at = now()
                WHERE conversation_key = %(conversation_key)s
                RETURNING conversation_key, risk_level, requires_human, last_intent;
                """,
                {
                    "conversation_key": conversation_key,
                    "risk_level": next_risk,
                    "requires_human": next_requires_human,
                    "intent": intent,
                },
            )
            row = cur.fetchone()

    return dict(row) if row else None


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
        "substance_disclosure",
        "substance_disclosure_status",
        "substance_disclosure_context",
        "substance_last_use_text",
        "substance_operational_risk",
        "substance_requires_review",
        "substance_analytics_flag",
        "substance_analytics_category",
        "substance_raw_mention",
    }

    clean_fields = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if not clean_fields:
        return

    set_sql = ", ".join([f"{key} = %({key})s" for key in clean_fields])
    params = {"conversation_key": conversation_key, **clean_fields}
    if "substance_disclosure" in params and isinstance(params["substance_disclosure"], (dict, list)):
        params["substance_disclosure"] = Jsonb(params["substance_disclosure"])

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
