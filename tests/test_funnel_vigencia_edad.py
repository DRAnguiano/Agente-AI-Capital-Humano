from __future__ import annotations

import os

import pytest

from app.knowledge.current_turn import (
    build_current_turn_ack,
    is_age_disqualified,
    next_question_from_missing_facts,
)
from app.knowledge.guard_asked_field import asked_field_keys_for_guard
from app.lead_memory.profile_extractor import extract_profile_facts_as_dict as facts
from app.chatwoot_note_sync import calculate_candidate_labels, render_candidate_note

_NO_GROQ = not os.getenv("GROQ_API_KEY")


def _ctx(f):
    return {"lead": {}, "facts": f, "last_message": {}, "conversation": {}}


def test_funnel_order_city_then_age_then_unit_then_license_then_apto_then_years_then_docs():
    assert "ciudad" in next_question_from_missing_facts({}).lower()

    q = next_question_from_missing_facts({"candidate.city": "Torreon"})
    assert "edad" in q.lower() or "años tiene" in q.lower()
    assert asked_field_keys_for_guard({"candidate.city": "Torreon"}) == ["candidate.age"]

    q = next_question_from_missing_facts({"candidate.city": "Torreon", "candidate.age": "45"})
    assert "tracto full" in q.lower() and "sencillo" in q.lower()

    q = next_question_from_missing_facts({
        "candidate.city": "Torreon",
        "candidate.age": "45",
        "experience.vehicle_type": "full",
    })
    assert "licencia federal" in q.lower()
    assert "vence" in q.lower()

    q = next_question_from_missing_facts({
        "candidate.city": "Torreon",
        "candidate.age": "45",
        "experience.vehicle_type": "full",
        "license.category": "E",
        "license.expiration_text": "vence en 1 año",
    })
    assert "apto" in q.lower()
    assert "vence" in q.lower()

    q = next_question_from_missing_facts({
        "candidate.city": "Torreon",
        "candidate.age": "45",
        "experience.vehicle_type": "full",
        "license.category": "E",
        "license.expiration_text": "vence en 1 año",
        "medical.apto_expiration_text": "vence en 1 año",
    })
    assert "años de experiencia" in q.lower()

    q = next_question_from_missing_facts({
        "candidate.city": "Torreon",
        "candidate.age": "45",
        "experience.vehicle_type": "full",
        "license.category": "E",
        "license.expiration_text": "vence en 1 año",
        "medical.apto_expiration_text": "vence en 1 año",
        "experience.years": "10 años",
    })
    assert "cartas" in q.lower() or "imss" in q.lower()


def test_age_at_limit_is_disqualified():
    # Límite: AGE_DISQUALIFICATION_LIMIT = 57 (settings.py); 57+ = no apto.
    assert is_age_disqualified({"candidate.age": "57"})
    assert is_age_disqualified({"candidate.age": "60"})
    assert not is_age_disqualified({"candidate.age": "56"})
    assert not is_age_disqualified({"candidate.age": "49"})


def test_age_disqualified_reply_is_non_empty():
    # El mensaje lo genera el LLM (persona_config); solo verificamos que no sea vacío
    # y que no contenga una pregunta de funnel.
    reply = next_question_from_missing_facts({
        "candidate.city": "Torreon",
        "candidate.age": "57",
    })
    assert reply  # no vacío
    # No debe continuar con pregunta de funnel (tipo de unidad, licencia, etc.)
    assert "tracto full" not in reply.lower()
    assert "licencia" not in reply.lower() or "años" not in reply.lower()


def test_age_under_limit_continues():
    q = next_question_from_missing_facts({"candidate.city": "Torreon", "candidate.age": "56"})
    assert "tracto full" in q.lower()


@pytest.mark.skipif(_NO_GROQ, reason="requiere GROQ_API_KEY — profile_extractor usa LLM T=0")
def test_expiration_extraction_relative_and_date():
    d = facts("mi licencia vence el 31 de diciembre de 2027")
    assert d["license.expiration_text"] == "31 de diciembre de 2027"

    d = facts("el apto se me vence como en dos meses")
    assert d["medical.apto_expiration_text"] == "vence en 2 meses"


def test_vigente_without_expiration_reprompts_time():
    q = next_question_from_missing_facts({
        "candidate.city": "Torreon",
        "candidate.age": "45",
        "experience.vehicle_type": "full",
        "license.category": "E",
        "license.status": "vigente",
    })
    assert "en cuánto tiempo se le vence su licencia" in q.lower()


def test_short_expiry_triggers_fixed_renewal_branch():
    base = {
        "candidate.city": "Torreon",
        "candidate.age": "45",
        "experience.vehicle_type": "full",
        "license.category": "E",
        "license.expiration_text": "vence en 18 días",
    }
    assert "papel" in next_question_from_missing_facts(base).lower()

    no_paper = {**base, "documents.renewal_proof": "no"}
    q = next_question_from_missing_facts(no_paper)
    assert "cuando lo tenga" in q.lower()
    assert "continuamos" in q.lower()


def test_age_discard_visible_in_note_without_review_labels_or_bot_activo():
    f = {"candidate.age": "52", "candidate.city": "Torreon"}
    labels = calculate_candidate_labels(_ctx(f))
    assert "bot_activo" not in labels
    assert "requiere_revision_ch" not in labels
    note = render_candidate_note(_ctx(f), labels)
    assert "Edad fuera de perfil" in note
