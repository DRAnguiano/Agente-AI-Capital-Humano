"""Contrato del renderer de la Nota IA — tests RED primero.

Estos tests verifican el formato objetivo definido en:
  openspec/changes/chatwoot-ai-note-contract/specs/chatwoot-ai-note/spec.md

Con el código actual deben FALLAR los tests marcados con # FAILS.
Cuando la implementación esté completa, todos deben pasar.
No llaman a DB, Chatwoot ni LLM.
"""
from __future__ import annotations

import pytest

from app.chatwoot_note_sync import render_candidate_note


# ── helpers ───────────────────────────────────────────────────────────────────

def _ctx(
    facts: dict | None = None,
    lead: dict | None = None,
    last_message: str | None = None,
    channel: str | None = None,
) -> dict:
    return {
        "lead": lead or {},
        "conversation": {"channel": channel or "whatsapp"},
        "facts": facts or {},
        "last_message": {"message": last_message or ""} if last_message else {},
    }


def _nota(
    facts: dict | None = None,
    labels: list[str] | None = None,
    lead: dict | None = None,
    last_message: str | None = None,
) -> str:
    return render_candidate_note(
        _ctx(facts=facts, lead=lead, last_message=last_message),
        labels or [],
    )


FULL_FACTS = {
    "experience.vehicle_type": "full",
    "experience.years": "10 años",
    "license.category": "E",
    "medical.apto_status": "vigente",
    "documents.labor_letters_status": "available",
    "candidate.city": "Torreón",
    "candidate.vacancy_accepted": "sí",
}


# ── Secciones prohibidas — FAILS con código actual ───────────────────────────

class TestSeccionesProhibidas:
    def test_nota_sin_interes_en_pago(self):  # FAILS
        nota = _nota()
        assert "Interés en pago" not in nota
        assert "pago/compensación" not in nota

    def test_nota_sin_labels_en_cuerpo(self):  # FAILS
        nota = _nota(labels=["bot_activo", "falta_licencia"])
        assert "🏷️ Labels" not in nota
        assert "Labels" not in nota.split("⏭️")[0]   # no en el cuerpo principal

    def test_nota_sin_disponibilidad_actual(self):  # FAILS
        nota = _nota()
        assert "Disponibilidad actual" not in nota

    def test_nota_sin_disponibilidad_para_acudir_por_defecto(self):
        # "Disponibilidad para acudir" tampoco debe aparecer por defecto
        nota = _nota()
        assert "Disponibilidad para acudir" not in nota

    def test_nota_sin_memoria_breve(self):  # FAILS
        nota = _nota(lead={"memory_summary": "Candidato interesado en full"})
        assert "🧠 Memoria breve" not in nota

    def test_nota_sin_memory_summary_crudo(self):  # FAILS
        # El texto del memory_summary no debe aparecer aunque sea real
        nota = _nota(lead={"memory_summary": "Candidato interesado en full"})
        assert "Candidato interesado en full" not in nota


# ── next_best_action una sola vez — FAILS con código actual ──────────────────

class TestSiguienteAccionUnica:
    def test_next_action_aparece_exactamente_una_vez(self):  # FAILS
        nota = _nota(lead={"next_best_action": "Confirmar tipo de unidad"})
        assert nota.count("Confirmar tipo de unidad") == 1

    def test_no_existe_seccion_accion_duplicada(self):  # FAILS
        nota = _nota(lead={"next_best_action": "Preguntar por licencia"})
        # "Acción:" antes de "👤 Contacto" no debe existir
        contacto_pos = nota.find("👤 Contacto")
        accion_pos = nota.find("Acción:")
        assert accion_pos == -1 or accion_pos > contacto_pos, (
            "'Acción:' no debe aparecer en la cabecera antes de 👤 Contacto"
        )

    def test_seccion_siguiente_accion_existe(self):
        nota = _nota(lead={"next_best_action": "Continuar flujo"})
        assert "⏭️ Siguiente acción" in nota


# ── Secciones obligatorias — deben existir ──────────────────────────────────

class TestSeccionesObligatorias:
    def test_contacto_presente(self):
        nota = _nota()
        assert "👤 Contacto" in nota

    def test_perfil_confirmado_presente(self):  # FAILS
        # Nombre canónico obligatorio: "Perfil confirmado", nunca "Perfil detectado".
        nota = _nota()
        assert "📋 Perfil confirmado" in nota
        assert "📋 Perfil detectado" not in nota

    def test_embudo_presente(self):
        nota = _nota()
        assert "📍 Embudo" in nota

    def test_siguiente_accion_presente(self):
        nota = _nota()
        assert "⏭️ Siguiente acción" in nota

    def test_ultimo_mensaje_presente(self):
        nota = _nota(last_message="manejo sencillo")
        assert "manejo sencillo" in nota

    def test_temperatura_ausente(self):
        nota = _nota()
        assert "Temperatura" not in nota
        assert "🌡️" not in nota


# ── Facts confirmados aparecen, facts vacíos muestran Pendiente ──────────────

class TestFactsConfirmados:
    def test_vehicle_type_full_renderiza(self):
        nota = _nota(facts={"experience.vehicle_type": "full"})
        assert "Full" in nota or "full" in nota.lower()

    def test_vehicle_type_sencillo_renderiza(self):
        nota = _nota(facts={"experience.vehicle_type": "sencillo"})
        assert "Sencillo" in nota or "sencillo" in nota.lower()

    def test_campo_vacio_muestra_pendiente(self):
        nota = _nota(facts={})
        assert "Pendiente" in nota

    def test_ciudad_confirmada_aparece(self):
        nota = _nota(facts={"candidate.city": "Monterrey"})
        assert "Monterrey" in nota

    def test_no_inventa_ciudad_cuando_vacia(self):
        nota = _nota(facts={})
        for ciudad in ("Monterrey", "Torreón", "Gómez Palacio", "CDMX"):
            assert ciudad not in nota


