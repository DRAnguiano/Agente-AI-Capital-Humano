"""Etapa: desambiguación de números/cantidades (Fase 1A).

Un número aislado NO se interpreta solo: su significado depende de la última pregunta del
bot (`last_bot_question`) y del estado del funnel. Sin contexto claro, NO se persiste.

No usa regex de negocio: tokeniza por espacios y reconoce dígitos con `str.isdigit()`
(extracción simple, no decisión de negocio). El mapeo contexto→campo es DATOS.
"""
from __future__ import annotations

from typing import Any

from app.knowledge.text_normalizer import normalize_text

# Contextos esperados (lo que la última pregunta del bot estaba pidiendo).
EXPERIENCE_YEARS_CONTEXT = "experience_years"
AGE_CONTEXT = "age"

# Mapeo declarativo contexto → (campo canónico, unidad). DATOS, no if/else disperso.
_CONTEXT_FIELD: dict[str, dict[str, Any]] = {
    EXPERIENCE_YEARS_CONTEXT: {"field": "experience.years", "unit": "years"},
    AGE_CONTEXT: {"field": "candidate.age", "unit": None},
}


def _first_number(text: str) -> str | None:
    for token in normalize_text(text or "").split():
        if token.isdigit():
            return token
    return None


def disambiguate(text: str, expected: str | None) -> dict[str, Any]:
    """Resuelve un número según el contexto esperado.

    - sin número            → {"status": "no_number"}
    - número + contexto conocido → {"status": "confirmed", "field", "value", "unit"}
    - número sin contexto claro  → {"status": "needs_clarification", "value"} (NO se guarda)
    """
    num = _first_number(text)
    if num is None:
        return {"status": "no_number"}

    mapping = _CONTEXT_FIELD.get(expected or "")
    if mapping:
        return {
            "status": "confirmed",
            "field": mapping["field"],
            "value": int(num),
            "unit": mapping["unit"],
        }

    # Número sin contexto claro: no se guarda como experiencia/edad/etc.
    return {"status": "needs_clarification", "value": num}
