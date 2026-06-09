"""Scheduler: detecta leads fríos y crea tareas de seguimiento."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from psycopg.types.json import Jsonb

from app.db import get_conn
from app.followup.ventana import proxima_ventana
from app.followup.templates import get_template

log = logging.getLogger(__name__)

MAX_INTENTOS = 3

# Días mínimos entre un intento y el siguiente
_ESPERA_ENTRE_INTENTOS: dict[int, int] = {
    1: 2,   # al menos 2 días entre intento 1 y 2
    2: 3,   # al menos 3 días entre intento 2 y 3
    3: 7,   # sin intento 4, pero si se creara necesitaría 7 días
}

# Etapas que usan flujo de llamada en lugar de seguimiento normal
_ETAPAS_LLAMADA = frozenset({"profile_ready", "human_review"})

# Etapas que no generan seguimientos automáticos
_ETAPAS_EXCLUIDAS = frozenset({"lost", "closed", "safety_review"})


def _suficiente_espera(ultimo_enviado_en: datetime | None, intento_siguiente: int) -> bool:
    if not ultimo_enviado_en:
        return True
    if ultimo_enviado_en.tzinfo is None:
        ultimo_enviado_en = ultimo_enviado_en.replace(tzinfo=timezone.utc)
    dias_minimos = _ESPERA_ENTRE_INTENTOS.get(intento_siguiente - 1, 3)
    return (datetime.now(timezone.utc) - ultimo_enviado_en).days >= dias_minimos


def _campo_faltante_para_lead(lead_key: str, conn) -> str | None:
    """Lee el primer campo faltante del perfil desde los facts activos."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT fact_group || '.' || fact_key AS clave
            FROM rh_lead_facts_v2
            WHERE lead_key = %(lead_key)s AND is_active = true
            """,
            {"lead_key": lead_key},
        )
        rows = cur.fetchall()
    active = {r["clave"] for r in rows}

    orden = [
        ("candidate.city",             "ciudad"),
        ("license.category",           "tipo de licencia"),
        ("license.status",             "vigencia de licencia"),
        ("medical.apto_status",        "apto médico"),
        ("experience.vehicle_type",    "tipo de unidad: tracto full o sencillo"),
        ("documents.labor_letters_status", "cartas laborales"),
    ]
    for clave, label in orden:
        if clave not in active:
            return label
    return None


def _crear_tarea(
    *,
    lead_key: str,
    tipo: str,
    clave_plantilla: str,
    variables: dict[str, Any],
    intento: int,
    conn,
) -> bool:
    """Inserta tarea respetando el índice único (un pendiente por lead+tipo).
    Devuelve True si se creó, False si ya existía."""
    programado = proxima_ventana()
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO rh_seguimiento_tareas
                (lead_key, tipo, estado, intento, max_intentos,
                 clave_plantilla, variables, programado_para)
            VALUES
                (%(lead_key)s, %(tipo)s, 'pendiente', %(intento)s, %(max_intentos)s,
                 %(clave_plantilla)s, %(variables)s, %(programado_para)s)
            ON CONFLICT (lead_key, tipo) WHERE estado = 'pendiente'
            DO NOTHING
            RETURNING id
            """,
            {
                "lead_key": lead_key,
                "tipo": tipo,
                "intento": intento,
                "max_intentos": MAX_INTENTOS,
                "clave_plantilla": clave_plantilla,
                "variables": Jsonb(variables),
                "programado_para": programado,
            },
        )
        row = cur.fetchone()
    return row is not None


def run_scheduler() -> dict[str, Any]:
    """Lee v_temperatura_leads y crea tareas para leads enfriando/fríos.

    Devuelve resumen de tareas creadas y omitidas.
    Si ocurre un error (vista caída, migración pendiente, permiso revocado),
    loggea el error y devuelve un dict vacío en lugar de propagar la excepción.
    """
    creadas: list[dict] = []
    omitidas: list[dict] = []
    try:
        return _run_scheduler_inner(creadas, omitidas)
    except Exception as exc:
        log.error("[SCHEDULER] run_scheduler falló — revisar v_temperatura_leads: %s", exc)
        return {
            "creadas": 0,
            "omitidas": 0,
            "error": str(exc)[:200],
            "detalle_creadas": [],
            "detalle_omitidas": [],
        }


