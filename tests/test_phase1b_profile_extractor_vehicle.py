"""Fase 1B / B2 — extracción de tipo de unidad en profile_extractor.

full/sencillo confirmados → vehicle_type (sin fifth_wheel).
quinta rueda/tráiler/trailero/trucker → señal ambigua; nada persistido, funnel pregunta.
torton/rabón/reparto → non_target; nada persistido.
experience.fifth_wheel es deuda técnica eliminada: ningún caso lo produce.

Deterministas, sin LLM ni DB.
"""
from __future__ import annotations

from app.lead_memory.profile_extractor import (
    extract_profile_facts_as_dict as f,
    missing_profile_fields,
)


# ── full/sencillo confirmados ─────────────────────────────────────────────────

def test_manejo_full_guarda_vehicle_type_full():
    facts = f("manejo full")
    assert facts.get("experience.vehicle_type") == "full"
    assert "experience.fifth_wheel" not in facts


def test_manejo_sencillo_guarda_vehicle_type_sencillo():
    facts = f("manejo sencillo")
    assert facts.get("experience.vehicle_type") == "sencillo"
    assert "experience.fifth_wheel" not in facts


def test_soy_fullero_guarda_full():
    facts = f("soy fullero")
    assert facts.get("experience.vehicle_type") == "full"
    assert "experience.fifth_wheel" not in facts


def test_tracto_full_guarda_full():
    facts = f("manejo tracto full")
    assert facts.get("experience.vehicle_type") == "full"
    assert "experience.fifth_wheel" not in facts


def test_tracto_sencillo_guarda_sencillo():
    facts = f("manejo tracto sencillo")
    assert facts.get("experience.vehicle_type") == "sencillo"
    assert "experience.fifth_wheel" not in facts


# ── señales ambiguas de oficio → nada persistido ─────────────────────────────

def test_quinta_rueda_no_fija_vehicle_type_ni_fifth_wheel():
    facts = f("soy operador de quinta rueda")
    assert "experience.vehicle_type" not in facts
    assert "experience.fifth_wheel" not in facts


def test_trailer_no_fija_vehicle_type_ni_fifth_wheel():
    facts = f("manejo tráiler")
    assert "experience.vehicle_type" not in facts
    assert "experience.fifth_wheel" not in facts


def test_trailero_no_fija_vehicle_type_ni_fifth_wheel():
    facts = f("soy trailero")
    assert "experience.vehicle_type" not in facts
    assert "experience.fifth_wheel" not in facts


def test_trucker_no_fija_vehicle_type_ni_fifth_wheel():
    facts = f("soy trucker")
    assert "experience.vehicle_type" not in facts
    assert "experience.fifth_wheel" not in facts


# ── non_target: torton/rabón/camión ──────────────────────────────────────────

def test_torton_no_infiere_unidad():
    facts = f("manejo torton")
    assert "experience.vehicle_type" not in facts
    assert "experience.fifth_wheel" not in facts


def test_rabon_no_infiere_unidad():
    facts = f("manejo rabón")
    assert "experience.vehicle_type" not in facts
    assert "experience.fifth_wheel" not in facts


def test_camion_no_infiere_full_ni_sencillo():
    facts = f("manejo camión")
    assert facts.get("experience.vehicle_type") not in ("full", "sencillo")
    assert "experience.vehicle_type" not in facts


# ── missing_profile_fields usa vehicle_type ───────────────────────────────────

def test_missing_fields_sin_vehicle_type_reporta_tipo_unidad():
    missing = missing_profile_fields({"candidate.city": "Torreón"})
    assert "tipo de unidad (tracto full o sencillo)" in missing


def test_missing_fields_con_vehicle_type_full_satisfecho():
    facts = {"candidate.city": "Torreón", "experience.vehicle_type": "full"}
    assert "tipo de unidad (tracto full o sencillo)" not in missing_profile_fields(facts)


def test_missing_fields_con_vehicle_type_sencillo_satisfecho():
    facts = {"candidate.city": "Torreón", "experience.vehicle_type": "sencillo"}
    assert "tipo de unidad (tracto full o sencillo)" not in missing_profile_fields(facts)


def test_missing_fields_fifth_wheel_no_satisface_vehicle_type():
    # Registro legacy con fifth_wheel pero sin vehicle_type → sigue faltando
    facts = {"candidate.city": "Torreón", "experience.fifth_wheel": "sí"}
    assert "tipo de unidad (tracto full o sencillo)" in missing_profile_fields(facts)
