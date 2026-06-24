"""Tests for business_route_schema.py — pure dataclasses, no LLM, no DB."""
import pytest
from app.knowledge.business_route_schema import (
    AmbiguityFlag,
    BusinessRouteOutput,
    BusinessSignal,
    ExplicitFact,
    RequestedInfoItem,
    BUSINESS_SIGNALS,
    VALID_VEHICLE_TYPES,
)


class TestRequestedInfoItem:
    def test_minimal(self):
        item = RequestedInfoItem(category="payment_per_km")
        assert item.category == "payment_per_km"
        assert item.evidence == ""

    def test_with_evidence(self):
        item = RequestedInfoItem(category="route_details", evidence="rutas de Coahuila")
        assert item.evidence == "rutas de Coahuila"

    def test_to_dict(self):
        item = RequestedInfoItem(category="salary", evidence="sueldo mensual")
        d = item.to_dict()
        assert d == {"category": "salary", "evidence": "sueldo mensual"}


class TestExplicitFact:
    def test_vehicle_type_full(self):
        fact = ExplicitFact(field="experience.vehicle_type", value="full", evidence="manejo full")
        assert fact.value == "full"
        assert fact.evidence == "manejo full"
        assert fact.confidence == 1.0
        assert fact.needs_confirmation is False

    def test_vehicle_type_sencillo(self):
        fact = ExplicitFact(
            field="experience.vehicle_type",
            value="sencillo",
            evidence="para sencillo",
            confidence=0.95,
        )
        assert fact.value == "sencillo"
        assert fact.confidence == 0.95

    def test_city_fact(self):
        fact = ExplicitFact(field="candidate.city", value="Monterrey", evidence="soy de Monterrey")
        assert fact.field == "candidate.city"
        assert fact.needs_confirmation is False

    def test_needs_confirmation_flag(self):
        fact = ExplicitFact(
            field="candidate.city",
            value="Torreón",
            evidence="soy de Torreón",
            needs_confirmation=True,
        )
        assert fact.needs_confirmation is True

    def test_to_dict(self):
        fact = ExplicitFact(
            field="experience.vehicle_type",
            value="full",
            evidence="manejo full",
            confidence=0.9,
        )
        d = fact.to_dict()
        assert d["field"] == "experience.vehicle_type"
        assert d["value"] == "full"
        assert d["evidence"] == "manejo full"
        assert d["confidence"] == 0.9
        assert d["needs_confirmation"] is False


class TestBusinessSignal:
    def test_all_signals_in_catalog(self):
        for name in BUSINESS_SIGNALS:
            sig = BusinessSignal(name=name, evidence="test evidence")
            assert sig.name == name

    def test_defaults(self):
        sig = BusinessSignal(name="objetivo_full_sencillo")
        assert sig.evidence == ""
        assert sig.confidence == 1.0

    def test_to_dict(self):
        sig = BusinessSignal(name="pago_condiciones", evidence="km cargado", confidence=0.9)
        d = sig.to_dict()
        assert d == {"name": "pago_condiciones", "evidence": "km cargado", "confidence": 0.9}


class TestAmbiguityFlag:
    def test_minimal(self):
        flag = AmbiguityFlag(name="vehicle_type_ambiguous")
        assert flag.name == "vehicle_type_ambiguous"
        assert flag.evidence == ""

    def test_with_evidence(self):
        flag = AmbiguityFlag(name="vehicle_type_ambiguous", evidence="5ta rueda")
        assert flag.evidence == "5ta rueda"

    def test_to_dict(self):
        flag = AmbiguityFlag(name="multimedia_no_ocr", evidence="<Multimedia omitido>")
        d = flag.to_dict()
        assert d == {"name": "multimedia_no_ocr", "evidence": "<Multimedia omitido>"}


class TestBusinessRouteOutput:
    def test_safe_empty_no_error(self):
        out = BusinessRouteOutput.safe_empty()
        assert out.shadow_error == ""
        assert out.requires_human is False
        assert out.business_signals == []
        assert out.explicit_facts == {}

    def test_safe_empty_with_error(self):
        out = BusinessRouteOutput.safe_empty("json_parse_error: something")
        assert out.shadow_error == "json_parse_error: something"

    def test_has_signal_true(self):
        out = BusinessRouteOutput()
        out.business_signals.append(BusinessSignal(name="pago_condiciones"))
        assert out.has_signal("pago_condiciones") is True

    def test_has_signal_false(self):
        out = BusinessRouteOutput()
        assert out.has_signal("pago_condiciones") is False

    def test_signal_names(self):
        out = BusinessRouteOutput()
        out.business_signals = [
            BusinessSignal(name="pago_condiciones"),
            BusinessSignal(name="ubicacion_base_traslado"),
        ]
        names = out.signal_names()
        assert "pago_condiciones" in names
        assert "ubicacion_base_traslado" in names

    def test_flag_names(self):
        out = BusinessRouteOutput()
        out.ambiguity_flags = [AmbiguityFlag(name="vehicle_type_ambiguous")]
        assert "vehicle_type_ambiguous" in out.flag_names()

    def test_to_dict_structure(self):
        out = BusinessRouteOutput()
        out.business_signals.append(BusinessSignal(name="objetivo_full_sencillo", evidence="sencillo"))
        out.explicit_facts["experience.vehicle_type"] = ExplicitFact(
            field="experience.vehicle_type", value="sencillo", evidence="sencillo"
        )
        d = out.to_dict()
        assert isinstance(d["business_signals"], list)
        assert d["business_signals"][0]["name"] == "objetivo_full_sencillo"
        assert isinstance(d["explicit_facts"], dict)
        assert d["explicit_facts"]["experience.vehicle_type"]["value"] == "sencillo"
        assert d["requires_human"] is False
        assert d["shadow_error"] == ""

    def test_to_dict_complete_keys(self):
        out = BusinessRouteOutput.safe_empty("test")
        d = out.to_dict()
        expected_keys = {
            "conversational_intents", "requested_info", "explicit_facts",
            "business_signals", "ambiguity_flags", "requires_human",
            "profile_context_action", "policy_answer_keys", "rag_needed",
            "validation_errors", "shadow_error",
        }
        assert set(d.keys()) == expected_keys

    def test_valid_vehicle_types(self):
        assert "full" in VALID_VEHICLE_TYPES
        assert "sencillo" in VALID_VEHICLE_TYPES
        assert "torton" not in VALID_VEHICLE_TYPES
        assert "quinta rueda" not in VALID_VEHICLE_TYPES
