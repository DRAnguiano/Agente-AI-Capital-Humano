"""Vigencia enunciada se conserva aunque se ofrezca antes de preguntarla
(volunteered-expiration-extraction). Deterministas: sin LLM/Groq.
"""
from __future__ import annotations

from app.knowledge.turn_extractor import (
    FieldValue,
    TurnExtraction,
    _mark_stated_expirations,
    _states_expiration,
    validate_extraction,
)


def _keys(out):
    return {f"{x['fact_group']}.{x['fact_key']}" for x in out}


def test_states_expiration_detects_markers():
    assert _states_expiration("tengo licencia E y vence en un año")
    assert _states_expiration("vencí en 2 años")
    assert _states_expiration("la vigencia es de 3 meses")
    assert _states_expiration("caduca en marzo 2027")
    assert not _states_expiration("hola, me interesa la vacante")
    assert not _states_expiration("soy de Torreón y manejo full")


def test_volunteered_license_expiration_persisted():
    # Sin marcar (D3): vigencia sin marcador ni pregunta directa → descartada.
    f = {"license.expiration_text": FieldValue(value="un año", explicit_marker=False, answered_direct_question=False)}
    assert "license.expiration_text" not in _keys(validate_extraction(TurnExtraction(fields=f), {}))
    # Marcado por mensaje con "vence": se conserva.
    f2 = {"license.expiration_text": FieldValue(value="un año", explicit_marker=False, answered_direct_question=False)}
    _mark_stated_expirations(f2, "tengo licencia E y vence en un año")
    out = validate_extraction(TurnExtraction(fields=f2), {})
    assert "license.expiration_text" in _keys(out)
    assert any(x["fact_value"] == "un año" for x in out)


def test_volunteered_apto_expiration_persisted():
    f = {"medical.apto_expiration_text": FieldValue(value="8 meses", explicit_marker=False, answered_direct_question=False)}
    _mark_stated_expirations(f, "mi apto medico vence en 8 meses y dispongo de cartas laborales")
    assert "medical.apto_expiration_text" in _keys(validate_extraction(TurnExtraction(fields=f), {}))


def test_no_expiration_marker_leaves_d3_intact():
    # Sin marcador de vencimiento en el mensaje → no se marca → D3 la descarta.
    f = {"license.expiration_text": FieldValue(value="un año", explicit_marker=False, answered_direct_question=False)}
    _mark_stated_expirations(f, "soy de Torreón")
    assert "license.expiration_text" not in _keys(validate_extraction(TurnExtraction(fields=f), {}))


def test_candidate_name_guard_unchanged():
    # candidate.name NO es campo de vigencia: aunque el mensaje diga "vence",
    # su guarda D3 no cambia (nombre sin marcador ni pregunta → descartado).
    f = {"candidate.name": FieldValue(value="Juan", explicit_marker=False, answered_direct_question=False)}
    _mark_stated_expirations(f, "vence en un año")
    assert "candidate.name" not in _keys(validate_extraction(TurnExtraction(fields=f), {}))


def test_mark_only_when_value_present():
    # Sin valor no se inventa nada (no-respuesta la filtra el extractor/is_valid aguas abajo).
    f = {"license.expiration_text": FieldValue(value=None, explicit_marker=False)}
    _mark_stated_expirations(f, "no sé cuándo vence")
    assert f["license.expiration_text"].explicit_marker is False
