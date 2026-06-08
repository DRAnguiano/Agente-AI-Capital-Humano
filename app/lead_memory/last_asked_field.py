"""Read-only: último campo que el funnel preguntó (captura pasiva).

Lee ``asked_field_keys`` del mensaje assistant más reciente que lo tenga en
``rh_lead_messages_v2.external_metadata``. Shadow-safe: NO escribe, NO decide,
NO infiere desde texto y NO usa ``last_bot_message`` textual como fuente.

Aún NO se cablea al parser contextual; es solo lectura de la metadata que
``_store_lead_memory_updates`` persiste cuando hay un nudge del funnel con
claves canónicas confiables. Las claves devueltas están en espacio canónico.
"""
from __future__ import annotations

import logging
from typing import Any

from app.db import get_conn

log = logging.getLogger(__name__)


def read_last_asked_field_keys(lead_key: str) -> list[str] | None:
    """Devuelve las ``asked_field_keys`` canónicas del último assistant que las tenga.

    Retorna ``None`` si no hay lead_key, si ningún mensaje las registró, o ante
    cualquier error de lectura (degradación segura: nunca rompe el flujo).
    La lista nunca se infiere desde texto; proviene tal cual de la metadata.
    """
    if not lead_key:
        return None

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT external_metadata
                    FROM rh_lead_messages_v2
                    WHERE lead_key = %(lead_key)s
                      AND role = 'assistant'
                      AND external_metadata ? 'asked_field_keys'
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    {"lead_key": lead_key},
                )
                row = cur.fetchone()
    except Exception as exc:
        log.warning("[LAST_ASKED_FIELD] lectura falló, desactivado: %s", exc)
        return None

    if not row:
        return None

    metadata: dict[str, Any] = row.get("external_metadata") or {}
    keys = metadata.get("asked_field_keys")
    if isinstance(keys, list) and keys:
        return [str(k) for k in keys]
    return None


def read_current_asked_field_keys(lead_key: str) -> list[str] | None:
    """Fresh canonical asked field keys del ÚLTIMO mensaje assistant real.

    Freshness strict: lee SOLO el assistant inmediatamente anterior (orden por
    ``created_at DESC, id DESC``), SIN reach-back. Si ese último assistant no
    tiene ``asked_field_keys`` (p. ej. un reply que no fue nudge del funnel) →
    ``None``. Así route-1 nunca usa metadata vieja como campo activo.

    Degradación segura: cualquier error de lectura → ``None``.
    """
    if not lead_key:
        return None

    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT external_metadata
                    FROM rh_lead_messages_v2
                    WHERE lead_key = %(lead_key)s
                      AND role = 'assistant'
                    ORDER BY created_at DESC, id DESC
                    LIMIT 1
                    """,
                    {"lead_key": lead_key},
                )
                row = cur.fetchone()
    except Exception as exc:
        log.warning("[LAST_ASKED_FIELD] lectura current falló, desactivado: %s", exc)
        return None

    if not row:
        return None

    metadata: dict[str, Any] = row.get("external_metadata") or {}
    keys = metadata.get("asked_field_keys")
    if isinstance(keys, list) and keys:
        return [str(k) for k in keys]
    return None
