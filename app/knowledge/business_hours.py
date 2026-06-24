"""Horario de oficina canónico para la política de contacto/llamada (live-reply B7.2).

8:00–17:30, **lunes a viernes**, zona canónica **`America/Mexico_City`** (decisión #15).
NO confundir con `app/followup/ventana.py` (08:30–20:30 L–S, envío async de seguimientos).

Robustez (#15b): si `zoneinfo`/tzdata no está disponible, cae a un offset fijo UTC-6
(Centro de México, sin horario de verano desde 2022) en lugar de la hora *naive* del
servidor — así el check nunca depende de la zona del contenedor.
"""
from __future__ import annotations

import datetime
import re

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


# ── Validación de ventana de llamada (B7.5) ───────────────────────────────────
# Clasifica un texto de ventana ("manana a las 3 de la tarde", "el sabado", …) contra
# el horario de oficina, SIN depender del reloj. Opera sobre texto normalizado
# (minúsculas, sin acentos). Conservadora: ante ambigüedad real (hora sin meridiano en
# rango 1–7, día hábil sin hora) devuelve "unknown" para no prometer ni descartar de más.
_WEEKEND_RE = re.compile(r"\b(?:sabado|domingo)\b")
_HOUR_RE = re.compile(r"\ba\s+las?\s+(\d{1,2})(?::\d{2})?\s*(am|pm|hrs|horas)?\b")
_MORNING_RE = re.compile(r"\b(?:por|en|de)\s+la\s+manana\b")
_AFTERNOON_RE = re.compile(r"\b(?:por|en|de)\s+la\s+tarde\b")
_NIGHT_RE = re.compile(r"\b(?:por|en|de)\s+la\s+noche\b")


def classify_call_window(text: str) -> str:
    """Devuelve "true" (dentro), "false" (fuera) o "unknown" (no interpretable).

    No usa la hora actual: evalúa la ventana declarada contra 8:00–17:30, L–V.
    """
    t = (text or "").lower()
    weekend = bool(_WEEKEND_RE.search(t))

    m = _HOUR_RE.search(t)
    if m:
        hour = int(m.group(1))
        meridiem = m.group(2)
        pm_ctx = bool(_AFTERNOON_RE.search(t) or _NIGHT_RE.search(t))
        am_ctx = bool(_MORNING_RE.search(t))
        if meridiem == "pm" or (pm_ctx and not am_ctx):
            if hour < 12:
                hour += 12
        elif meridiem == "am" or am_ctx:
            if hour == 12:
                hour = 0
        elif 1 <= hour <= 7:
            # sin meridiano ni contexto: 4 → 4am vs 4pm → no interpretable
            return "unknown"
        # 8–12 sin contexto se asume mañana de oficina; 13–23 ya es 24h
        if hour > 23:
            return "unknown"
        if weekend:
            return "false"
        return "true" if OPEN.hour <= hour <= CLOSE.hour else "false"

    # sin hora explícita
    if weekend or _NIGHT_RE.search(t):
        return "false"
    if _MORNING_RE.search(t):
        return "true"
    # tarde sin hora (cruza 17:30), día hábil sin hora, "manana" (día) → no interpretable
    return "unknown"
