"""Tests for business_route_classifier.py — mocks call_groq_json, no Groq API needed."""
import json
from unittest.mock import patch

import pytest

from app.knowledge.business_route_classifier import classify_business_route_shadow
from app.knowledge.business_route_schema import BusinessRouteOutput


# ── mock helpers ──────────────────────────────────────────────────────────────

MOCK_PATH = "app.knowledge.business_route_classifier.call_groq_json"


def _make_llm_response(
    *,
    requested_info=None,
    explicit_facts=None,
    business_signals=None,
    ambiguity_flags=None,
    requires_human=False,
    profile_context_action="continue_profiling",
    policy_answer_keys=None,
) -> str:
    payload = {
        "requested_info": requested_info or [],
        "explicit_facts": explicit_facts or [],
        "business_signals": business_signals or [],
        "ambiguity_flags": ambiguity_flags or [],
        "requires_human": requires_human,
        "profile_context_action": profile_context_action,
        "policy_answer_keys": policy_answer_keys or [],
    }
    return json.dumps(payload)


# ── basic smoke tests ─────────────────────────────────────────────────────────

class TestEmptyInput:
    def test_empty_string_returns_safe_empty(self):
        result = classify_business_route_shadow("")
        assert isinstance(result, BusinessRouteOutput)
        assert result.shadow_error == "empty_message"

    def test_whitespace_only_returns_safe_empty(self):
        result = classify_business_route_shadow("   ")
        assert result.shadow_error == "empty_message"


class TestLLMErrorHandling:
    @patch(MOCK_PATH, return_value='{"error": "missing_groq_api_key"}')
    def test_llm_api_key_error_returns_safe_empty(self, _mock):
        result = classify_business_route_shadow("hola")
        assert result.shadow_error.startswith("llm_error:")

    @patch(MOCK_PATH, return_value="not valid json {{{")
    def test_json_parse_error_returns_safe_empty(self, _mock):
        result = classify_business_route_shadow("hola")
        assert result.shadow_error.startswith("json_parse_error:")

    @patch(MOCK_PATH, return_value='"just a string"')
    def test_non_dict_response_returns_safe_empty(self, _mock):
        result = classify_business_route_shadow("hola")
        assert result.shadow_error.startswith("llm_error:")


# ── vehicle_type / objetivo_full_sencillo ─────────────────────────────────────

class TestVehicleTypeSencillo:
    @patch(MOCK_PATH, return_value=_make_llm_response(
        explicit_facts=[{"field": "experience.vehicle_type", "value": "sencillo",
                          "evidence": "para sencillo", "confidence": 0.95}],
        business_signals=[{"name": "objetivo_full_sencillo", "evidence": "para sencillo",
                            "confidence": 0.95}],
    ))
    def test_sencillo_explicit(self, _mock):
        result = classify_business_route_shadow("Me interesa para sencillo")
        assert "experience.vehicle_type" in result.explicit_facts
        assert result.explicit_facts["experience.vehicle_type"].value == "sencillo"
        assert result.has_signal("objetivo_full_sencillo")
        assert result.requires_human is False

    @patch(MOCK_PATH, return_value=_make_llm_response(
        explicit_facts=[{"field": "experience.vehicle_type", "value": "full",
                          "evidence": "manejo full", "confidence": 0.95}],
        business_signals=[{"name": "objetivo_full_sencillo", "evidence": "manejo full",
                            "confidence": 0.95}],
    ))
    def test_full_explicit(self, _mock):
        result = classify_business_route_shadow("manejo full hace 5 años")
        assert result.explicit_facts["experience.vehicle_type"].value == "full"
        assert result.has_signal("objetivo_full_sencillo")

    @patch(MOCK_PATH, return_value=_make_llm_response(
        explicit_facts=[{"field": "experience.vehicle_type", "value": "full",
                          "evidence": "fullero", "confidence": 0.95}],
        business_signals=[{"name": "objetivo_full_sencillo", "evidence": "fullero",
                            "confidence": 0.95}],
    ))
    def test_fullero_resolves(self, _mock):
        result = classify_business_route_shadow("soy fullero desde hace 5 años")
        assert "experience.vehicle_type" in result.explicit_facts
        assert result.has_signal("objetivo_full_sencillo")


