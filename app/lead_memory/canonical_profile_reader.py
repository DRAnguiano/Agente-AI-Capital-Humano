"""Fase 2B.2 — canonical_profile_reader (I/O mínimo, shadow-safe).

Lee `v_rh_lead_facts_canonical` y devuelve `list[CanonicalFact]` (la misma dataclass del
`funnel_state_planner`, NO se duplica). Diseñado para shadow mode: si la vista no existe o
hay cualquier error de lectura, devuelve [] y NUNCA rompe el flujo vivo.

NO escribe nada. NO decide labels. NO se conecta al orquestador (eso es cutover).
"""
from __future__ import annotations

import logging

from app.db import get_conn
from app.knowledge.funnel_state_planner import CanonicalFact

log = logging.getLogger(__name__)

_VIEW = "v_rh_lead_facts_canonical"

_SELECT = """
    SELECT lead_key, is_active, confidence, source, observed_at,
           raw_group, raw_key, raw_value,
           canonical_group, canonical_key, canonical_value, canonical_unit, canonical_state
    FROM v_rh_lead_facts_canonical
    WHERE lead_key = %(lead_key)s AND is_active = true
    ORDER BY observed_at DESC NULLS LAST
"""


def _row_to_fact(row: dict) -> CanonicalFact:
    """Mapea una fila (dict) de la vista a CanonicalFact. Puro, testeable sin DB."""
    return CanonicalFact(
        lead_key=row.get("lead_key"),
        is_active=bool(row.get("is_active", True)),
        confidence=row.get("confidence"),
        source=row.get("source"),
        observed_at=row.get("observed_at"),
        raw_group=row.get("raw_group"),
        raw_key=row.get("raw_key"),
        raw_value=row.get("raw_value"),
        canonical_group=row.get("canonical_group"),
        canonical_key=row.get("canonical_key"),
        canonical_value=row.get("canonical_value"),
        canonical_unit=row.get("canonical_unit"),
        canonical_state=row.get("canonical_state"),
    )


def canonical_view_exists() -> bool:
    """True si la vista canónica existe en la BD.

    TODO(shadow/cutover): hoy consulta information_schema en cada llamada. Bajo tráfico
    real conviene cachear el resultado o verificarlo una vez al arranque para no convertir
    este probe en un cuello de botella.
    """
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM information_schema.views WHERE table_name = %(t)s LIMIT 1",
                    {"t": _VIEW},
                )
                return cur.fetchone() is not None
    except Exception:  # nunca romper por el probe
        return False


def read_canonical_facts(lead_key: str) -> list[CanonicalFact]:
    """Lee los facts canónicos activos de un lead. Shadow-safe: [] ante cualquier fallo."""
    if not canonical_view_exists():
        log.warning("[CANONICAL_READER] %s no existe; canonical reader desactivado.", _VIEW)
        return []
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(_SELECT, {"lead_key": lead_key})
                rows = cur.fetchall()
        return [_row_to_fact(r) for r in rows]
    except Exception as exc:  # degradación segura — nunca afecta el flujo vivo
        log.warning("[CANONICAL_READER] error leyendo %s, desactivado: %s", _VIEW, exc)
        return []
