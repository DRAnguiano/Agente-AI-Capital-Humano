"""B7.4 — call scheduling determinista (sin agenda real, sin Groq/DB).

Contrato (live-reply, chatwoot-label-taxonomy + message-orchestration):
  - El extractor registra `scheduling.call_requested=true`, `scheduling.call_status=pending`
    y `scheduling.call_window_text` (texto del candidato) ante una solicitud de llamada.
  - `llamada_pendiente` SHALL emitirse SOLO desde la decisión determinista cuando
    `perfil_listo` o `requiere_agente` están activos y el candidato pidió llamada.
    Antes de perfil listo / handoff → `seguimiento` (no `llamada_pendiente`).
  - La validez del horario (`scheduling.call_window_valid`) es B7.5, fuera de este test.
"""
from __future__ import annotations

import pytest

import app.lead_memory.profile_extractor as PE
from app.chatwoot_note_sync import OFFICIAL_LABELS, calculate_candidate_labels


# ── extractor: detección de solicitud de llamada ──────────────────────────────

@pytest.mark.parametrize("message", [
    "quiero que me llamen",
    "me pueden llamar?",
    "prefiero una llamada",
    "mejor llámenme por teléfono",
    "agenden una llamada porfa",
])
def test_call_request_sets_scheduling_facts(message):
    facts = PE.extract_profile_facts_as_dict(message)
    assert facts.get("scheduling.call_requested") == "true"
    assert facts.get("scheduling.call_status") == "pending"


@pytest.mark.parametrize("message", [
    "no quiero llamada, mejor escríbanme",
    "no me llamen por favor",
    "¿cuánto pagan?",
    "soy de Torreón y manejo full",
])
def test_no_call_request_no_scheduling_facts(message):
    facts = PE.extract_profile_facts_as_dict(message)
    assert "scheduling.call_requested" not in facts


def test_call_window_text_captured():
    facts = PE.extract_profile_facts_as_dict("me pueden llamar mañana a las 4")
    assert facts.get("scheduling.call_requested") == "true"
    assert "manana" in (facts.get("scheduling.call_window_text") or "")


# ── label: emisión gated de llamada_pendiente ─────────────────────────────────

def _ctx(facts=None, requires_human=False, risk_level=None):
    return {
        "lead": {"requires_human": requires_human, "risk_level": risk_level or ""},
        "facts": facts or {},
    }


_PERFIL_LISTO_FACTS = {
    "license.category": "E",
    "medical.apto_status": "vigente",
    "experience.vehicle_type": "full",
    "experience.years": "10 años",
    "documents.labor_letters_status": "available",
    "candidate.city": "Torreón",
    "candidate.vacancy_accepted": "sí",
}


def test_llamada_pendiente_con_perfil_listo():
    facts = {**_PERFIL_LISTO_FACTS, "scheduling.call_requested": "true"}
    result = calculate_candidate_labels(_ctx(facts))
    assert "perfil_listo" in result
    assert "llamada_pendiente" in result


def test_llamada_pendiente_con_requiere_agente():
    facts = {"scheduling.call_requested": "true"}
    result = calculate_candidate_labels(_ctx(facts, requires_human=True))
    assert "requiere_agente" in result
    assert "llamada_pendiente" in result


def test_sin_perfil_ni_agente_no_llamada_pendiente_usa_seguimiento():
    facts = {"scheduling.call_requested": "true", "candidate.city": "Torreón"}
    result = calculate_candidate_labels(_ctx(facts))
    assert "llamada_pendiente" not in result
    assert "seguimiento" in result


def test_sin_solicitud_no_llamada_pendiente():
    result = calculate_candidate_labels(_ctx(_PERFIL_LISTO_FACTS))
    assert "llamada_pendiente" not in result


def test_llamada_pendiente_es_label_oficial():
    assert "llamada_pendiente" in OFFICIAL_LABELS
