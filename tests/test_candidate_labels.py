"""B11 — labels oficiales / no labels fantasma.

`calculate_candidate_labels` solo emite labels del catálogo oficial.
Labels fantasma (`falta_cartas`, `apto_por_vencer*`, `licencia_por_vencer*`) eliminadas.
"""
from __future__ import annotations

import pytest

from app.chatwoot_note_sync import (
    OFFICIAL_LABELS,
    _filter_official_labels,
    calculate_candidate_labels,
)


# ── helpers ──────────────────────────────────────────────────────────────────

def _ctx(facts=None, requires_human=False, risk_level=None):
    return {
        "lead": {"requires_human": requires_human, "risk_level": risk_level or ""},
        "facts": facts or {},
    }


FULL_FACTS = {
    "license.category": "E",
    "medical.apto_status": "vigente",
    "experience.fifth_wheel": "sí",
    "experience.years": "10 años",
    "documents.labor_letters_status": "available",
    "candidate.city": "Torreón",
    "candidate.vacancy_accepted": "sí",
}


# ── catálogo oficial ──────────────────────────────────────────────────────────

def test_official_labels_count():
    assert len(OFFICIAL_LABELS) == 23


def test_official_labels_contains_expected():
    expected = {
        "aclaracion_pendiente", "bot_activo", "cecati", "disponible_acudir",
        "documentos", "escuelita", "falta_apto", "falta_ciudad",
        "falta_experiencia", "falta_licencia", "falta_unidad", "foraneo",
        "jerga_ambigua", "local_laguna", "objetivo_full_sencillo", "perfil_listo",
        "reingreso_verificar", "requiere_agente", "requiere_revision_ch",
        "riesgo_alto", "seguimiento", "urgente", "validar_traslado",
    }
    assert OFFICIAL_LABELS == expected


# ── _filter_official_labels ───────────────────────────────────────────────────

def test_filter_removes_fantasy_label():
    result = _filter_official_labels(["bot_activo", "label_fantasma", "falta_cartas"])
    assert "bot_activo" in result
    assert "label_fantasma" not in result
    assert "falta_cartas" not in result


def test_filter_keeps_all_official():
    result = set(_filter_official_labels(list(OFFICIAL_LABELS)))
    assert result == OFFICIAL_LABELS


def test_filter_returns_sorted():
    result = _filter_official_labels(["seguimiento", "bot_activo"])
    assert result == sorted(result)


# ── allowlist: nunca sale nada fuera del catálogo ─────────────────────────────

@pytest.mark.parametrize("facts,requires_human,risk_level", [
    ({}, False, None),
    (FULL_FACTS, False, None),
    (FULL_FACTS, True, "high"),
    ({"license.category": "E", "medical.apto_expiration_text": "vence en 3 días"}, False, None),
    ({"license.category": "E", "license.expiration_text": "vence en 2 semanas"}, False, None),
    ({"medical.apto_expiration_text": "vence en 1 mes"}, False, None),
    ({"candidate.city": "Monterrey", "experience.years": "5 años"}, False, None),
])
def test_allowlist_subsets_official(facts, requires_human, risk_level):
    result = calculate_candidate_labels(_ctx(facts, requires_human, risk_level))
    assert set(result) <= OFFICIAL_LABELS, f"Labels fuera de catálogo: {set(result) - OFFICIAL_LABELS}"


# ── falta_cartas → documentos ─────────────────────────────────────────────────

def test_no_letters_with_license_emits_documentos():
    facts = {"license.category": "E"}
    result = calculate_candidate_labels(_ctx(facts))
    assert "documentos" in result
    assert "falta_cartas" not in result


def test_no_letters_with_experience_emits_documentos():
    facts = {"experience.years": "5 años"}
    result = calculate_candidate_labels(_ctx(facts))
    assert "documentos" in result
    assert "falta_cartas" not in result


def test_has_letters_no_documentos():
    facts = {"license.category": "E", "documents.labor_letters_status": "available"}
    result = calculate_candidate_labels(_ctx(facts))
    assert "documentos" not in result
    assert "falta_cartas" not in result


def test_no_license_no_experience_no_documentos():
    result = calculate_candidate_labels(_ctx({}))
    assert "documentos" not in result


# ── labels fantasma de vencimiento eliminadas ─────────────────────────────────

@pytest.mark.parametrize("exp_text", [
    "vence en 3 días",
    "vence en 2 semanas",
    "vence en 1 mes",
    "vence en 5 meses",
])
def test_no_apto_por_vencer_variants(exp_text):
    facts = {"medical.apto_expiration_text": exp_text}
    result = calculate_candidate_labels(_ctx(facts))
    assert "apto_por_vencer" not in result
    assert "apto_por_vencer_urgente" not in result


@pytest.mark.parametrize("exp_text", [
    "vence en 3 días",
    "vence en 2 semanas",
    "vence en 1 mes",
    "vence en 5 meses",
])
def test_no_licencia_por_vencer_variants(exp_text):
    facts = {"license.expiration_text": exp_text}
    result = calculate_candidate_labels(_ctx(facts))
    assert "licencia_por_vencer" not in result
    assert "licencia_por_vencer_urgente" not in result


# ── regresiones: labels oficiales conservadas ─────────────────────────────────

def test_regression_falta_licencia():
    result = calculate_candidate_labels(_ctx({}))
    assert "falta_licencia" in result


def test_regression_falta_apto_sin_medico():
    result = calculate_candidate_labels(_ctx({}))
    assert "falta_apto" in result


def test_regression_apto_vigente_clears_falta_apto():
    facts = {"medical.apto_status": "vigente"}
    result = calculate_candidate_labels(_ctx(facts))
    assert "falta_apto" not in result


def test_regression_foraneo_y_validar_traslado():
    facts = {"candidate.city": "Monterrey"}
    result = calculate_candidate_labels(_ctx(facts))
    assert "foraneo" in result
    assert "validar_traslado" in result


def test_regression_local_no_foraneo():
    facts = {"candidate.city": "Torreón"}
    result = calculate_candidate_labels(_ctx(facts))
    assert "foraneo" not in result
    assert "validar_traslado" not in result


def test_regression_perfil_listo():
    result = calculate_candidate_labels(_ctx(FULL_FACTS))
    assert "perfil_listo" in result
    assert "falta_licencia" not in result
    assert "falta_apto" not in result
    assert "documentos" not in result


def test_regression_bot_activo_siempre_presente():
    result = calculate_candidate_labels(_ctx({}))
    assert "bot_activo" in result


def test_regression_requiere_agente_y_revision():
    result = calculate_candidate_labels(_ctx({}, requires_human=True))
    assert "requiere_agente" in result
    assert "requiere_revision_ch" in result


def test_regression_riesgo_alto():
    result = calculate_candidate_labels(_ctx({}, risk_level="high"))
    assert "riesgo_alto" in result


def test_regression_seguimiento_por_submission():
    facts = {"documents.submission_status": "pending_candidate_will_send"}
    result = calculate_candidate_labels(_ctx(facts))
    assert "seguimiento" in result
