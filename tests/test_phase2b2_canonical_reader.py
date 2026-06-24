"""Fase 2B.2 — tests del canonical_profile_reader.

Unit (sin DB): mapeo `_row_to_fact` + degradación segura cuando la vista no existe.
La lectura real contra la vista es prueba de integración manual (2B.3).
"""
from __future__ import annotations

from app.lead_memory import canonical_profile_reader as reader
from app.knowledge.funnel_state_planner import CanonicalFact, compute_funnel_state


def test_row_to_fact_mapping():
    row = {
        "lead_key": "chatwoot:99",
        "is_active": True,
        "confidence": 0.9,
        "source": "knowledge_orchestrator",
        "observed_at": "2026-06-04T12:00:00Z",
        "raw_group": "license", "raw_key": "category", "raw_value": "B",
        "canonical_group": "license", "canonical_key": "type",
        "canonical_value": "B", "canonical_unit": None, "canonical_state": "ok",
    }
    f = reader._row_to_fact(row)
    assert isinstance(f, CanonicalFact)
    assert f.field == "license.type"
    assert f.canonical_value == "B" and f.canonical_state == "ok"
    assert f.raw_key == "category" and f.lead_key == "chatwoot:99"


def test_row_to_fact_feeds_planner():
    # El reader produce CanonicalFact que el planner consume directamente (contrato).
    row = {
        "canonical_group": "documents", "canonical_key": "proof",
        "canonical_value": "cartas", "canonical_state": "mapped_to_proof",
        "is_active": True, "raw_key": "labor_letters", "raw_value": "sí",
    }
    st = compute_funnel_state([reader._row_to_fact(row)])
    assert "documents.proof" in st.completed_fields


def test_read_returns_empty_when_view_absent(monkeypatch):
    # Shadow-safe: si la vista no existe, [] sin tocar la BD ni lanzar excepción.
    monkeypatch.setattr(reader, "canonical_view_exists", lambda: False)
    assert reader.read_canonical_facts("chatwoot:99") == []
