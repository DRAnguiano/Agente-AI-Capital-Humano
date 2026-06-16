"""Etapa `memory_guard` del pipeline multi-intent (Fase 3, tarea 6).

Se ejecuta ANTES de proponer cualquier pregunta del funnel. Tiene dos trabajos:

1. **forbidden_questions**: a partir de los facts ya conocidos del lead
   (``known_facts`` = snapshot de ``lead_memory``; la Fase 4 los leerá de
   Postgres), deriva qué campos del funnel NO deben volver a preguntarse porque
   ya tienen un valor. El orquestador los salta al elegir la siguiente pregunta.

2. **memory_claim**: detecta un *reclamo de memoria* ("ya te había dicho que
   full") y lo resuelve contra el fact canónico previo en uno de tres casos
   (spec ``multi-intent-pipeline`` · "Conversation memory guard"):
     - ``reaffirm``         → el fact previo coincide: reafirmar, no reescribir,
                              no repetir la pregunta.
     - ``process_as_fact``  → no hay fact previo: dejar que el valor explícito
                              del turno fluya por el pipeline normal de facts
                              (no perder el dato).
     - ``conflict``         → el fact previo difiere: registrar conflicto, NO
                              sobrescribir, pedir confirmación neutral.

  Distinto de la corrección explícita (tarea 7.4), que sí sobrescribe con
  auditoría.

PURO: no lee BD, no llama al LLM, no muta la entrada. Recibe ``known_facts``
(memoria previa al turno) y la clasificación enriquecida del turno.
"""
from __future__ import annotations

import re
from typing import Any

from app.knowledge.text_normalizer import normalize_text

# Campos del funnel (mismos ids que `intent_orchestrator.FUNNEL_STEPS`) y las
# claves de fact que dan el campo por respondido. Espejo deliberado: si cambian
# los pasos del funnel, este mapa debe seguirlos (lo blinda test_memory_guard).
FUNNEL_FIELD_FACT_KEYS: dict[str, tuple[str, ...]] = {
    "candidate.city":          ("candidate.city",),
    "experience.vehicle_type": ("experience.vehicle_type",),
    "license":                 ("license.type", "license.status"),
    "medical.apto_status":     ("medical.apto_status",),
    "experience.years":        ("experience.years",),
    "documents.proof":         ("documents.proof",),
}

# Frases (sobre texto normalizado, sin acentos) que marcan un reclamo de memoria:
# el candidato afirma haber dado ya un dato. NO incluye la corrección explícita
# ("me equivoque", "son 10 no 5"), que es la tarea 7.4.
_MEMORY_CLAIM_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bya\s+(?:te|le|les|se\s+lo)\s+(?:habia\s+)?dij[eo]\b"),
    re.compile(r"\bya\s+(?:lo\s+)?(?:habia\s+)?dije\b"),
    re.compile(r"\bya\s+(?:te|le)\s+habia\s+dicho\b"),
    re.compile(r"\b(?:como|si)\s+(?:te|le)\s+(?:habia\s+)?dij[eo]\b"),
    re.compile(r"\bya\s+habia\s+dicho\b"),
    re.compile(r"\bya\s+(?:le|te)\s+comente\b"),
)


def _is_memory_claim(message: str) -> bool:
    """True si el mensaje contiene una frase de reclamo de memoria."""
    norm = normalize_text(message or "")
    return any(p.search(norm) for p in _MEMORY_CLAIM_PATTERNS)


def derive_forbidden_questions(known_facts: dict[str, Any]) -> list[str]:
    """Campos del funnel ya respondidos en la memoria previa.

    Spec "Campo ya respondido": si un campo ya tiene fact con valor, entra en
    forbidden_questions y NO se vuelve a preguntar. Presence-based contra
    ``known_facts`` (memoria previa al turno), preservando el orden del funnel.
    """
    forbidden: list[str] = []
    for funnel_field, fact_keys in FUNNEL_FIELD_FACT_KEYS.items():
        if any(known_facts.get(k) for k in fact_keys):
            forbidden.append(funnel_field)
    return forbidden


def _claimed_answer(enriched: dict[str, Any]) -> dict[str, Any] | None:
    """El answer núcleo del turno (campo+valor) sobre el que recae el reclamo.

    Se apoya en lo que el clasificador ya extrajo y el enricher dejó persistible
    (evidence_ok + confianza). El memory_guard NO re-extrae del texto: si el
    turno no trae un answer núcleo, no hay nada que reafirmar/comparar.
    """
    for ans in enriched.get("answers_to_persist") or []:
        field = ans.get("field")
        if field in FUNNEL_FIELD_FACT_KEYS or field == "experience.vehicle_type":
            return ans
    return None


def apply_memory_guard(
    enriched: dict[str, Any],
    message: str,
    known_facts: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Resultado de la etapa memory_guard. Función pura.

    Devuelve:
      - ``forbidden_questions``: campos del funnel ya respondidos en memoria.
      - ``memory_claim``: ``None`` o ``{field, value, resolution}`` con
        resolution en ``reaffirm`` | ``process_as_fact`` | ``conflict``.
    """
    known_facts = dict(known_facts or {})
    forbidden = derive_forbidden_questions(known_facts)

    memory_claim: dict[str, Any] | None = None
    if _is_memory_claim(message):
        ans = _claimed_answer(enriched)
        if ans is not None:
            field = ans["field"]
            value = ans.get("value")
            prior = known_facts.get(field)
            if not prior:
                # (2) Sin fact previo → procesar como dato normal (no perderlo).
                resolution = "process_as_fact"
            elif str(prior) == str(value):
                # (1) Coincide → reafirmar, no repreguntar, no reescribir.
                resolution = "reaffirm"
                if field not in forbidden:
                    forbidden.append(field)
            else:
                # (3) Difiere → conflicto: no sobrescribir, confirmación neutral.
                resolution = "conflict"
            memory_claim = {"field": field, "value": value, "resolution": resolution}

    return {"forbidden_questions": forbidden, "memory_claim": memory_claim}
