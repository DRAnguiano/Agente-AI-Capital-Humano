"""B6.1 — dedup de prefijo/ack en la respuesta visible del current_turn guard.

Cubre el helper puro `_join_ack_and_question` (sin extracción ni BD) y una
verificación de integración por `build_current_turn_ack` para confirmar que el
reply visible no duplica "Perfecto".
"""
from __future__ import annotations

from app.knowledge.current_turn import (
    _join_ack_and_question,
    _strip_leading_perfecto,
    build_current_turn_ack,
)


# ---------------------------------------------------------------------------
# Helper puro
# ---------------------------------------------------------------------------

def test_join_dedups_double_perfecto():
    out = _join_ack_and_question(
        "Perfecto, registro ciudad Torreón, licencia tipo E.",
        "Perfecto. ¿Cuántos años de experiencia tienes como operador?",
    )
    assert out == ("Perfecto, registro ciudad Torreón, licencia tipo E. "
                   "¿Cuántos años de experiencia tienes como operador?")
    assert out.count("Perfecto") == 1
    assert "¿Cuántos años de experiencia" in out  # se preserva la apertura ¿


def test_join_empty_prefix_keeps_question():
    q = "Perfecto. ¿Cuántos años de experiencia tienes como operador?"
    assert _join_ack_and_question("", q) == q


def test_join_question_none_returns_prefix():
    assert _join_ack_and_question("Perfecto, lo dejo registrado.", None) == "Perfecto, lo dejo registrado."


def test_join_question_empty_returns_prefix():
    assert _join_ack_and_question("Perfecto, lo dejo registrado.", "   ") == "Perfecto, lo dejo registrado."


def test_join_question_without_perfecto_unchanged():
    out = _join_ack_and_question("Perfecto, registro ciudad Torreón.", "¿Cuentas con cartas laborales?")
    assert out == "Perfecto, registro ciudad Torreón. ¿Cuentas con cartas laborales?"
    assert out.count("Perfecto") == 1


def test_strip_leading_perfecto_preserves_inverted_question_mark():
    assert _strip_leading_perfecto("Perfecto. ¿Cuántos años?") == "¿Cuántos años?"


def test_strip_leading_perfecto_recapitalizes_next_word():
    assert _strip_leading_perfecto("Perfecto, ya casi terminamos. ¿X?") == "Ya casi terminamos. ¿X?"


# ---------------------------------------------------------------------------
# Integración por build_current_turn_ack (un solo "Perfecto")
# ---------------------------------------------------------------------------

def test_ack_city_license_single_perfecto():
    reply = build_current_turn_ack("soy de Torreón y tengo licencia tipo E")
    assert reply.count("Perfecto") == 1
    assert "¿Cuántos años tiene" in reply
    assert "Perfecto. ¿" not in reply  # no quedó el doble prefijo


def test_ack_city_license_apto_single_perfecto_single_question():
    reply = build_current_turn_ack("soy de Torreón, licencia tipo E vigente y mi apto está vigente")
    assert reply.count("Perfecto") == 1
    assert reply.count("?") == 1  # una sola pregunta visible


# ---------------------------------------------------------------------------
# B6.2 — sin fact duplicado en el prefijo ("20 años, 20 años de experiencia").
# El extractor único (profile_extractor, guard B3) NO saca candidate.age desde
# una frase de experiencia, así que el ack menciona los años una sola vez.
# ---------------------------------------------------------------------------

def test_ack_experience_years_not_duplicated_as_age():
    reply = build_current_turn_ack("tengo 20 años manejando full")
    assert "20 años de experiencia" in reply
    # "20 años" aparece solo dentro de "20 años de experiencia", no como edad aparte.
    assert reply.count("20 años") == 1
    assert "20 años," not in reply  # no el patrón "20 años, 20 años de experiencia"


def test_ack_experience_full_mentioned_once():
    reply = build_current_turn_ack("tengo 20 años manejando full")
    assert reply.count("tracto full") == 1
