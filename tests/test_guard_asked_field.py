"""asked_field_keys_for_guard — captura pasiva del campo preguntado por el guard (Fase B).

Verifica que el helper es un espejo EXACTO de la cascada de
``current_turn.next_question_from_missing_facts`` (mismos predicados, incl. el
`and` literal de licencia), y que el save del guard enriquece external_metadata
solo cuando preguntó un campo limpio.
"""
from __future__ import annotations

import pytest

from app.knowledge.guard_asked_field import asked_field_keys_for_guard
from app.knowledge.current_turn import next_question_from_missing_facts


# Estados del funnel del guard (city presente salvo el primero).
_CITY = {"candidate.city": "Torreon"}
_LIC = {"license.category": "E", "license.status": "vigente"}
_YEARS = {"experience.years": "5"}
_VT = {"experience.vehicle_type": "full"}
_APTO = {"medical.apto_status": "vigente"}
_DOCS = {"documents.labor_letters": "si"}


# ---------------------------------------------------------------------------
# 1) Helper por estado de la cascada
# ---------------------------------------------------------------------------

def test_city_missing():
    assert asked_field_keys_for_guard({}) == ["candidate.city"]


def test_license_mixed_returns_empty():
    # Falta licencia (categoría Y status) → pregunta mixta tipo+vigencia → [].
    assert asked_field_keys_for_guard({**_CITY}) == []


def test_years_missing():
    assert asked_field_keys_for_guard({**_CITY, **_LIC}) == ["experience.years"]


def test_vehicle_type_missing():
    assert asked_field_keys_for_guard({**_CITY, **_LIC, **_YEARS}) == ["experience.vehicle_type"]


def test_apto_missing_returns_empty():
    # Apto/vigencia advisory → diferido → [].
    assert asked_field_keys_for_guard({**_CITY, **_LIC, **_YEARS, **_VT}) == []


def test_documents_missing():
    assert asked_field_keys_for_guard({**_CITY, **_LIC, **_YEARS, **_VT, **_APTO}) == ["documents.proof"]


def test_profile_complete_returns_empty():
    full = {**_CITY, **_LIC, **_YEARS, **_VT, **_APTO, **_DOCS}
    assert asked_field_keys_for_guard(full) == []


# ---------------------------------------------------------------------------
# 2) Caso específico solicitado: categoría presente, vigencia faltante, años faltante
# ---------------------------------------------------------------------------

def test_category_present_status_missing_falls_through_to_years():
    # city presente, license.category presente, license.status faltante,
    # experience.years faltante. El guard usa `and` → brinca licencia → pregunta AÑOS.
    facts = {"candidate.city": "Torreon", "license.category": "E"}
    q = next_question_from_missing_facts(facts)
    assert "años de experiencia" in q  # la pregunta visible es la de experiencia
    assert asked_field_keys_for_guard(facts) == ["experience.years"]  # y el helper coincide


# ---------------------------------------------------------------------------
# 3) Alineación helper ↔ pregunta visible (anti-drift), por estado
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("facts,expected_keys,question_marker", [
    ({},                                                  ["candidate.city"],          "ciudad"),
    ({**_CITY},                                           [],                          "licencia federal"),
    ({**_CITY, **_LIC},                                   ["experience.years"],        "años de experiencia"),
    ({**_CITY, **_LIC, **_YEARS},                         ["experience.vehicle_type"], "sencillo"),
    ({**_CITY, **_LIC, **_YEARS, **_VT},                  [],                          "apto médico"),
    ({**_CITY, **_LIC, **_YEARS, **_VT, **_APTO},         ["documents.proof"],         "cartas laborales"),
])
def test_helper_aligned_with_visible_question(facts, expected_keys, question_marker):
    # El campo del helper corresponde a la pregunta que el guard realmente hace.
    assert asked_field_keys_for_guard(facts) == expected_keys
    assert question_marker in next_question_from_missing_facts(facts)


# ---------------------------------------------------------------------------
# 4) Pureza: no muta la entrada
# ---------------------------------------------------------------------------

def test_helper_does_not_mutate_input():
    facts = {**_CITY, **_LIC}
    snapshot = dict(facts)
    asked_field_keys_for_guard(facts)
    assert facts == snapshot


# ---------------------------------------------------------------------------
# 5) Construcción de external_metadata del save (espejo del glue en tasks_chatwoot)
# ---------------------------------------------------------------------------

def _build_guard_meta(facts):
    """Misma construcción que el save del guard en tasks_chatwoot.py."""
    guard_keys = asked_field_keys_for_guard(facts)
    return (
        {
            "asked_field_keys": guard_keys,
            "asked_field_source": "current_turn_guard",
            "asked_field_key_space": "canonical",
        }
        if guard_keys
        else None
    )


def test_save_metadata_clean_field():
    meta = _build_guard_meta({**_CITY, **_LIC})  # falta years → pregunta experiencia
    assert meta == {
        "asked_field_keys": ["experience.years"],
        "asked_field_source": "current_turn_guard",
        "asked_field_key_space": "canonical",
    }


def test_save_metadata_mixed_or_advisory_is_none():
    assert _build_guard_meta({**_CITY}) is None                                  # licencia mixta
    assert _build_guard_meta({**_CITY, **_LIC, **_YEARS, **_VT}) is None         # apto advisory
