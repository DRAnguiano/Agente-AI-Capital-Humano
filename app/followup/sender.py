"""Sender: despacha tareas pendientes dentro de la ventana operativa."""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

import httpx

from app.db import get_conn
from app.followup.templates import get_template, render_template
from app.followup.ventana import dentro_de_ventana

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Chatwoot helpers
# ---------------------------------------------------------------------------

def _chatwoot_headers() -> dict[str, str]:
    return {
        "api_access_token": os.getenv("CHATWOOT_API_TOKEN", "").strip(),
        "Content-Type": "application/json",
    }


def _base_url() -> str:
    return os.getenv("CHATWOOT_BASE_URL", "").strip().rstrip("/")


async def _enviar_mensaje(account_id: str, conversation_id: str, content: str) -> dict:
    url = f"{_base_url()}/api/v1/accounts/{account_id}/conversations/{conversation_id}/messages"
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(
            url,
            headers=_chatwoot_headers(),
            json={"content": content, "message_type": "outgoing", "private": False},
        )
        r.raise_for_status()
        return r.json()


async def _enviar_nota_privada(account_id: str, conversation_id: str, content: str) -> dict:
    url = f"{_base_url()}/api/v1/accounts/{account_id}/conversations/{conversation_id}/messages"
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(
            url,
            headers=_chatwoot_headers(),
            json={"content": content, "message_type": "outgoing", "private": True},
        )
        r.raise_for_status()
        return r.json()


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def _ids_chatwoot(lead_key: str) -> tuple[str | None, str | None]:
    """Devuelve (account_id, conversation_id) para el lead desde rh_lead_conversations_v2."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT chatwoot_account_id, chatwoot_conversation_id
                FROM rh_lead_conversations_v2
                WHERE lead_key = %(lead_key)s
                  AND chatwoot_conversation_id IS NOT NULL
                  AND chatwoot_account_id IS NOT NULL
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                {"lead_key": lead_key},
            )
            row = cur.fetchone()
    if not row:
        return None, None
    return str(row["chatwoot_account_id"]), str(row["chatwoot_conversation_id"])


def _marcar_tarea(task_id: int, estado: str, motivo: str | None = None) -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE rh_seguimiento_tareas
                SET estado = %(estado)s,
                    enviado_en  = CASE WHEN %(estado)s = 'enviado' THEN now() ELSE enviado_en END,
                    motivo_omision = %(motivo)s,
                    updated_at  = now()
                WHERE id = %(id)s
                """,
                {"estado": estado, "motivo": motivo, "id": task_id},
            )


def _marcar_lead_perdido(lead_key: str) -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE rh_leads_v2 SET lead_status = 'lost', updated_at = now() WHERE lead_key = %s",
                (lead_key,),
            )
    log.info("[SENDER] Lead marcado como perdido: %s", lead_key)


# ---------------------------------------------------------------------------
# Runner principal
# ---------------------------------------------------------------------------

def run_sender() -> dict[str, Any]:
    """Procesa tareas pendientes que ya vencieron.

    Respeta la ventana operativa lunes–sábado 08:30–20:30.
    """
    if not dentro_de_ventana():
        return {"estado": "fuera_de_ventana", "enviados": 0, "omitidos": 0}

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    t.id, t.lead_key, t.tipo, t.intento, t.max_intentos,
                    t.clave_plantilla, t.variables,
                    l.display_name, l.phone, l.funnel_stage
                FROM rh_seguimiento_tareas t
                JOIN rh_leads_v2 l ON l.lead_key = t.lead_key
                WHERE t.estado = 'pendiente'
                  AND t.programado_para <= now()
                  AND l.lead_status NOT IN ('lost', 'closed')
                ORDER BY t.programado_para ASC
                LIMIT 50
                """
            )
            tareas = cur.fetchall()

    enviados: list[dict] = []
    omitidos: list[dict] = []

    for tarea in tareas:
        task_id    = tarea["id"]
        lead_key   = tarea["lead_key"]
        tipo       = tarea["tipo"]
        intento    = tarea["intento"]
        max_int    = tarea["max_intentos"]
        variables  = tarea["variables"] or {}

        account_id, conversation_id = _ids_chatwoot(lead_key)
        if not account_id or not conversation_id:
            _marcar_tarea(task_id, "omitido", "sin_ids_chatwoot")
            omitidos.append({"task_id": task_id, "motivo": "sin_ids_chatwoot"})
            continue

        etapa   = variables.get("etapa") or tarea.get("funnel_stage") or "followup_pending"
        nombre  = variables.get("nombre") or tarea.get("display_name") or "candidato"
        campo   = variables.get("campo_faltante")

        plantilla = get_template(etapa, intento)
        if not plantilla:
            _marcar_tarea(task_id, "omitido", "sin_plantilla")
            omitidos.append({"task_id": task_id, "motivo": "sin_plantilla"})
            continue

        mensaje = render_template(plantilla, nombre=nombre, campo_faltante=campo)

        try:
            if tipo == "nota_interna":
                asyncio.run(_enviar_nota_privada(account_id, conversation_id, mensaje))
            else:
                asyncio.run(_enviar_mensaje(account_id, conversation_id, mensaje))

            _marcar_tarea(task_id, "enviado")
            enviados.append({"task_id": task_id, "lead_key": lead_key, "tipo": tipo})
            log.info("[SENDER] Enviado task_id=%d lead=%s tipo=%s intento=%d", task_id, lead_key, tipo, intento)

            # Si se agotaron los intentos → marcar lead como perdido
            if tipo == "mensaje_seguimiento" and intento >= max_int:
                _marcar_lead_perdido(lead_key)

        except Exception as exc:
            motivo = str(exc)[:300]
            log.error("[SENDER] Error task_id=%d lead=%s: %s", task_id, lead_key, motivo)
            _marcar_tarea(task_id, "omitido", motivo)
            omitidos.append({"task_id": task_id, "motivo": motivo})

    return {
        "estado": "ok",
        "enviados": len(enviados),
        "omitidos": len(omitidos),
        "detalle": enviados,
    }
