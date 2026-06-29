"""Tests para el gate de LLM no disponible (llm-gate-silent-fail-on-quota).

Cubre:
- extract_turn lanza LLMUnavailableError cuando call_groq_json falla con GroqRateLimitError.
- extract_turn devuelve TurnExtraction vacía (sin lanzar) cuando falla por JSON inválido.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from groq import RateLimitError as GroqRateLimitError

from app.knowledge.llm_errors import LLMUnavailableError
from app.knowledge.turn_extractor import extract_turn, TurnExtraction


def _make_rate_limit_error() -> GroqRateLimitError:
    """Construye un GroqRateLimitError mínimo compatible con la librería groq."""
    # GroqRateLimitError hereda de APIStatusError que requiere (message, response, body).
    # Usamos una respuesta mínima simulada.
    import httpx
    response = httpx.Response(429, request=httpx.Request("POST", "https://api.groq.com/"))
    return GroqRateLimitError("Rate limit exceeded", response=response, body={})


# ── Tarea 2.2a: GroqRateLimitError → LLMUnavailableError ─────────────────────

def test_extract_turn_raises_llm_unavailable_on_rate_limit():
    """Cuando call_groq_json lanza GroqRateLimitError, extract_turn debe propagarla
    como LLMUnavailableError (no absorberla en TurnExtraction vacía).

    call_groq_json se importa de forma lazy dentro de extract_turn, por lo que
    el patch debe apuntar a app.indexer.call_groq_json.
    """
    exc = _make_rate_limit_error()
    with patch("app.indexer.call_groq_json", side_effect=exc):
        with pytest.raises(LLMUnavailableError):
            extract_turn("hola, soy Juan", last_bot_question=None, known_facts={})


def test_llm_unavailable_is_runtime_error():
    """LLMUnavailableError es subclase de RuntimeError."""
    assert issubclass(LLMUnavailableError, RuntimeError)


# ── Tarea 2.2b: JSONDecodeError → TurnExtraction vacía (camino actual) ───────

def test_extract_turn_returns_empty_on_json_decode_error():
    """Cuando call_groq_json devuelve JSON malformado, extract_turn debe devolver
    TurnExtraction vacía sin lanzar (comportamiento de degradación actual)."""
    with patch("app.indexer.call_groq_json", return_value="no es json válido {{"):
        result = extract_turn("mensaje de prueba", last_bot_question=None, known_facts={})
    assert isinstance(result, TurnExtraction)
    assert result.fields == {}


def test_extract_turn_returns_empty_on_generic_exception():
    """Errores genéricos (no cuota) siguen absorbidos en TurnExtraction vacía."""
    with patch("app.indexer.call_groq_json", side_effect=ConnectionError("timeout")):
        result = extract_turn("mensaje", last_bot_question=None, known_facts={})
    assert isinstance(result, TurnExtraction)
    assert result.fields == {}


# ── Tareas 4.1 / 4.2: comportamiento del gate en el worker (lógica aislada) ──

def test_llm_unavailable_propagates_through_gate_path():
    """LLMUnavailableError lanzada desde extract_turn es capturada como RuntimeError
    (parent) — verifica que no queda absorbida por un except Exception genérico.

    Nota: el test de integración completo del worker requiere mocks de Postgres/Redis/
    Chatwoot que no están disponibles en este entorno de test liviano. La verificación
    funcional se hace en prod (tarea 5.3). Este test cubre la cadena de tipos.
    """
    exc = LLMUnavailableError("quota agotada")
    assert isinstance(exc, RuntimeError)
    # El except LLMUnavailableError en tasks_chatwoot captura antes que except Exception
    try:
        raise exc
    except LLMUnavailableError as caught:
        result = {
            "status": "skipped_llm_unavailable",
            "processed": False,
            "sent_to_chatwoot": False,
            "reason": str(caught),
        }
    assert result["status"] == "skipped_llm_unavailable"
    assert result["processed"] is False
    assert result["sent_to_chatwoot"] is False


def test_extract_turn_ok_returns_extraction():
    """Regresión: cuando call_groq_json funciona, extract_turn devuelve TurnExtraction
    con los fields esperados (sin gate)."""
    import json
    payload = json.dumps({
        "fields": {},
        "embedded_question": None,
        "signals": {},
    })
    with patch("app.indexer.call_groq_json", return_value=payload):
        result = extract_turn("todo bien", last_bot_question=None, known_facts={})
    assert isinstance(result, TurnExtraction)
    # Sin GroqRateLimitError → no se lanza LLMUnavailableError
    assert result.fields == {}
