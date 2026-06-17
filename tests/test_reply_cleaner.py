"""rag-corpus #13 — cleaner de respuesta LLM unificado.

`reply_cleaner.clean_reply` es el punto único; el orquestador (`_clean_reply`) y el
endpoint (`_clean_llm_answer`) delegan en él. Tests deterministas, sin Groq/LLM.
"""
from __future__ import annotations

import app.orchestrators.knowledge_orchestrator as KO
from app.knowledge.reply_cleaner import clean_reply

_SAMPLES = [
    '"Laredo, anotado."',
    "Te explico el pago. ¿Tienes alguna otra duda?",
    "Listo.�",
    "<think>razono algo</think>Perfecto, registrado.",
    "Respuesta normal sin relleno.",
    "",
]


def test_orchestrator_delegates_to_clean_reply():
    for s in _SAMPLES:
        assert KO._clean_reply(s) == clean_reply(s)


def test_clean_reply_unified_behaviors():
    # comillas envolventes (#19) — un solo nivel
    assert clean_reply('"Laredo, anotado."') == "Laredo, anotado."
    # sanitiza el carácter de reemplazo U+FFFD
    assert "�" not in clean_reply("hola�mundo")
    # quita think-tags
    assert clean_reply("<think>x</think>Listo.") == "Listo."
    # recorta cierre genérico
    assert clean_reply("Te explico. ¿Tienes alguna otra duda?").rstrip() == "Te explico."
    # no toca comillas internas legítimas
    assert clean_reply('La ruta "MTY-NLD" sale temprano.') == 'La ruta "MTY-NLD" sale temprano.'


def test_clean_reply_idempotent():
    for s in _SAMPLES:
        once = clean_reply(s)
        assert clean_reply(once) == once