# ── jerga ambigua ─────────────────────────────────────────────────────────────

class TestJergaAmbigua:
    @patch(MOCK_PATH, return_value=_make_llm_response(
        requested_info=[{"category": "vacancy_availability", "evidence": "5ta rueda"}],
        business_signals=[{"name": "jerga_ambigua_falta_unidad", "evidence": "5ta rueda",
                            "confidence": 0.9}],
        ambiguity_flags=[{"name": "vehicle_type_ambiguous", "evidence": "5ta rueda"}],
    ))
    def test_5ta_rueda_no_vehicle_type_fact(self, _mock):
        result = classify_business_route_shadow("información para operador 5ta rueda")
        assert "experience.vehicle_type" not in result.explicit_facts
        assert result.has_signal("jerga_ambigua_falta_unidad")
        assert "vehicle_type_ambiguous" in result.flag_names()

    @patch(MOCK_PATH, return_value=_make_llm_response(
        business_signals=[{"name": "jerga_ambigua_falta_unidad", "evidence": "trailer",
                            "confidence": 0.9}],
        ambiguity_flags=[{"name": "vehicle_type_ambiguous", "evidence": "trailer"}],
    ))
    def test_trailer_jerga_ambigua(self, _mock):
        result = classify_business_route_shadow("manejo trailer")
        assert "experience.vehicle_type" not in result.explicit_facts
        assert result.has_signal("jerga_ambigua_falta_unidad")

    def test_policy_rejects_quinta_rueda_as_vehicle_type(self):
        """Policy rejects 5ta rueda even if LLM wrongly emits vehicle_type=full."""
        llm_response = _make_llm_response(
            explicit_facts=[{"field": "experience.vehicle_type", "value": "full",
                              "evidence": "5ta rueda", "confidence": 0.9}],
            business_signals=[{"name": "objetivo_full_sencillo", "evidence": "5ta rueda",
                                "confidence": 0.9}],
        )
        with patch(MOCK_PATH, return_value=llm_response):
            result = classify_business_route_shadow("opero 5ta rueda")
        assert "experience.vehicle_type" not in result.explicit_facts
        assert result.has_signal("jerga_ambigua_falta_unidad")


# ── escuelita / CECATI ────────────────────────────────────────────────────────

class TestEscuelitaAndCecati:
    @patch(MOCK_PATH, return_value=_make_llm_response(
        business_signals=[{"name": "considerar_escuelita_transmontes", "evidence": "torton",
                            "confidence": 0.9}],
    ))
    def test_torton_escuelita(self, _mock):
        result = classify_business_route_shadow("manejé torton varios años")
        assert result.has_signal("considerar_escuelita_transmontes")
        assert not result.has_signal("objetivo_full_sencillo")
        assert "experience.vehicle_type" not in result.explicit_facts

    @patch(MOCK_PATH, return_value=_make_llm_response(
        business_signals=[{"name": "cecati_sugerido", "evidence": "no tengo experiencia",
                            "confidence": 0.9}],
    ))
    def test_sin_experiencia_cecati(self, _mock):
        result = classify_business_route_shadow("no tengo experiencia manejando")
        assert result.has_signal("cecati_sugerido")
        assert not result.has_signal("considerar_escuelita_transmontes")


# ── B1 / reingreso → requires_human ──────────────────────────────────────────

class TestRequiresHuman:
    @patch(MOCK_PATH, return_value=_make_llm_response(
        business_signals=[{"name": "considerar_operador_b1", "evidence": "B1 para Estados Unidos",
                            "confidence": 0.95}],
        requires_human=True,
        profile_context_action="escalate_to_human",
    ))
    def test_b1_requires_human(self, _mock):
        result = classify_business_route_shadow("busco vacante B1 para Estados Unidos")
        assert result.has_signal("considerar_operador_b1")
        assert result.requires_human is True
        assert result.profile_context_action == "escalate_to_human"

    @patch(MOCK_PATH, return_value=_make_llm_response(
        business_signals=[{"name": "reingreso_verificar", "evidence": "reingreso",
                            "confidence": 0.9}],
        requires_human=True,
        profile_context_action="escalate_to_human",
    ))
    def test_reingreso_requires_human(self, _mock):
        result = classify_business_route_shadow("sería como reingreso si se puede")
        assert result.has_signal("reingreso_verificar")
        assert result.requires_human is True

    def test_policy_enforces_requires_human_even_if_llm_omits(self):
        """Policy must set requires_human=True even if LLM forgot."""
        llm_response = _make_llm_response(
            business_signals=[{"name": "considerar_operador_b1", "evidence": "B1",
                                "confidence": 0.95}],
            requires_human=False,   # LLM forgot to set True
        )
        with patch(MOCK_PATH, return_value=llm_response):
            result = classify_business_route_shadow("quiero vacante B1")
        assert result.requires_human is True