def _run_scheduler_inner(creadas: list[dict], omitidas: list[dict]) -> dict[str, Any]:

    with get_conn() as conn:
        # --- Leads en cooling / cold (seguimiento normal) ---
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    lead_key, display_name, phone, funnel_stage,
                    temperatura, horas_inactivo,
                    seguimientos_enviados, ultimo_seguimiento_en
                FROM v_temperatura_leads
                WHERE temperatura IN ('enfriando', 'frio')
                  AND funnel_stage NOT IN (
                      'lost', 'closed', 'safety_review',
                      'profile_ready', 'human_review'
                  )
                  AND seguimientos_enviados < %(max_intentos)s
                ORDER BY horas_inactivo DESC
                """,
                {"max_intentos": MAX_INTENTOS},
            )
            leads = cur.fetchall()

        for lead in leads:
            lead_key = lead["lead_key"]
            etapa = lead["funnel_stage"] or "followup_pending"
            intento = int(lead["seguimientos_enviados"] or 0) + 1
            ultimo_en = lead["ultimo_seguimiento_en"]

            if not _suficiente_espera(ultimo_en, intento):
                omitidas.append({"lead_key": lead_key, "motivo": "espera_minima_no_cumplida"})
                continue

            if not get_template(etapa, intento):
                omitidas.append({"lead_key": lead_key, "motivo": "sin_plantilla"})
                continue

            campo = None
            if etapa == "profile_hint_collected":
                campo = _campo_faltante_para_lead(lead_key, conn)

            variables = {
                "nombre": lead["display_name"] or "candidato",
                "campo_faltante": campo,
                "etapa": etapa,
            }

            creada = _crear_tarea(
                lead_key=lead_key,
                tipo="mensaje_seguimiento",
                clave_plantilla=f"{etapa}_intento_{intento}",
                variables=variables,
                intento=intento,
                conn=conn,
            )

            if creada:
                creadas.append({"lead_key": lead_key, "etapa": etapa, "intento": intento})
                log.info("[SCHEDULER] Tarea creada lead=%s etapa=%s intento=%d", lead_key, etapa, intento)
            else:
                omitidas.append({"lead_key": lead_key, "motivo": "tarea_pendiente_ya_existe"})

        # --- Leads en profile_ready / human_review → solicitud de llamada ---
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT lead_key, display_name, phone, funnel_stage, horas_inactivo
                FROM v_temperatura_leads
                WHERE funnel_stage IN ('profile_ready', 'human_review')
                  AND horas_inactivo > 24
                  AND NOT EXISTS (
                      SELECT 1 FROM rh_seguimiento_tareas t
                      WHERE t.lead_key = v_temperatura_leads.lead_key
                        AND t.tipo = 'solicitud_llamada'
                        AND t.estado IN ('pendiente', 'enviado')
                  )
                """
            )
            leads_avanzados = cur.fetchall()

        for lead in leads_avanzados:
            lead_key = lead["lead_key"]
            etapa = lead["funnel_stage"]
            variables = {
                "nombre": lead["display_name"] or "candidato",
                "etapa": etapa,
            }
            creada = _crear_tarea(
                lead_key=lead_key,
                tipo="solicitud_llamada",
                clave_plantilla=f"{etapa}_llamada",
                variables=variables,
                intento=1,
                conn=conn,
            )
            if creada:
                creadas.append({"lead_key": lead_key, "etapa": etapa, "tipo": "solicitud_llamada"})
                log.info("[SCHEDULER] Solicitud de llamada creada lead=%s etapa=%s", lead_key, etapa)
            else:
                omitidas.append({"lead_key": lead_key, "motivo": "solicitud_llamada_ya_existe"})

    return {
        "creadas": len(creadas),
        "omitidas": len(omitidas),
        "detalle_creadas": creadas,
        "detalle_omitidas": omitidas,
        "error": None,
    }
