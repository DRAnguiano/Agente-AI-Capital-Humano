"""Tarea 9.1 (replay) — helper puro de emparejamiento de turnos.

Determinista: prueba `_last_user_exchange` (sin DB, sin Groq). El resto del script
(`_candidate_lead_keys`, `replay`) necesita Postgres+Groq y se ejerce en vivo vía api-test.
"""
from __future__ import annotations

from scripts.shadow_replay import _last_user_exchange


def _m(role, message):
    return {"role": role, "message": message}


def test_last_exchange_basic():
    msgs = [_m("assistant", "q1"), _m("user", "a1"), _m("assistant", "r1")]
    user_msg, actual_reply, prev = _last_user_exchange(msgs)
    assert user_msg == "a1"
    assert actual_reply == "r1"
    assert prev == [_m("assistant", "q1")]  # mensajes previos al turno de usuario


def test_last_exchange_falls_back_to_answered_turn():
    # el último turno de usuario no tiene respuesta; usa el anterior que sí la tiene
    msgs = [_m("user", "u1"), _m("assistant", "r1"), _m("user", "u2")]
    user_msg, actual_reply, prev = _last_user_exchange(msgs)
    assert user_msg == "u1"
    assert actual_reply == "r1"
    assert prev == []


def test_last_exchange_none_when_no_reply():
    assert _last_user_exchange([_m("user", "hola")]) is None
    assert _last_user_exchange([]) is None
    assert _last_user_exchange([_m("assistant", "hola")]) is None


def test_last_exchange_picks_most_recent_answered():
    msgs = [
        _m("user", "u1"), _m("assistant", "r1"),
        _m("user", "u2"), _m("assistant", "r2"),
    ]
    user_msg, actual_reply, prev = _last_user_exchange(msgs)
    assert user_msg == "u2" and actual_reply == "r2"
    assert len(prev) == 2  # u1 + r1 quedan como previos
