"""Tarea 7.2–7.6 — detect_fact_corrections / resolve_fact_conflicts + estados.

Cubre el contrato del spec `multi-intent-pipeline` · "Corrección y contradicción
de facts" y "Estados de fact". El acto de corrección llega como señal estructurada
del clasificador (`is_correction`/`certainty`), no por regex; aquí se prueba la
resolución pura del estado.

Deterministas: sin Groq, sin Chroma, sin DB.
"""
from __future__ import annotations

from app.knowledge.fact_corrections import (
    FACT_STATES,
    normalize_fact_value,
    resolve_facts,
)


def _ans(field, value, **kw):
    a = {"field": field, "value": value, "evidence": str(value), "confidence": 0.95}
    a.update(kw)
    return a


# ── Estados base (Scenario: Fact confirmado / inferido) ───────────────────────

def test_new_fact_without_prior_is_confirmed():
    out = resolve_facts([_ans("experience.years", "10")], prior_facts={})
    assert out["resolved"][0]["state"] == "confirmed"
    assert out["facts_to_apply"][0]["field"] == "experience.years"


def test_new_fact_from_context_is_inferred():
    out = resolve_facts([_ans("experience.years", "10", from_context=True)], prior_facts={})
    assert out["resolved"][0]["state"] == "inferred_from_context"


# ── Equivalencia tras normalizar (Scenario: mismo valor distinta forma) ───────

def test_same_value_different_form_no_conflict_numeric():
    # previo "10", nuevo "diez" → equivalentes → confirmed, sin conflicto
    out = resolve_facts([_ans("experience.years", "diez")], prior_facts={"experience.years": "10"})
    assert out["resolved"][0]["state"] == "confirmed"
    assert out["conflicts"] == []
    assert out["facts_pending_confirmation"] == []


def test_same_value_different_form_no_conflict_text():
    out = resolve_facts([_ans("candidate.city", "torreon")], prior_facts={"candidate.city": "Torreón"})
    assert out["resolved"][0]["state"] == "confirmed"
    assert out["conflicts"] == []


def test_vehicle_jargon_with_full_prior_does_not_conflict():
    # previo full; nuevo "quinta rueda" no resuelve a valor canónico → no compara/conflicto
    out = resolve_facts(
        [_ans("experience.vehicle_type", "quinta rueda")],
        prior_facts={"experience.vehicle_type": "full"},
    )
    assert out["conflicts"] == []


# ── Corrección explícita (Scenario: Corrección clara) → corrected + auditoría ─

def test_explicit_correction_overwrites_with_audit():
    out = resolve_facts(
        [_ans("experience.years", "10", is_correction=True, evidence="me equivoque son 10")],
        prior_facts={"experience.years": "9"},
        turn_id="t-42",
    )
    rf = out["resolved"][0]
    assert rf["state"] == "corrected"
    assert rf["previous_value"] == "9"
    corr = out["corrections"][0]
    assert corr == {
        "field": "experience.years", "previous_value": "9", "new_value": "10",
        "correction_evidence": "me equivoque son 10", "source_turn_id": "t-42",
    }
    # corrected SÍ se aplica (sobrescribe)
    assert any(f["field"] == "experience.years" for f in out["facts_to_apply"])


# ── Corrección con duda (Scenario: Corrección con duda) → needs_confirmation ──

def test_low_certainty_does_not_overwrite():
    # "no se creo que 10" sobre un previo 9 → needs_confirmation, no sobrescribe
    out = resolve_facts(
        [_ans("experience.years", "10", certainty="low")],
        prior_facts={"experience.years": "9"},
    )
    rf = out["resolved"][0]
    assert rf["state"] == "needs_confirmation"
    assert rf["previous_value"] == "9"
    assert out["facts_to_apply"] == []  # no sobrescribe


# ── Contradicción sin corrección (Scenario: Contradicción) → conflict ─────────

def test_contradiction_without_correction_is_conflict():
    out = resolve_facts(
        [_ans("experience.vehicle_type", "sencillo")],
        prior_facts={"experience.vehicle_type": "full"},
    )
    rf = out["resolved"][0]
    assert rf["state"] == "conflict"
    assert rf["previous_value"] == "full"
    assert out["facts_to_apply"] == []  # no cambia el valor hasta resolver


# ── 7.6: "10" sin contexto no llega como answer núcleo → no persiste ──────────

def test_no_answer_no_persist():
    out = resolve_facts([], prior_facts={})
    assert out["resolved"] == [] and out["facts_to_apply"] == []


# ── estados válidos y normalizador ────────────────────────────────────────────

def test_all_emitted_states_are_in_catalog():
    cases = [
        resolve_facts([_ans("experience.years", "10")], {}),
        resolve_facts([_ans("experience.years", "10", certainty="low")], {"experience.years": "9"}),
        resolve_facts([_ans("experience.years", "10", is_correction=True)], {"experience.years": "9"}),
        resolve_facts([_ans("experience.vehicle_type", "sencillo")], {"experience.vehicle_type": "full"}),
    ]
    for out in cases:
        for rf in out["resolved"]:
            assert rf["state"] in FACT_STATES


def test_normalize_fact_value():
    assert normalize_fact_value("experience.years", "10 años") == "10"
    assert normalize_fact_value("experience.years", "diez") == "10"
    assert normalize_fact_value("experience.vehicle_type", "full") == "full"
    assert normalize_fact_value("experience.vehicle_type", "quinta rueda") is None
    assert normalize_fact_value("candidate.city", "Torreón") == "torreon"
