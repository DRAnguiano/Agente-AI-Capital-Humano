"""Fase 1B — camino VIVO: extracción de tipo de unidad en profile_extractor.

Verifica que el extractor (regex legacy) ahora delega la resolución de unidad al catálogo
de dominio: full/sencillo confirmados; quinta rueda/tráiler = experiencia compatible sin
vehicle_type final (F8); camión/torton no infieren full/sencillo.

Deterministas, sin LLM ni DB.
"""
from __future__ import annotations

from app.lead_memory.profile_extractor import extract_profile_facts_as_dict


def test_manejo_full_guarda_vehicle_type_full():
    facts = extract_profile_facts_as_dict("manejo full")
    assert facts.get("experience.vehicle_type") == "full"


def test_manejo_sencillo_guarda_vehicle_type_sencillo():
    facts = extract_profile_facts_as_dict("manejo sencillo")
    assert facts.get("experience.vehicle_type") == "sencillo"


def test_quinta_rueda_no_fija_vehicle_type_pero_marca_experiencia():
    facts = extract_profile_facts_as_dict("soy operador de quinta rueda")
    assert "experience.vehicle_type" not in facts            # F8: no se fija
    assert facts.get("experience.fifth_wheel") == "sí"       # experiencia compatible


def test_trailer_no_fija_vehicle_type_pero_marca_experiencia():
    facts = extract_profile_facts_as_dict("manejo tráiler")
    assert "experience.vehicle_type" not in facts
    assert facts.get("experience.fifth_wheel") == "sí"


def test_camion_no_infiere_full_ni_sencillo():
    facts = extract_profile_facts_as_dict("manejo camión")
    assert facts.get("experience.vehicle_type") not in ("full", "sencillo")
    assert "experience.vehicle_type" not in facts


def test_torton_no_infiere_unidad_ni_fifth_wheel():
    facts = extract_profile_facts_as_dict("manejo torton")
    assert "experience.vehicle_type" not in facts
    assert "experience.fifth_wheel" not in facts