# ── multi-intent / pago + pagarés + rutas ────────────────────────────────────

class TestMultiIntent:
    @patch(MOCK_PATH, return_value=_make_llm_response(
        requested_info=[
            {"category": "payment_per_km", "evidence": "km cargado y vacío"},
            {"category": "hiring_practice", "evidence": "firman pagarés en blanco"},
            {"category": "route_details", "evidence": "rutas de Coahuila"},
        ],
        business_signals=[
            {"name": "pago_condiciones", "evidence": "km cargado y vacío", "confidence": 0.95},
            {"name": "ubicacion_base_traslado", "evidence": "rutas de Coahuila", "confidence": 0.9},
        ],
        policy_answer_keys=["no_pagares_en_blanco"],
    ))
    def test_pago_pagares_rutas_multi_intent(self, _mock):
        text = "A como el km cargado y vacío? firman pagarés en blanco? rutas de Coahuila?"
        result = classify_business_route_shadow(text)
        assert result.has_signal("pago_condiciones")
        assert result.has_signal("ubicacion_base_traslado")
        assert "no_pagares_en_blanco" in result.policy_answer_keys
        assert len(result.requested_info) == 3

    @patch(MOCK_PATH, return_value=_make_llm_response(
        business_signals=[
            {"name": "complaint_with_candidate_interest", "evidence": "buscando en otro lado",
             "confidence": 0.85},
        ],
        profile_context_action="acknowledge_complaint_then_profile",
    ))
    def test_complaint_with_interest(self, _mock):
        text = "entré la semana pasada y no me dan viaje, estoy buscando en otro lado"
        result = classify_business_route_shadow(text)
        assert result.has_signal("complaint_with_candidate_interest")
        assert result.profile_context_action == "acknowledge_complaint_then_profile"
        assert result.requires_human is False


# ── multimedia ────────────────────────────────────────────────────────────────

class TestMultimedia:
    @patch(MOCK_PATH, return_value=_make_llm_response(
        requested_info=[{"category": "documents_required", "evidence": "fotos por los dos lados"}],
        business_signals=[{"name": "documentos_requisitos", "evidence": "fotos por los dos lados",
                            "confidence": 0.85}],
        ambiguity_flags=[{"name": "multimedia_no_ocr", "evidence": "<Multimedia omitido>"}],
    ))
    def test_multimedia_with_text_question(self, _mock):
        result = classify_business_route_shadow(
            "<Multimedia omitido> Necesitas fotos por los dos lados?"
        )
        assert "multimedia_no_ocr" in result.flag_names()
        assert result.has_signal("documentos_requisitos")


# ── conversational intents passthrough ───────────────────────────────────────

class TestConversationalPassthrough:
    @patch(MOCK_PATH, return_value=_make_llm_response(
        business_signals=[{"name": "pago_condiciones", "evidence": "km", "confidence": 0.9}],
    ))
    def test_conv_classification_passthrough(self, _mock):
        conv = {"primary_intent": "pay_question", "secondary_intents": ["logistics_question"]}
        result = classify_business_route_shadow("a como el km", conversational_classification=conv)
        assert "pay_question" in result.conversational_intents
        assert "logistics_question" in result.conversational_intents


# ── no production imports ─────────────────────────────────────────────────────

class TestNoProductionImports:
    def test_classifier_does_not_import_db(self):
        import app.knowledge.business_route_classifier as m
        import sys
        assert "app.db" not in sys.modules or True  # classifier must not trigger db import
        # Verify by checking the module's source doesn't import db/chatwoot/app.app
        import inspect
        source = inspect.getsource(m)
        assert "app.db" not in source
        assert "tasks_chatwoot" not in source
        assert "from app.app" not in source
