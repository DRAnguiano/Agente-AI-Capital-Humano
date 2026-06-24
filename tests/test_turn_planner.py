"""Sección 8 — funnel state planner + auditoría por turno.

Cubre el contrato del spec `multi-intent-pipeline` · "Funnel state planner" y
"Auditoría por turno": estado del turno (completed/missing/forbidden/next),
traza de auditoría, no repreguntar lo respondido, y emisión de asked_field_keys.

Deterministas: sin Groq, sin Chroma, sin DB.
"""
from __future__ import annotations

from app.knowledge.turn_planner import ASKED_FIELD_KEYS, plan_turn


def _ans(field, value, **kw):
    a = {"field": field, "value": value, "evidence": str(value), "confidence": 0.95}
    a.update(kw)
    return a


# ── 8.1/8.3: traza de turno completa ──────────────────────────────────────────

TRACE_KEYS = {
    "facts_before", "facts_after", "completed_fields", "missing_fields",
    "forbidden_questions", "next_question", "next_question_field",
    "asked_field_keys", "candidate_corrections", "facts_pending_confirmation",
    "confirmation_question",
}


def test_trace_has_all_audit_keys():
    out = plan_turn({}, [], "hola")
    assert TRACE_KEYS.issubset(out.keys())


def test_empty_facts_next_is_city():
    out = plan_turn({}, [], "hola")
    assert out["next_question_field"] == "candidate.city"
    assert len(out["missing_fields"]) == 6
    assert out["profile_ready"] is False


# ── 8.2/8.7: el sistema fija next_question y emite asked_field_keys ────────────

def test_next_question_emits_asked_field_keys():
    out = plan_turn({}, [], "hola")
    assert out["asked_field_keys"] == ASKED_FIELD_KEYS["candidate.city"]
    assert out["next_question"]  # texto fijado por el sistema, no por el LLM


def test_asked_field_keys_match_next_field():
    facts = {"candidate.city": "Torreón"}  # siguiente faltante: vehicle_type
    out = plan_turn(facts, [], "")
    assert out["next_question_field"] == "experience.vehicle_type"
    assert out["asked_field_keys"] == ASKED_FIELD_KEYS["experience.vehicle_type"]


# ── 8.5: mensaje compuesto extrae todo y no repregunta la unidad ──────────────

def test_compound_extracts_all_and_does_not_reask_unit():
    answers = [
        _ans("experience.years", "10"),
        _ans("experience.vehicle_type", "full"),
        _ans("candidate.availability_status", "available"),
    ]
    out = plan_turn({}, answers, "10 años de full estoy disponible")
    assert out["facts_after"]["experience.years"] == "10"
    assert out["facts_after"]["experience.vehicle_type"] == "full"
    # availability se captura pero NO gatea el funnel (no-núcleo)
    assert out["facts_after"]["candidate.availability_status"] == "available"
    assert "candidate.availability_status" not in out["missing_fields"]
    # la unidad ya está completa → no se vuelve a preguntar
    assert "experience.vehicle_type" in out["completed_fields"]
    assert out["next_question_field"] != "experience.vehicle_type"


# ── 8.6: "¿qué más le falta?" → el planner calcula missing_fields ─────────────

def test_missing_fields_reflect_known_facts():
    facts = {
        "candidate.city": "Torreón",
        "experience.vehicle_type": "full",
        "experience.years": "10",
    }
    out = plan_turn(facts, [], "¿pero que mas le falta?")
    # faltan los tres campos no provistos; los provistos no aparecen
    assert set(out["missing_fields"]) == {"license", "medical.apto_status", "documents.proof"}
    assert "candidate.city" in out["completed_fields"]


# ── Integración con secciones 6 y 7 ──────────────────────────────────────────

def test_memory_reaffirm_marks_field_forbidden_and_completed():
    answers = [_ans("experience.vehicle_type", "full")]
    out = plan_turn({"experience.vehicle_type": "full"}, answers,
                    "ya te había dicho que full")
    assert "experience.vehicle_type" in out["forbidden_questions"]
    assert "experience.vehicle_type" in out["completed_fields"]
    assert out["next_question_field"] != "experience.vehicle_type"


def test_explicit_correction_overwrites_and_audits():
    out = plan_turn(
        {"experience.years": "9"},
        [_ans("experience.years", "10", is_correction=True, evidence="me equivoque son 10")],
        "me equivoqué, son 10 años",
        turn_id="t-7",
    )
    assert out["facts_after"]["experience.years"] == "10"
    assert out["candidate_corrections"][0]["previous_value"] == "9"
    assert out["candidate_corrections"][0]["source_turn_id"] == "t-7"


def test_conflict_does_not_overwrite_and_asks_confirmation():
    out = plan_turn(
        {"experience.vehicle_type": "full"},
        [_ans("experience.vehicle_type", "sencillo")],
        "manejo sencillo",
    )
    # no sobrescribe el valor previo
    assert out["facts_after"]["experience.vehicle_type"] == "full"
    assert out["conflicts"]
    assert out["confirmation_question"] is not None
