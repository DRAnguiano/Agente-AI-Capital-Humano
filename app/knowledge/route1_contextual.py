"""Route-1 contextual resolver (G2, Fase A shadow).

Interpreta una respuesta corta del candidato usando el campo canónico que el
funnel preguntó en el turno previo (fresh canonical keys, leídas por el
integrador vía ``read_current_asked_field_keys``). Puro, delgado, SIN BD y SIN
writes: devuelve qué *haría* route-1, nunca persiste.

Fase A = log-only. No reemplaza el path textual vivo ni el current_turn guard
(`guard_context` en ``tasks_chatwoot``, debounce ON), que se reconcilian en
Fase B. Alcance v1: solo ``experience.years``, ``experience.vehicle_type`` y
``documents.proof``. v1 conservador: negación → no_persist.
"""
from __future__ import annotations

from typing import Any

from app.knowledge.text_normalizer import normalize_text
from app.knowledge.contextual_answer_classifier import classify_short_answer

# Allowlist v1: solo campos con resolver corto confiable.
# (license.status / medical.apto_status / candidate.city / license.type quedan fuera.)
ROUTE1_ALLOWED: frozenset[str] = frozenset({
    "experience.years",
    "experience.vehicle_type",
    "documents.proof",
})

# Negación conservadora (alineada con current_turn._neg_hints). v1: negación -> no_persist.
_NEG_HINTS: frozenset[str] = frozenset({
    "no", "nel", "nop", "tampoco", "nunca",
    "vencido", "vencida", "vencio", "venció", "caducado", "caducada",
})


def _no_persist(reason: str, field: str | None = None) -> dict[str, Any]:
    return {"status": "no_persist", "field": field, "value": None, "reason": reason}


def _has_negation(text: str) -> bool:
    return any(tok in _NEG_HINTS for tok in normalize_text(text or "").split())


def resolve_route1(text: str, asked_field_keys: list[str] | None) -> dict[str, Any]:
    """Resuelve la respuesta contra el campo activo (fresh canonical keys).

    Devuelve ``{"status","field","value","reason"}``. NUNCA persiste: en Fase A el
    integrador solo loguea el resultado (``[ROUTE1_SHADOW]``).

    Reasons posibles: ok | no_asked_field | multi_field | field_not_allowed |
    negation | ambiguous | no_number.
    """
    if not asked_field_keys:
        return _no_persist("no_asked_field")
    if len(asked_field_keys) != 1:
        return _no_persist("multi_field")

    expected_field = asked_field_keys[0]
    if expected_field not in ROUTE1_ALLOWED:
        return _no_persist("field_not_allowed", expected_field)

    # v1 conservador: cualquier negación bloquea la persistencia (no valores negativos aún).
    if _has_negation(text):
        return _no_persist("negation", expected_field)

    # Cantidad numérica para experience.years: extraer primer dígito del texto.
    # Desambiguación contextual real ya la maneja current_turn.py vía LLM;
    # aquí solo necesitamos el valor para el shadow log.
    if expected_field == "experience.years":
        tokens = normalize_text(text or "").split()
        token_set = set(tokens)
        subannual = {"mes", "meses", "semana", "semanas", "dia", "dias"}
        fractional = {"medio", "media"}
        if token_set & subannual or token_set & fractional:
            return _no_persist("needs_clarification", expected_field)
        num = next((t for t in tokens if t.isdigit()), None)
        if num is None:
            return _no_persist("no_number", expected_field)
        return {"status": "confirmed", "field": "experience.years",
                "value": int(num), "reason": "ok"}

    # Respuesta corta / elíptica (unidad o sí-no) → clasificador contextual.
    res = classify_short_answer(text, expected_field)
    if res.get("status") != "confirmed":
        return _no_persist("ambiguous", expected_field)

    # documents.proof: solo polaridad afirmativa confirma (negativa ya filtrada arriba).
    if expected_field == "documents.proof" and res.get("polarity") == "negative":
        return _no_persist("negation", expected_field)
    if res.get("value") is None:
        return _no_persist("ambiguous", expected_field)

    return {"status": "confirmed", "field": expected_field,
            "value": res.get("value"), "reason": "ok"}
