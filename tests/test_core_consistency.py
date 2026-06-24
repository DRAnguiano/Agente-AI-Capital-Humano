"""core-consistency-fixes (#1 voz de equipo, #8 ciclo HUMAN_REVIEW).

Tests deterministas, SIN Groq/LLM. Fijan los dos gaps de contrato (Fase 3 implementada):
  - #1: el SYSTEM_PROMPT no usa "Capital Humano" como tercero (solo puede nombrarlo
        dentro de la regla que lo prohíbe).
  - #8: existe una vía explícita de liberación de HUMAN_REVIEW (`db.release_human_review`),
        conservando el guard de `update_stage` contra auto-regresión por mensajes.
"""
from __future__ import annotations

import inspect

import app.db as db
from app.persona_config import SYSTEM_PROMPT

# Pistas de que una mención de "Capital Humano" es parte de la PROHIBICIÓN (permitida),
# no un uso como tercero (prohibido).
_PROHIBITION_CUES = ("nunca", "jamas", "jamás", "no uses", "no lo uses", "no usar")


def _third_party_capital_humano_lines() -> list[str]:
    """Líneas del prompt que usan 'Capital Humano' SIN ser la regla que lo prohíbe."""
    offending = []
    for line in SYSTEM_PROMPT.splitlines():
        low = line.lower()
        if "capital humano" in low and not any(cue in low for cue in _PROHIBITION_CUES):
            offending.append(line.strip())
    return offending


# ---------------------------------------------------------------------------
# #1 — Voz de equipo: el prompt no usa "Capital Humano" como tercero
# ---------------------------------------------------------------------------

def test_system_prompt_no_capital_humano_as_third_party():
    offending = _third_party_capital_humano_lines()
    assert offending == [], (
        f"{len(offending)} líneas usan 'Capital Humano' como tercero (deben ir a voz de equipo): "
        + " | ".join(offending[:5])
    )


def test_system_prompt_keeps_voz_de_equipo_rule():
    # La regla de voz de equipo debe seguir presente (no se elimina al limpiar).
    low = SYSTEM_PROMPT.lower()
    assert "voz de equipo" in low
    assert "nuestro equipo" in low


# ---------------------------------------------------------------------------
# #8 — Ciclo de vida de HUMAN_REVIEW
# ---------------------------------------------------------------------------

def test_update_stage_pins_human_review_no_auto_regression():
    # Guard ya existente (mitad verde de #8): un stage_to normal NO saca de
    # HUMAN_REVIEW_REQUIRED — el SQL lo fija con un CASE.
    src = inspect.getsource(db.update_stage)
    assert "HUMAN_REVIEW_REQUIRED" in src
    assert "CASE" in src  # la no-auto-regresión es determinista en el SQL


def test_human_review_has_explicit_release_path():
    # Vía explícita para liberar HUMAN_REVIEW (acción humana/operativa), de modo que no
    # sea un bloqueo permanente.
    assert hasattr(db, "release_human_review"), "falta vía de liberación de HUMAN_REVIEW"


def test_release_human_review_only_targets_human_review():
    # El SQL de liberación SHALL acotar su efecto a conversaciones en HUMAN_REVIEW_REQUIRED
    # (no toca conversaciones en otros estados).
    src = inspect.getsource(db.release_human_review)
    assert "current_stage = 'HUMAN_REVIEW_REQUIRED'" in src
    assert "requires_human = false" in src
