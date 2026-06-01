"""Ventana de envío de mensajes: lunes–sábado, 08:30–20:30 h (Monterrey)."""
from __future__ import annotations

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

ZONA = ZoneInfo("America/Monterrey")

_INICIO = time(8, 30)
_FIN    = time(20, 30)
_APERTURA = time(9, 0)   # hora de apertura cuando se reprograma al día siguiente


def _es_dia_habil(dt: datetime) -> bool:
    """Lunes (0)–Sábado (5). Domingo (6) no es hábil."""
    return dt.weekday() != 6


def _siguiente_dia_habil(dt: datetime) -> datetime:
    sig = dt + timedelta(days=1)
    while not _es_dia_habil(sig):
        sig += timedelta(days=1)
    return sig


def proxima_ventana(desde: datetime | None = None) -> datetime:
    """Devuelve el siguiente momento válido para enviar un mensaje de seguimiento.

    - Si estamos dentro de la ventana → ahora mismo.
    - Si es muy temprano hoy → hoy a las 08:30.
    - Si ya pasó la ventana hoy o es domingo → siguiente día hábil a las 09:00.
    """
    ahora = (desde or datetime.now(ZONA)).astimezone(ZONA)

    if not _es_dia_habil(ahora):
        sig = _siguiente_dia_habil(ahora)
        return sig.replace(hour=_APERTURA.hour, minute=_APERTURA.minute,
                           second=0, microsecond=0)

    hora = ahora.time().replace(second=0, microsecond=0)

    if _INICIO <= hora <= _FIN:
        return ahora

    if hora < _INICIO:
        return ahora.replace(hour=_INICIO.hour, minute=_INICIO.minute,
                             second=0, microsecond=0)

    # Pasó la ventana → siguiente día hábil
    sig = _siguiente_dia_habil(ahora)
    return sig.replace(hour=_APERTURA.hour, minute=_APERTURA.minute,
                       second=0, microsecond=0)


def dentro_de_ventana(dt: datetime | None = None) -> bool:
    """True si el momento dado está dentro de la ventana operativa."""
    ahora = (dt or datetime.now(ZONA)).astimezone(ZONA)
    if not _es_dia_habil(ahora):
        return False
    hora = ahora.time().replace(second=0, microsecond=0)
    return _INICIO <= hora <= _FIN
