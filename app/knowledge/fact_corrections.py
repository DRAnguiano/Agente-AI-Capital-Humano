"""Etapas `detect_fact_corrections` + `resolve_fact_conflicts` del pipeline
multi-intent (Fase 3, tareas 7.2–7.5).

Resuelve cómo se aplica el answer de un turno frente al fact previo en Postgres
(``prior_facts``), asignando uno de los estados de ciclo de vida del spec
``multi-intent-pipeline`` · "Estados de fact" / "Corrección y contradicción de
facts":

  confirmed             evidence válido + confianza suficiente, sin previo en conflicto
  inferred_from_context derivado de `last_bot_question` (respuesta elíptica)
  needs_confirmation    contradice un previo SIN corrección clara → no sobrescribe
  conflict              valores incompatibles sin intención de corrección → no sobrescribe
  corrected             corrección explícita confiable → sobrescribe + auditoría

Reglas que esta etapa respeta (spec "Corrección y contradicción de facts"):

- El **acto** de corrección NO se detecta por regex ni frases literales: se toma
  de la clasificación estructurada del turno (campos ``is_correction`` y
  ``certainty`` del answer, que el clasificador LLM poblará — su cableado se
  activa con la clasificación real, igual que `/classify` en 9.x). Esta etapa es
  pura: decide el estado a partir de esas señales + el estado previo.
- Antes de declarar `conflict`/`needs_confirmation` se NORMALIZAN ambos valores
  dentro del dominio del campo (caja, acentos, dígitos/palabras, unidad). Un
  mismo valor en distinta forma NO genera conflicto ni repregunta.
- Sin fact previo, un valor nuevo es `confirmed`/`inferred_from_context`.
- La corrección confirmada guarda auditoría (`previous_value`, `new_value`,
  `correction_evidence`, `source_turn_id`).

PURO: no lee/escribe Postgres ni llama al LLM. La persistencia del estado
(columna en `rh_lead_facts_v2`) y la reescritura real ocurren en el cutover de
Fase 4; aquí se produce el contrato en memoria que esa fase consume.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field as dc_field
from typing import Any

from app.knowledge.normalize_domain_values import normalize_vehicle
from app.knowledge.text_normalizer import normalize_text

FACT_STATES = frozenset(
    {"confirmed", "inferred_from_context", "needs_confirmation", "conflict", "corrected"}
)

# Campos cuyo valor es una cantidad entera (se comparan como número, no como texto).
_NUMERIC_FIELDS = frozenset({"experience.years", "candidate.age"})

# Mapa de número en palabra → entero. Espejo reducido de los mapas en
# current_turn/profile_extractor (candidato a helper único; ver docs/deuda_tecnica.md).
_NUM_WORDS = {
    "un": 1, "uno": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5,
    "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10,
}


def _normalize_numeric(value: Any) -> str | None:
    """Extrae la cantidad entera de un valor numérico de perfil.

    Acepta dígitos ("10 años" → "10") y números en palabra ("diez" → "10").
    Devuelve None si no hay cantidad reconocible (no se compara como número).
    """
    text = normalize_text(str(value or ""))
    if not text:
        return None
    m = re.search(r"\d{1,3}", text)
    if m:
        return str(int(m.group()))
    for tok in text.split():
        if tok in _NUM_WORDS:
            return str(_NUM_WORDS[tok])
    return None


def normalize_fact_value(field: str, value: Any) -> str | None:
    """Forma canónica comparable de un valor según el dominio del campo.

    Devuelve None cuando el valor no resuelve a una forma canónica del campo
    (p. ej. una unidad fuera del catálogo, o un numérico sin cantidad): en ese
    caso la etapa NO compara ni declara conflicto.
    """
    if value is None:
        return None
    if field == "experience.vehicle_type":
        res = normalize_vehicle(str(value))
        # solo full/sencillo son valores canónicos comparables; jerga ambigua no.
        return res.value if (res and res.value) else None
    if field in _NUMERIC_FIELDS:
        return _normalize_numeric(value)
    norm = normalize_text(str(value))
    return norm or None


@dataclass
class ResolvedFact:
    """Resultado de resolver un answer del turno contra el fact previo."""
    field: str
    value: Any
    state: str
    previous_value: Any = None
    correction_evidence: str | None = None
    source_turn_id: str | None = None
    confidence: float | None = None

    def to_dict(self) -> dict[str, Any]:
        d = {"field": self.field, "value": self.value, "state": self.state}
        if self.previous_value is not None:
            d["previous_value"] = self.previous_value
        if self.correction_evidence is not None:
            d["correction_evidence"] = self.correction_evidence
        if self.source_turn_id is not None:
            d["source_turn_id"] = self.source_turn_id
        if self.confidence is not None:
            d["confidence"] = self.confidence
        return d


def _resolve_one(
    answer: dict[str, Any],
    prior_facts: dict[str, Any],
    turn_id: str | None,
) -> ResolvedFact | None:
    field = answer.get("field")
    if not field:
        return None
    value = answer.get("value")
    confidence = answer.get("confidence")
    evidence = answer.get("evidence")
    is_correction = bool(answer.get("is_correction"))
    certainty = (answer.get("certainty") or "high").lower()
    from_context = bool(answer.get("from_context"))

    # Valor nuevo en forma canónica del campo. Si no resuelve (jerga ambigua como
    # "quinta rueda", o numérico sin cantidad), NO hay valor confiable: la etapa
    # NO persiste ni declara conflicto (spec: "sin un F confiable aplicable, SHALL
    # NOT persistir, SHALL NOT generar conflicto estructurado"). Lo aclara otra etapa.
    nv = normalize_fact_value(field, value)
    if nv is None:
        return None

    prior = prior_facts.get(field)

    # Sin previo: dato nuevo. inferred_from_context si vino de una respuesta elíptica.
    if not prior:
        state = "inferred_from_context" if from_context else "confirmed"
        return ResolvedFact(field=field, value=value, state=state, confidence=confidence)

    # Hay previo: normalizar dentro del dominio F antes de comparar.
    pv = normalize_fact_value(field, prior)

    # Mismo valor en distinta forma → no es conflicto, no repregunta. Se mantiene
    # confirmado sin reescribir (el valor previo ya está).
    if pv is not None and nv == pv:
        return ResolvedFact(field=field, value=prior, state="confirmed", confidence=confidence)

    # Valores realmente distintos: el acto decide el estado (no el texto).
    if certainty == "low":
        # Corrección/duda con baja certeza del candidato → no sobrescribe.
        return ResolvedFact(field=field, value=value, state="needs_confirmation",
                            previous_value=prior, confidence=confidence)
    if is_correction:
        # Corrección explícita confiable → sobrescribe + auditoría.
        return ResolvedFact(field=field, value=value, state="corrected", previous_value=prior,
                            correction_evidence=evidence, source_turn_id=turn_id,
                            confidence=confidence)
    # Contradicción sin intención clara de corrección → conflicto, no sobrescribe.
    return ResolvedFact(field=field, value=value, state="conflict", previous_value=prior,
                        confidence=confidence)


def resolve_facts(
    answers: list[dict[str, Any]],
    prior_facts: dict[str, Any] | None = None,
    *,
    turn_id: str | None = None,
) -> dict[str, Any]:
    """Resuelve los answers del turno contra los facts previos. Función pura.

    Devuelve, listo para la traza de auditoría del turno (tarea 8.3) y para que
    la Fase 4 escriba en Postgres:
      - ``facts_to_apply``: estados que SÍ se escriben (confirmed/inferred/corrected)
      - ``facts_pending_confirmation``: needs_confirmation (no sobrescriben)
      - ``conflicts``: conflict (no sobrescriben; no cambian labels hasta resolver)
      - ``corrections``: auditoría de los facts `corrected`
      - ``resolved``: todos los ResolvedFact como dict
    """
    prior_facts = dict(prior_facts or {})
    resolved: list[ResolvedFact] = []
    for ans in answers or []:
        rf = _resolve_one(ans, prior_facts, turn_id)
        if rf is not None:
            resolved.append(rf)

    apply_states = {"confirmed", "inferred_from_context", "corrected"}
    return {
        "facts_to_apply": [r.to_dict() for r in resolved if r.state in apply_states],
        "facts_pending_confirmation": [r.to_dict() for r in resolved if r.state == "needs_confirmation"],
        "conflicts": [r.to_dict() for r in resolved if r.state == "conflict"],
        "corrections": [
            {"field": r.field, "previous_value": r.previous_value, "new_value": r.value,
             "correction_evidence": r.correction_evidence, "source_turn_id": r.source_turn_id}
            for r in resolved if r.state == "corrected"
        ],
        "resolved": [r.to_dict() for r in resolved],
    }
