"""qwen-disable-reasoning: /no_think condicionado al modelo en generación.

Deterministas: sin Groq/LLM.
"""
from __future__ import annotations

from app.indexer import _reasoning_suppression_suffix


def test_suffix_for_qwen_reasoning_models():
    assert _reasoning_suppression_suffix("qwen/qwen3-32b") == " /no_think"
    assert _reasoning_suppression_suffix("qwen/qwen3.6-27b") == " /no_think"
    assert _reasoning_suppression_suffix("QWEN/QWEN3-32B") == " /no_think"  # case-insensitive


def test_no_suffix_for_non_qwen():
    assert _reasoning_suppression_suffix("llama-3.3-70b-versatile") == ""
    assert _reasoning_suppression_suffix("openai/gpt-oss-120b") == ""
    assert _reasoning_suppression_suffix("") == ""
    assert _reasoning_suppression_suffix(None) == ""


def test_suffix_is_appendable_and_idempotent_shape():
    # El sufijo empieza con espacio para concatenar tras el system message sin pegar.
    s = _reasoning_suppression_suffix("qwen/qwen3-32b")
    assert s.startswith(" ")
    base = "Eres Mundo."
    assert (base + s).endswith("/no_think")