# ── Vigencias independientes: licencia usa license_exp_text ──────────────────

class TestVigenciaIndependiente:
    def test_vigencia_licencia_no_cruza_con_apto(self):  # FAILS
        # Bug actual: la línea Licencia muestra apto_exp_text guardado por license_exp_text.
        nota = _nota(facts={
            "license.category": "E",
            "license.expiration_text": "31/12/2027",
            "medical.apto_status": "vigente",
            "medical.apto_expiration_text": "30/06/2026",
        })
        licencia_line = next(l for l in nota.splitlines() if l.startswith("Licencia:"))
        apto_line = next(l for l in nota.splitlines() if l.startswith("Apto médico:"))
        assert "31/12/2027" in licencia_line
        assert "30/06/2026" not in licencia_line
        assert "30/06/2026" in apto_line

    def test_licencia_sin_vigencia_no_muestra_la_del_apto(self):
        # Sin license.expiration_text, la línea Licencia no muestra ninguna vigencia.
        nota = _nota(facts={
            "license.category": "E",
            "medical.apto_status": "vigente",
            "medical.apto_expiration_text": "30/06/2026",
        })
        licencia_line = next(l for l in nota.splitlines() if l.startswith("Licencia:"))
        assert "30/06/2026" not in licencia_line


# ── Multimedia no produce facts ───────────────────────────────────────────────

class TestMultimediaNoFacts:
    def test_multimedia_no_genera_vehicle_type(self):
        nota = _nota(
            facts={},
            last_message="<Multimedia omitido>",
        )
        # No hay vehicle_type real, no debe aparecer Full/Sencillo como confirmado
        assert "experience.vehicle_type" not in nota

    def test_multimedia_muestra_pendiente_en_tipo_unidad(self):
        nota = _nota(facts={}, last_message="<Multimedia omitido>")
        assert "Pendiente" in nota


# ── B1 y reingreso muestran revisión humana ──────────────────────────────────

class TestRevisionHumana:
    def test_b1_muestra_requiere_humano(self):
        nota = _nota(
            lead={"requires_human": True},
            labels=["considerar_operador_b1", "requiere_agente"],
        )
        assert "Sí" in nota   # "Requiere humano: Sí"

    def test_reingreso_muestra_requiere_humano(self):
        nota = _nota(
            lead={"requires_human": True},
            labels=["reingreso_verificar"],
        )
        assert "Sí" in nota

    def test_sin_señal_humana_requiere_no(self):
        nota = _nota(lead={"requires_human": False})
        assert "No" in nota   # "Requiere humano: No"


# ── Labels deprecadas no aparecen ────────────────────────────────────────────

class TestLabelsDeprecadas:
    def test_cecati_raw_no_aparece(self):
        nota = _nota(labels=["cecati_sugerido"])
        lines = [l.lower() for l in nota.splitlines()]
        # "cecati" puede estar en "CECATI sugerido" (display), pero no como label raw en sección Labels
        assert "🏷️ labels" not in nota.lower()

    def test_escuelita_raw_no_aparece_como_label(self):
        nota = _nota(labels=["considerar_escuelita_transmontes"])
        # No debe haber una línea que diga "escuelita" como label sin formato
        assert "🏷️ Labels" not in nota

    def test_disponible_acudir_no_aparece(self):
        nota = _nota(labels=["bot_activo"])
        assert "disponible_acudir" not in nota


# ── Sección condicional ⚠️ Pendientes ────────────────────────────────────────

class TestSeccionCondicional:
    def test_sin_bloqueo_pendientes_ausente(self):
        # Perfil completo → sin bloqueo → no debe aparecer ⚠️
        nota = _nota(facts=FULL_FACTS, lead={"funnel_stage": "profile_ready"})
        assert "⚠️" not in nota

    def test_con_bloqueo_pendientes_presente(self):
        # Sin tipo de unidad → bloqueo → debe aparecer ⚠️ o el bloqueo en Embudo
        nota = _nota(facts={})
        # El bloqueo debe estar indicado (ya sea en ⚠️ o en "Bloqueo actual:")
        assert "Bloqueo actual:" in nota


# ── Contrato de formato completo ─────────────────────────────────────────────

class TestFormatoCompleto:
    def test_orden_de_secciones(self):
        nota = _nota(
            facts=FULL_FACTS,
            last_message="manejo full",
            lead={"next_best_action": "Agendar entrevista"},
        )
        # Orden obligatorio: Último mensaje → Contacto → Perfil → Embudo → Siguiente acción
        pos_msg = nota.find("Último mensaje")
        pos_contacto = nota.find("👤 Contacto")
        pos_perfil = nota.find("📋 Perfil")
        pos_embudo = nota.find("📍 Embudo")
        pos_accion = nota.find("⏭️ Siguiente acción")

        assert pos_msg < pos_contacto < pos_perfil < pos_embudo < pos_accion, (
            "Las secciones de la nota no están en el orden esperado"
        )

    def test_cabecera_correcta(self):
        nota = _nota()
        assert nota.startswith("🤖 Nota IA: Seguimiento de candidato")

    def test_next_action_en_ultima_seccion(self):
        nota = _nota(lead={"next_best_action": "Preguntar por ciudad"})
        siguiente_pos = nota.find("⏭️ Siguiente acción")
        accion_pos = nota.find("Preguntar por ciudad")
        assert siguiente_pos != -1
        assert accion_pos > siguiente_pos, (
            "next_best_action debe estar DENTRO de ⏭️ Siguiente acción"
        )
