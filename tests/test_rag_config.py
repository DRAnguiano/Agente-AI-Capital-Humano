"""rag-corpus #14 — defaults RAG centralizados en settings (fuente única).

Antes `context_builder` usaba un `RAG_TOP_K=3` hardcodeado, independiente de
`settings.TOP_K=5`. Ahora los defaults viven en `settings` y `RAG_TOP_K` hereda `TOP_K`.
"""
from __future__ import annotations

import inspect
import os

import app.settings as settings


def test_rag_defaults_exist_in_settings():
    for name in ("RAG_TOP_K", "RAG_MIN_SCORE", "RAG_MAX_CONTEXT_CHARS", "RAG_MAX_CHARS_PER_DOC"):
        assert hasattr(settings, name), f"falta {name} en settings (fuente única)"


def test_rag_top_k_defaults_to_top_k():
    # Sin override de RAG_TOP_K en el entorno, hereda TOP_K (un solo knob).
    if os.getenv("RAG_TOP_K") is None:
        assert settings.RAG_TOP_K == settings.TOP_K


def test_context_builder_reads_settings():
    import app.knowledge.context_builder as cb
    src = inspect.getsource(cb)
    assert "settings.RAG_TOP_K" in src
    assert "settings.RAG_MIN_SCORE" in src
    assert "settings.RAG_MAX_CONTEXT_CHARS" in src
