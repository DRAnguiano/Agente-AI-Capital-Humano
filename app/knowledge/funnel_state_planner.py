"""Fase 2B.1 — funnel_state_planner (PURO, sin DB / sin LLM / sin red).

Calcula el estado del funnel a partir de una lista de facts canónicos (tal como los
expone `v_rh_lead_facts_canonical`). NO lee la vista ni la BD: recibe los facts ya
construidos (el `canonical_profile_reader` de 2B.2 los proveerá). NO decide labels y NO
redacta: el LLM solo podrá redactar después con base en `next_question`.

Límites explícitos de Fase 2B.1 (ver OpenSpec design.md):
  * `license.type` y `license.status` son facts DISTINTOS. Tener `license.type` completado
    NO implica licencia vigente — 2B.1 solo evalúa el tipo.
  * `medical.apto_status` (estado del apto) y la VIGENCIA del apto son cosas distintas.
    NO se infiere vigencia si el fact no existe explícitamente.
"""
from __future__ import annotations

from dataclasses import dataclass, field as dc_field
from typing import Any

# ── Estados (decididos en Fase 2A/2B) ────────────────────────────────────────
SAFE_STATES = {"ok", "mapped_to_proof", "mapped_from_document_group"}
# No seguros: needs_review, legacy_needs_clarification, review_availability_candidate,
# separate_delivery_state (informativo, NO documento probado).

# ── Campos núcleo: orden base + pregunta canónica (DATOS, no if/else) ─────────
# El LLM NO decide estas preguntas; el planner las fija.
CORE_FIELDS: list[tuple[str, str]] = [
    ("license.type",                    "¿Qué tipo de licencia federal tiene?"),
    ("medical.apto_status",             "¿Su apto médico está vigente?"),
    ("documents.proof",                 "¿Cuenta con cartas laborales o semanas del IMSS?"),
    ("candidate.city",                  "¿Desde qué ciudad o estado nos escribe?"),
    ("experience.vehicle_type",         "¿Maneja full o sencillo?"),
    ("experience.years",                "¿Cuántos años tiene manejando?"),
    ("candidate.availability_to_attend", "¿Cuándo tiene disponibilidad para acudir al proceso?"),
]
_QUESTION = dict(CORE_FIELDS)
_ORDER = [f for f, _ in CORE_FIELDS]

# Evidencia candidata por campo: clave que la vista produce en estado de revisión.
# Nunca completa el campo núcleo; solo lo lleva a needs_confirmation.
EVIDENCE_KEY: dict[str, str] = {
    "candidate.availability_to_attend": "candidate.availability_to_attend_candidate",
}


@dataclass(frozen=True)
class CanonicalFact:
    """Fila de `v_rh_lead_facts_canonical` (el reader 2B.2 producirá estas instancias)."""
    canonical_group: str
    canonical_key: str
    canonical_value: str | None
    canonical_state: str
    canonical_unit: str | None = None
    raw_group: str | None = None
    raw_key: str | None = None
    raw_value: str | None = None
    source: str | None = None
    observed_at: str | None = None
    confidence: float | None = None
    is_active: bool = True
    lead_key: str | None = None

    @property
    def field(self) -> str:
        return f"{self.canonical_group}.{self.canonical_key}"


@dataclass
class FunnelState:
    completed_fields: dict[str, dict[str, Any]] = dc_field(default_factory=dict)
    missing_fields: list[str] = dc_field(default_factory=list)
    forbidden_questions: list[str] = dc_field(default_factory=list)
    needs_confirmation_fields: list[str] = dc_field(default_factory=list)
    conflict_fields: list[str] = dc_field(default_factory=list)
    next_question_field: str | None = None
    next_question_text: str | None = None
    next_question_reason: str | None = None
    profile_ready: bool = False


def _audit(f: CanonicalFact) -> dict[str, Any]:
    return {
        "value": f.canonical_value,
        "state": f.canonical_state,
        "raw_group": f.raw_group,
        "raw_key": f.raw_key,
        "raw_value": f.raw_value,
        "source": f.source,
        "observed_at": f.observed_at,
        "confidence": f.confidence,
    }


def compute_funnel_state(facts: list[CanonicalFact]) -> FunnelState:
    """Estado del funnel a partir de facts canónicos. Función pura."""
    active = [f for f in facts if f.is_active]
    by_field: dict[str, list[CanonicalFact]] = {}
    for f in active:
        by_field.setdefault(f.field, []).append(f)

    st = FunnelState()
    reason_map: dict[str, str] = {}

    for core in _ORDER:
        ff = by_field.get(core, [])
        safe_valued = [f for f in ff if f.canonical_value is not None and f.canonical_state in SAFE_STATES]
        unsafe = [f for f in ff if f.canonical_state not in SAFE_STATES]

        if safe_valued:
            distinct = {f.canonical_value for f in safe_valued}
            if len(distinct) > 1:
                # Conflicto (p. ej. medical.apto_status vigente vs document pending_update).
                # NO se resuelve, NO se elige ganador.
                st.conflict_fields.append(core)
                st.needs_confirmation_fields.append(core)
                reason_map[core] = "conflict"
            else:
                chosen = max(safe_valued, key=lambda f: f.confidence or 0.0)
                st.completed_fields[core] = _audit(chosen)
                st.forbidden_questions.append(core)  # no repreguntar
        elif unsafe:
            reason = unsafe[0].canonical_state
            reason_map[core] = reason
            if reason == "legacy_needs_clarification":
                st.missing_fields.append(core)          # p. ej. vehicle_type=quinta_rueda
            else:
                st.needs_confirmation_fields.append(core)  # needs_review, etc.
        else:
            # Sin fact del campo: ¿hay evidencia candidata (p. ej. availability)?
            ev = EVIDENCE_KEY.get(core)
            if ev and ev in by_field:
                st.needs_confirmation_fields.append(core)
                reason_map[core] = "review_availability_candidate"
            else:
                st.missing_fields.append(core)
                reason_map[core] = "missing"

    # ── next_question por prioridad: conflict > needs_confirmation > missing ──
    nq_field = _select_next(st)
    if nq_field is not None:
        st.next_question_field = nq_field
        st.next_question_text = _QUESTION[nq_field]
        st.next_question_reason = reason_map.get(nq_field, "missing")
    else:
        st.profile_ready = True

    return st


def _select_next(st: FunnelState) -> str | None:
    for core in _ORDER:
        if core in st.conflict_fields:
            return core
    for core in _ORDER:
        if core in st.needs_confirmation_fields:
            return core
    for core in _ORDER:
        if core in st.missing_fields:
            return core
    return None
