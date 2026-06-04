"""Etapa: clasificación contextual de respuestas cortas / sí-no / elípticas (Fase 1A).

Interpreta respuestas como `sí`, `no`, `full`, `B` usando `last_bot_question` (el campo
que el bot estaba preguntando) + estado del funnel. NO usa regex global de sí/no y SOLO
persiste si se sabe exactamente qué campo se estaba preguntando.

- Si el campo esperado es de unidad → delega al catálogo de dominio (`normalize_vehicle`).
- Si es sí/no → resuelve la polaridad y la traduce al valor del campo (mapa de DATOS).
- Sin campo esperado → no_context (no persiste).
"""
from __future__ import annotations

from typing import Any

from app.knowledge.text_normalizer import normalize_text
from app.knowledge.normalize_domain_values import normalize_vehicle

# Conjuntos de polaridad (DATOS, no regex). Texto ya normalizado (sin acentos/minúsculas).
_AFFIRMATIVE = {"si", "sip", "claro", "correcto", "afirmativo", "asi es", "sii", "simon"}
_NEGATIVE = {"no", "nel", "negativo", "para nada", "nop"}

# Traducción declarativa (campo, polaridad) → valor canónico. DATOS.
_POLARITY_VALUE: dict[str, dict[str, str]] = {
    "medical.apto_status": {"affirmative": "vigente", "negative": "vencido"},
    "license.status": {"affirmative": "vigente", "negative": "vencida"},
    "documents.proof": {"affirmative": "cartas", "negative": "ninguno"},
}


def _polarity(text: str) -> str | None:
    norm = normalize_text(text or "")
    if not norm:
        return None
    if norm in _AFFIRMATIVE or any(tok in _AFFIRMATIVE for tok in norm.split()):
        return "affirmative"
    if norm in _NEGATIVE or any(tok in _NEGATIVE for tok in norm.split()):
        return "negative"
    return None


def classify_short_answer(text: str, expected_field: str | None) -> dict[str, Any]:
    """Interpreta una respuesta corta según el campo que el bot preguntó.

    - expected_field None → {"status": "no_context"} (no se persiste).
    - campo de unidad     → delega al catálogo (full/sencillo confirmados; resto aclaración).
    - sí/no               → polaridad → valor del campo (si hay mapeo).
    """
    if not expected_field:
        return {"status": "no_context"}

    # Campo de unidad → catálogo de dominio (full/sencillo confirmados, resto aclaración).
    if expected_field == "experience.vehicle_type":
        res = normalize_vehicle(text)
        if res and res.value:
            return {"status": "confirmed", "field": "experience.vehicle_type", "value": res.value}
        if res:
            return {"status": res.status, "field": "experience.vehicle_type"}
        return {"status": "needs_clarification", "field": "experience.vehicle_type"}

    # Sí / No contextual
    pol = _polarity(text)
    if pol is None:
        return {"status": "needs_clarification", "field": expected_field}

    mapping = _POLARITY_VALUE.get(expected_field)
    if mapping and pol in mapping:
        return {"status": "confirmed", "field": expected_field, "value": mapping[pol], "polarity": pol}

    # Polaridad clara pero sin valor mapeado para el campo: devuelve la polaridad.
    return {"status": "confirmed", "field": expected_field, "polarity": pol}
