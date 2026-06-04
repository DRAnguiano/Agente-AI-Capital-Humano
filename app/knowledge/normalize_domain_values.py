"""Etapa: normalización de valores claros del dominio (Fase 1A).

Resuelve un término de unidad dicho por el candidato contra el catálogo de dominio
(`domain_catalog`). NO usa regex de negocio: hace lookup de datos sobre texto normalizado.

- `full`/`sencillo`                       → vehicle_type confirmado.
- `quinta rueda`/`tráiler`/`tractocamión` → needs_clarification (NO fija vehicle_type).
- `camión`                                → needs_clarification + ambiguous.
- `torton`/`rabón`/`reparto`/`local`/`camioneta` → non_target.

El LLM clasificador entiende el lenguaje (incl. faltas de ortografía); esta etapa solo
valida/normaliza el término contra el catálogo. Aislada: no toca Postgres ni Chatwoot.
"""
from __future__ import annotations

from app.knowledge.text_normalizer import normalize_text
from app.knowledge.domain_catalog import VEHICLE_TERMS, VehicleResolution

# Claves ordenadas por longitud desc: "camioneta" antes que "camion",
# "quinta rueda" antes que cualquier palabra suelta. Evita falsos positivos por substring.
_TERMS_BY_LEN = sorted(VEHICLE_TERMS.items(), key=lambda kv: len(kv[0]), reverse=True)


def normalize_vehicle(text: str) -> VehicleResolution | None:
    """Devuelve la resolución del primer término de unidad presente, o None si no hay.

    None significa "el texto no contiene un término de unidad conocido" — el clasificador
    o el funnel decidirán; esta etapa NO inventa un valor.
    """
    norm = normalize_text(text or "")
    if not norm:
        return None
    for key, resolution in _TERMS_BY_LEN:
        if key in norm:
            return resolution
    return None


def applies_objetivo_full_sencillo(resolution: VehicleResolution | None) -> bool:
    """Regla declarativa: `objetivo_full_sencillo` SOLO si vehicle_type quedó confirmado.

    quinta rueda/tráiler/camión (needs_clarification) y torton/etc (non_target) NO aplican.
    """
    return bool(resolution and resolution.value is not None and resolution.status == "confirmed")
