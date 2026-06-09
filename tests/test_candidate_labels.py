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
    "experience.vehicle_type": "full",
    "experience.years": "10 años",
    "documents.labor_letters_status": "available",
    "candidate.city": "Torreón",
    "candidate.vacancy_accepted": "sí",
}

SENCILLO_FACTS = {
    "license.category": "E",
    "medical.apto_status": "vigente",
    "experience.vehicle_type": "sencillo",
    "experience.years": "8 años",
    "documents.labor_letters_status": "available",
    "candidate.city": "Torreón",
    "candidate.vacancy_accepted": "sí",
}


# ── catálogo oficial ──────────────────────────────────────────────────────────

def test_official_labels_count():
    assert len(OFFICIAL_LABELS) == 24


def test_official_labels_contains_expected():
    expected = {
        "aclaracion_pendiente", "bot_activo", "cecati_sugerido",
        "considerar_escuelita_transmontes", "considerar_operador_b1",
        "documentos", "falta_apto", "falta_ciudad", "falta_experiencia",
        "falta_licencia", "falta_unidad", "foraneo", "jerga_ambigua",
        "llamada_pendiente", "local_laguna", "objetivo_full_sencillo",
        "perfil_listo", "reingreso_verificar", "requiere_agente",
        "requiere_revision_ch", "riesgo_alto", "seguimiento",
        "urgente", "validar_traslado",
    }
    assert OFFICIAL_LABELS == expected


def test_official_labels_no_cecati():
    assert "cecati" not in OFFICIAL_LABELS


def test_official_labels_no_escuelita():
    assert "escuelita" not in OFFICIAL_LABELS


def test_official_labels_no_disponible_acudir():
    assert "disponible_acudir" not in OFFICIAL_LABELS


def test_official_labels_tiene_cecati_sugerido():
    assert "cecati_sugerido" in OFFICIAL_LABELS


def test_official_labels_tiene_considerar_escuelita():
    assert "considerar_escuelita_transmontes" in OFFICIAL_LABELS


def test_official_labels_tiene_llamada_pendiente():
    assert "llamada_pendiente" in OFFICIAL_LABELS


def test_official_labels_tiene_considerar_operador_b1():
    assert "considerar_operador_b1" in OFFICIAL_LABELS


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


# ── sencillo como unidad objetivo válida (igual que full) ────────────────────

def test_sencillo_perfil_listo_igual_que_full():
    result = calculate_candidate_labels(_ctx(SENCILLO_FACTS))
    assert "perfil_listo" in result
    assert "falta_licencia" not in result
    assert "falta_apto" not in result
    assert "documentos" not in result


def test_sencillo_has_experience_sin_fifth_wheel():
    """vehicle_type=sencillo cuenta como has_experience sin necesitar fifth_wheel."""
    facts = {"experience.vehicle_type": "sencillo"}
    result = calculate_candidate_labels(_ctx(facts))
    assert "bot_activo" in result  # flujo normal activo
    # has_experience = True → no genera documentos sin licencia/experiencia vacía


def test_sencillo_allowlist_subsets_official():
    result = calculate_candidate_labels(_ctx(SENCILLO_FACTS))
    assert set(result) <= OFFICIAL_LABELS


def test_sencillo_no_requiere_fifth_wheel():
    """SENCILLO_FACTS no tiene fifth_wheel y perfil_listo debe funcionar igual."""
    assert "experience.fifth_wheel" not in SENCILLO_FACTS
    result = calculate_candidate_labels(_ctx(SENCILLO_FACTS))
    assert "perfil_listo" in result


# ── labels deprecadas nunca en output ────────────────────────────────────────

@pytest.mark.parametrize("facts,requires_human,risk_level", [
    ({}, False, None),
    (FULL_FACTS, False, None),
    (SENCILLO_FACTS, False, None),
    (FULL_FACTS, True, "high"),
])
def test_deprecated_labels_never_emitted(facts, requires_human, risk_level):
    """cecati, escuelita y disponible_acudir nunca deben aparecer en el output."""
    result = calculate_candidate_labels(_ctx(facts, requires_human, risk_level))
    assert "cecati" not in result
    assert "escuelita" not in result
    assert "disponible_acudir" not in result


# ── nota IA: display de labels nuevas ────────────────────────────────────────

from app.chatwoot_note_sync import render_candidate_note, _LABEL_DISPLAY  # noqa: E402


def _nota_con_labels(labels: list[str]) -> str:
    ctx = {"lead": {}, "facts": {}, "last_message": {}, "conversation": {}}
    return render_candidate_note(ctx, labels)


def test_nota_muestra_cecati_sugerido_en_humano():
    note = _nota_con_labels(["bot_activo", "cecati_sugerido"])
    assert "CECATI sugerido" in note
    assert "cecati_sugerido" not in note


def test_nota_muestra_considerar_escuelita_en_humano():
    note = _nota_con_labels(["bot_activo", "considerar_escuelita_transmontes"])
    assert "Considerar Escuelita Transmontes" in note
    assert "considerar_escuelita_transmontes" not in note


def test_nota_no_muestra_cecati_raw():
    """La nota nunca debe mostrar el string raw 'cecati' (label deprecada)."""
    note = _nota_con_labels(["bot_activo"])
    assert "cecati\n" not in note.lower()
    assert note.count("cecati") == 0 or "CECATI sugerido" in note


def test_nota_no_muestra_escuelita_raw():
    """La nota nunca debe mostrar el string raw 'escuelita' (label deprecada)."""
    note = _nota_con_labels(["bot_activo"])
    # escuelita no debe aparecer como label en la sección Labels
    lines = note.split("\n")
    label_section = next((l for l in lines if "bot_activo" in l.lower() or "Bot activo" in l), "")
    assert "escuelita" not in label_section


def test_label_display_no_contiene_deprecated():
    """_LABEL_DISPLAY no debe tener keys para labels deprecadas."""
    assert "cecati" not in _LABEL_DISPLAY
    assert "escuelita" not in _LABEL_DISPLAY
    assert "disponible_acudir" not in _LABEL_DISPLAY


def test_nota_muestra_considerar_operador_b1_en_humano():
    note = _nota_con_labels(["bot_activo", "considerar_operador_b1"])
    assert "Considerar operador B1" in note
    assert "considerar_operador_b1" not in note


def test_perfil_listo_no_depende_de_disponible_acudir():
    """disponible_acudir no debe completar perfil_listo."""
    facts_sin_disponible = {
        "license.category": "E",
        "medical.apto_status": "vigente",
        "experience.vehicle_type": "full",
        "experience.years": "10 años",
        "documents.labor_letters_status": "available",
        "candidate.city": "Torreón",
        "candidate.vacancy_accepted": "sí",
    }
    facts_con_disponible = {**facts_sin_disponible, "candidate.availability_to_attend": "sí"}
    result_sin = calculate_candidate_labels(_ctx(facts_sin_disponible))
    result_con = calculate_candidate_labels(_ctx(facts_con_disponible))
    # disponible_acudir no altera perfil_listo
    assert "perfil_listo" in result_sin
    assert "perfil_listo" in result_con
    assert "disponible_acudir" not in result_sin
    assert "disponible_acudir" not in result_con
