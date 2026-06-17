"""B1 — friendly grounding anti-fabrication.

El comentario friendly no debe introducir cifras/años/facts que el candidato no
dijo, y las no-respuestas ("ahorita le respondo", "espéreme") deben dar una
respuesta neutral sin llamar al LLM.
"""
from __future__ import annotations

import pytest

import app.orchestrators.knowledge_orchestrator as KO


def _friendly(monkeypatch, message, llm_reply="ok", capture=None):
    monkeypatch.setenv("KNOWLEDGE_FRIENDLY_LLM_GENERATION_ENABLED", "true")

    def fake_llm(prompt):
        if capture is not None:
            capture.append(prompt)
        return llm_reply

    monkeypatch.setattr(KO, "call_llm", fake_llm)
    return KO._answer_friendly_message(message, {"intent": "friendly_smalltalk"}, {"facts": []})


# ---------------------------------------------------------------------------
# Helpers puros
# ---------------------------------------------------------------------------

def test_helpers_no_answer_and_numbers():
    assert KO._is_no_answer("ahorita le respondo pereme")
    assert KO._is_no_answer("espéreme tantito")
    assert not KO._is_no_answer("soy de Torreón")
    assert KO._text_has_number("Cuatro años de peso")
    assert KO._text_has_number("tengo 4 años")
    assert not KO._text_has_number("Anotado, Monterrey")
    assert KO._friendly_introduces_number("Cuatro años...", "ahorita le respondo")
    assert not KO._friendly_introduces_number("Cuatro años...", "tengo 4 años")


# ---------------------------------------------------------------------------
# No-respuesta → neutral, sin LLM, sin fabricar
# ---------------------------------------------------------------------------

def test_no_answer_neutral_does_not_call_llm(monkeypatch):
    monkeypatch.setenv("KNOWLEDGE_FRIENDLY_LLM_GENERATION_ENABLED", "true")
    calls = []
    monkeypatch.setattr(KO, "call_llm", lambda p: calls.append(p) or "Cuatro años ya son experiencia de peso.")
    out = KO._answer_friendly_message("ahorita le respondo pereme", {}, {"facts": []})
    assert calls == []  # el LLM NO se llamó
    assert out["friendly_generation_skipped_reason"] == "no_answer"
    assert not KO._text_has_number(out["reply"])
    low = out["reply"].lower()
    for bad in ("cuatro", "experiencia", "perfil"):
        assert bad not in low


@pytest.mark.parametrize("msg", [
    "espéreme", "pereme", "luego le digo", "ahorita le paso el dato", "deme un momento",
])
def test_no_answer_variants_neutral(monkeypatch, msg):
    out = _friendly(monkeypatch, msg, llm_reply="Cinco años, perfil fuerte.")
    assert not KO._text_has_number(out["reply"])
    assert out["friendly_generation_skipped_reason"] == "no_answer"


# ---------------------------------------------------------------------------
# Guard anti-fabricación sobre la salida del LLM
# ---------------------------------------------------------------------------

def test_guard_discards_fabricated_number(monkeypatch):
    out = _friendly(monkeypatch, "me interesa la vacante",
                    llm_reply="Cuatro años ya son experiencia de peso para esta chamba.")
    assert "cuatro" not in out["reply"].lower()
    assert not KO._text_has_number(out["reply"])
    assert out["reply"] == KO._FRIENDLY_NEUTRAL_REPLY


def test_legit_reply_without_number_passes(monkeypatch):
    out = _friendly(monkeypatch, "soy de Monterrey", llm_reply="Anotado, Monterrey.")
    assert out["reply"] == "Anotado, Monterrey."


def test_number_echo_allowed_when_candidate_said_it(monkeypatch):
    # El candidato sí dijo "4 años" → el bot puede reflejarlo (no es fabricación).
    out = _friendly(monkeypatch, "tengo 4 años de experiencia",
                    llm_reply="Cuatro años son buena experiencia.")
    assert out["reply"] == "Cuatro años son buena experiencia."


# ---------------------------------------------------------------------------
# El prompt ya no induce la fabricación
# ---------------------------------------------------------------------------

def test_prompt_drops_fabrication_fewshot(monkeypatch):
    cap: list[str] = []
    _friendly(monkeypatch, "me interesa la vacante", llm_reply="ok", capture=cap)
    prompt = cap[0]
    assert "Cuatro años ya son experiencia" not in prompt
    assert "no haya dicho" in prompt  # regla anti-fabricación presente


# ---------------------------------------------------------------------------
# Copy: el LLM a veces envuelve toda la respuesta en comillas ("Laredo, anotado.")
# → _clean_reply quita UN nivel de comillas envolventes (rag-corpus item 124).
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ('"Laredo, anotado."', "Laredo, anotado."),
    ("“Perfecto, lo dejo registrado.”", "Perfecto, lo dejo registrado."),
    ("«Gracias por avisar.»", "Gracias por avisar."),
    ("'Va, seguimos.'", "Va, seguimos."),
])
def test_clean_reply_strips_wrapping_quotes(raw, expected):
    assert KO._clean_reply(raw) == expected


def test_clean_reply_keeps_internal_quotes():
    # No debe tocar comillas internas legítimas ni apóstrofes de contracción.
    assert KO._clean_reply('La ruta "MTY-NLD" sale temprano.') == 'La ruta "MTY-NLD" sale temprano.'
    assert KO._clean_reply("Para el corredor d'México hay vuelta.") == "Para el corredor d'México hay vuelta."
