"""B4/B5 — higiene de fuentes RAG + anti over-retrieval (deterministas, sin Chroma/Groq).

B4: el contexto ensamblado para el prompt NO debe contener instrucciones internas
dirigidas al bot ("Mundo debe…", "debe pedir… antes de dar una cifra"); sí conserva
el texto respondible.
B5: el ensamblado se acota a la fuente del mejor match (+ fuentes muy cercanas), para
no mezclar temas no relacionados ("pago para sencillo" no jala paradas ni documental).
"""
from __future__ import annotations

import app.knowledge.context_builder as CB


# ── B4: strip de instrucciones internas ───────────────────────────────────────

def test_strip_removes_mundo_debe_line():
    text = (
        "El esquema de pago varía según el circuito.\n"
        "Mundo debe orientar con la referencia y pedir su ciudad antes de dar una cifra.\n"
        "Hay circuitos que pagan por kilómetro y otros por vuelta."
    )
    out = CB._strip_internal_instructions(text)
    assert "Mundo debe" not in out
    assert "antes de dar una cifra" not in out
    assert "pagan por kilómetro" in out
    assert "esquema de pago" in out


def test_strip_removes_inline_directive_sentence():
    text = "Para el proceso se piden documentos. Mundo debe evitar pedir todo el paquete desde el inicio."
    out = CB._strip_internal_instructions(text)
    assert "Mundo debe" not in out
    assert "Para el proceso se piden documentos" in out


def test_strip_keeps_clean_text():
    text = "Las vacantes son para tracto full o sencillo. El pago es por kilómetro o por vuelta."
    out = CB._strip_internal_instructions(text)
    assert out == text


def test_strip_directive_verbs():
    for d in ["debe pedir", "debe preguntar", "debe confirmar", "debe escalar", "debe marcar"]:
        text = f"Información válida del proceso. El sistema {d} algo interno."
        out = CB._strip_internal_instructions(text)
        assert d not in out
        assert "Información válida del proceso" in out


# ── B5: focus por fuente dominante (anti over-retrieval) ───────────────────────

def test_focus_keeps_only_dominant_source():
    items = [
        {"source": "01_pago_prestaciones",     "score": 0.62, "text": "pago por km"},
        {"source": "01_pago_prestaciones",     "score": 0.55, "text": "pago por vuelta"},
        {"source": "04_bases_rutas",           "score": 0.30, "text": "paradas autorizadas"},
        {"source": "02_documentos_requisitos", "score": 0.28, "text": "proceso documental"},
    ]
    out = CB._focus_items_by_source(items)
    assert {i["source"] for i in out} == {"01_pago_prestaciones"}


def test_focus_keeps_close_secondary_source():
    items = [
        {"source": "01_pago_prestaciones", "score": 0.60, "text": "a"},
        {"source": "04_bases_rutas",       "score": 0.58, "text": "b"},  # dentro del margen
    ]
    out = CB._focus_items_by_source(items)
    assert {i["source"] for i in out} == {"01_pago_prestaciones", "04_bases_rutas"}


def test_focus_preserves_order_and_dominant_items():
    items = [
        {"source": "01_pago_prestaciones", "score": 0.62, "text": "a"},
        {"source": "04_bases_rutas",       "score": 0.30, "text": "b"},
        {"source": "01_pago_prestaciones", "score": 0.55, "text": "c"},
    ]
    out = CB._focus_items_by_source(items)
    assert [i["text"] for i in out] == ["a", "c"]


def test_focus_empty():
    assert CB._focus_items_by_source([]) == []
