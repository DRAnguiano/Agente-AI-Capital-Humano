"""Horario de oficina canónico para la política de contacto/llamada (live-reply B7.2).

8:00–17:30, **lunes a viernes**, zona canónica **`America/Mexico_City`** (decisión #15).
NO confundir con `app/followup/ventana.py` (08:30–20:30 L–S, envío async de seguimientos).

Robustez (#15b): si `zoneinfo`/tzdata no está disponible, cae a un offset fijo UTC-6
(Centro de México, sin horario de verano desde 2022) en lugar de la hora *naive* del
servidor — así el check nunca depende de la zona del contenedor.
"""
from __future__ import annotations

import datetime

_TZ_NAME = "America/Mexico_City"
try:
    from zoneinfo import ZoneInfo

    _TZ: datetime.tzinfo = ZoneInfo(_TZ_NAME)
except Exception:  # pragma: no cover - entorno sin tzdata
    _TZ = datetime.timezone(datetime.timedelta(hours=-6), _TZ_NAME)

OPEN = datetime.time(8, 0)
CLOSE = datetime.time(17, 30)


def now_centro() -> datetime.datetime:
    """Hora actual en la zona canónica de oficina."""
    return datetime.datetime.now(tz=_TZ)


def is_business_hours(now: datetime.datetime | None = None) -> bool:
    """True si ``now`` (o la hora actual de México) cae en 8:00–17:30, lunes a viernes.

    Un ``now`` sin tzinfo se interpreta como hora de México (no del servidor); uno con
    tzinfo se convierte a la zona canónica antes de evaluar.
    """
    t = now or now_centro()
    if t.tzinfo is None:
        t = t.replace(tzinfo=_TZ)
    t = t.astimezone(_TZ)
    return t.weekday() < 5 and OPEN <= t.time() <= CLOSE
