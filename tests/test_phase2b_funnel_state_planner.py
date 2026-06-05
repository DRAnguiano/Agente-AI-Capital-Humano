"""Fase 2B.1 — tests unitarios del funnel_state_planner (puro, sin DB/LLM).

Facts canónicos FABRICADOS (no requiere la vista aplicada).
"""
from __future__ import annotations

from app.knowledge.funnel_state_planner import CanonicalFact, compute_funnel_state


def cf(group, key, value, state, **kw) -> CanonicalFact:
    return CanonicalFact(canonical_group=group, canonical_key=key,
                         canonical_value=value, canonical_state=state, **kw)


# Facts de los 6 campos núcleo (estado seguro) para armar perfiles.
# availability_to_attend NO es campo núcleo (2C.1): no va aquí.
_COMPLETE = {
    "license.type":            cf("license", "type", "B", "ok", raw_group="license", raw_key="category", raw_value="B", confidence=0.9),
    "medical.apto_status":     cf("medical", "apto_status", "vigente", "ok"),
    "documents.proof":         cf("documents", "proof", "cartas", "mapped_to_proof", raw_key="labor_letters", raw_value="sí"),
    "candidate.city":          cf("candidate", "city", "Torreón", "ok"),
    "experience.vehicle_type": cf("experience", "vehicle_type", "full", "ok"),
    "experience.years":        cf("experience", "years", "10", "ok", canonical_unit="years"),
}


def complete_except(*skip: str) -> list[CanonicalFact]:
    return [v for k, v in _COMPLETE.items() if k not in skip]


# ── 1) licencia legacy → completed; no repreguntar ────────────────────────────
def test_license_legacy_completed():
    st = compute_funnel_state([_COMPLETE["license.type"]])
    assert "license.type" in st.completed_fields
    assert "license.type" in st.forbidden_questions
    assert st.next_question_field != "license.type"
    # auditoría completa
    aud = st.completed_fields["license.type"]
    for k in ("value", "state", "raw_group", "raw_key", "raw_value", "source", "observed_at", "confidence"):
        assert k in aud
    assert aud["value"] == "B" and aud["raw_key"] == "category"


# ── 2) documentos via proof → completed ───────────────────────────────────────
def test_documents_proof_completed():
    st = compute_funnel_state([_COMPLETE["documents.proof"]])
    assert "documents.proof" in st.completed_fields
    assert "documents.proof" in st.forbidden_questions
    assert st.completed_fields["documents.proof"]["value"] == "cartas"


# ── 3) vehicle_type legacy → missing; pregunta full/sencillo ──────────────────
def test_vehicle_type_legacy_missing_asks_full_sencillo():
    facts = complete_except("experience.vehicle_type") + [
        cf("experience", "vehicle_type", None, "legacy_needs_clarification", raw_value="quinta_rueda"),
    ]
    st = compute_funnel_state(facts)
    assert "experience.vehicle_type" in st.missing_fields
    assert "experience.vehicle_type" not in st.completed_fields
    assert st.next_question_field == "experience.vehicle_type"
    assert st.next_question_text == "¿Maneja full o sencillo?"
    assert st.next_question_reason == "legacy_needs_clarification"


# ── 4) availability_to_attend IGNORADA por el profile planner (2C.1) ──────────
def test_availability_is_ignored_by_profile_planner():
    # Con los 6 núcleo completos, un fact de availability (candidate o confirmado) NO
    # aparece en el planner ni bloquea profile_ready.
    facts = complete_except() + [
        cf("candidate", "availability_to_attend_candidate", "candidate_says_available",
           "review_availability_candidate", raw_group="documents", raw_key="availability_claim"),
        cf("candidate", "availability_to_attend", "2026-06-10", "ok"),
    ]
    st = compute_funnel_state(facts)
    assert "candidate.availability_to_attend" not in st.completed_fields
    assert "candidate.availability_to_attend" not in st.missing_fields
    assert "candidate.availability_to_attend" not in st.needs_confirmation_fields
    assert "candidate.availability_to_attend_candidate" not in st.needs_confirmation_fields
    assert st.profile_ready is True
    assert st.next_question_field is None


# ── 5) conflicto apto → conflict, no resuelve ────────────────────────────────
def test_apto_conflict_not_resolved():
    facts = complete_except("medical.apto_status") + [
        cf("medical", "apto_status", "vigente", "ok"),
        cf("medical", "apto_status", "pending_update", "mapped_from_document_group", raw_group="document"),
    ]
    st = compute_funnel_state(facts)
    assert "medical.apto_status" in st.conflict_fields
    assert "medical.apto_status" in st.needs_confirmation_fields
    assert "medical.apto_status" not in st.completed_fields
    assert st.next_question_field == "medical.apto_status"
    assert st.next_question_reason == "conflict"


# ── 6) perfil con todo menos unidad → next_question unidad ────────────────────
def test_next_question_unit_when_only_unit_missing():
    facts = complete_except("experience.vehicle_type", "experience.years")
    st = compute_funnel_state(facts)
    assert st.next_question_field == "experience.vehicle_type"


# ── 7) perfil con todo menos ciudad → next_question ciudad ───────────────────
def test_next_question_city_when_only_city_missing():
    facts = complete_except("candidate.city", "experience.years")
    st = compute_funnel_state(facts)
    assert st.next_question_field == "candidate.city"


# ── 8) perfil completo → profile_ready, sin next_question ─────────────────────
def test_profile_complete_ready():
    st = compute_funnel_state(complete_except())
    assert st.next_question_field is None
    assert st.profile_ready is True
    assert st.missing_fields == [] and st.conflict_fields == [] and st.needs_confirmation_fields == []
