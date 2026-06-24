"""funnel-and-note-redesign — Nota IA administrativa, rama ESCUELITA.

La nota de un candidato de escuelita (experiencia no objetivo: torton/rabón/reparto)
debe ser administrativa para Capital Humano: sin lenguaje técnico (Embudo/Canal/Riesgo/
Requiere humano), cabecera por escenario, y mostrar solo lo mínimo (experiencia no objetivo
+ licencia B/E). Determinista. Migración incremental: solo la rama escuelita cambia; el resto
del formato técnico sigue hasta migrarse.
"""
from __future__ import annotations

from app.chatwoot_note_sync import render_candidate_note


def _nota_escuelita(license_cat: str | None = None) -> str:
    facts = {"experience.non_target_vehicle_type": "torton"}
    if license_cat:
        facts["license.category"] = license_cat
    ctx = {
        "lead": {"display_name": "David Ramos"},
        "conversation": {"channel": "whatsapp"},
        "facts": facts,
        "last_message": {"message": "manejo torton"},
    }
    return render_candidate_note(ctx, ["bot_activo", "considerar_escuelita_transmontes"])


def test_cabecera_por_escenario_escuelita():
    nota = _nota_escuelita()
    assert nota.startswith("🤖 Nota IA")
    assert "escuelita" in nota.lower()


def test_sin_lenguaje_tecnico():
    nota = _nota_escuelita()
    assert "📍 Embudo" not in nota
    assert "Canal:" not in nota
    assert "Requiere humano" not in nota
    assert "Etapa:" not in nota


def test_lenguaje_administrativo():
    nota = _nota_escuelita()
    assert "📌 Estado del candidato" in nota
    assert "Escuelita Transmontes" in nota
    assert "Requiere Agente: Sí" in nota


def test_muestra_solo_minimo_escuelita():
    # experiencia no objetivo + licencia; NO apto/cartas/ciudad como campos principales
    nota = _nota_escuelita()
    assert "torton" in nota.lower()
    assert "Apto médico" not in nota
    assert "Cartas/documentos" not in nota


def test_sin_licencia_be_pide_confirmar():
    nota = _nota_escuelita(license_cat=None)
    assert "Falta confirmar" in nota
    assert "B o E" in nota


def test_con_licencia_be_valora_escuelita():
    nota = _nota_escuelita(license_cat="E")
    # con B/E la siguiente acción es valorar/canalizar, no pedir licencia
    assert "Valorar Escuelita Transmontes" in nota


def test_no_renderiza_label_raw():
    nota = _nota_escuelita()
    assert "considerar_escuelita_transmontes" not in nota
    assert "🏷️ Labels" not in nota
