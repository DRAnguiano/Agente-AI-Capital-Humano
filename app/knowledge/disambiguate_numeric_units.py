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


# Vocabulario de unidad U (tokens normalizados, alineado con profile_extractor).
# Para campos cuya unidad esperada es "years", una unidad subanual o una expresión
# fraccional contradice el campo y NO debe confirmarse por la sola cantidad.
_YEARS_UNITS = {"ano", "anos", "anio", "anios"}
_SUBANNUAL_UNITS = {"mes", "meses", "semana", "semanas", "dia", "dias"}
_FRACTIONAL_WORDS = {"medio", "media"}


def _first_number(tokens: list[str]) -> str | None:
    for token in tokens:
        if token.isdigit():
            return token
    return None


def disambiguate(text: str, expected: str | None) -> dict[str, Any]:
    """Resuelve una cantidad X según el contexto F y su unidad U.

    - unidad subanual/fraccional en campo de años → {"status": "needs_clarification", "reason"}
    - sin número                                   → {"status": "no_number"}
    - número + contexto conocido                   → {"status": "confirmed", "field", "value", "unit"}
    - número sin contexto claro                    → {"status": "needs_clarification", "value"}
    """
    tokens = normalize_text(text or "").split()
    mapping = _CONTEXT_FIELD.get(expected or "")

    # Unidad U: solo para campos cuya unidad esperada es "years" (no aplica a age, etc.).
    if mapping and mapping.get("unit") == "years":
        token_set = set(tokens)
        if token_set & _SUBANNUAL_UNITS:
            return {"status": "needs_clarification", "reason": "subannual_unit"}
        if token_set & _FRACTIONAL_WORDS:
            return {"status": "needs_clarification", "reason": "fractional_unit"}

    num = _first_number(tokens)
    if num is None:
        return {"status": "no_number"}

    if mapping:
        return {
            "status": "confirmed",
            "field": mapping["field"],
            "value": int(num),
            "unit": mapping["unit"],
        }

    # Número sin contexto claro: no se guarda como experiencia/edad/etc.
    return {"status": "needs_clarification", "value": num}
