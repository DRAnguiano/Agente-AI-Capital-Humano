"""Tareas Celery para el sistema de seguimiento y temperatura."""
from __future__ import annotations

import logging
from typing import Any

from app.celery_app import celery_app

log = logging.getLogger(__name__)


@celery_app.task(name="seguimiento.programar_tareas", bind=True, max_retries=2)
def programar_tareas(self) -> dict[str, Any]:
    """Detecta leads fríos y crea tareas de seguimiento pendientes."""
    try:
        from app.followup.scheduler import run_scheduler
        resultado = run_scheduler()
        log.info("[BEAT_SCHEDULER] creadas=%d omitidas=%d",
                 resultado.get("creadas", 0), resultado.get("omitidas", 0))
        return resultado
    except Exception as exc:
        log.error("[BEAT_SCHEDULER] Error: %s", exc)
        raise self.retry(exc=exc, countdown=120)


@celery_app.task(name="seguimiento.enviar_pendientes", bind=True, max_retries=2)
def enviar_pendientes(self) -> dict[str, Any]:
    """Despacha tareas pendientes dentro de la ventana operativa."""
    try:
        from app.followup.sender import run_sender
        resultado = run_sender()
        log.info("[BEAT_SENDER] estado=%s enviados=%d omitidos=%d",
                 resultado.get("estado"), resultado.get("enviados", 0), resultado.get("omitidos", 0))
        return resultado
    except Exception as exc:
        log.error("[BEAT_SENDER] Error: %s", exc)
        raise self.retry(exc=exc, countdown=60)
