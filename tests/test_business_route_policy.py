"""Tests for business_route_policy.py — deterministic, no LLM, no DB."""
import pytest
from app.knowledge.business_route_schema import (
    AmbiguityFlag,
    BusinessRouteOutput,
    BusinessSignal,
    ExplicitFact,
)
from app.knowledge.business_route_policy import validate_business_output


# ── helpers ───────────────────────────────────────────────────────────────────

def _output_with_vehicle_fact(value: str, evidence: str, confidence: float = 0.95) -> BusinessRouteOutput:
    out = BusinessRouteOutput()
    out.explicit_facts["experience.vehicle_type"] = ExplicitFact(
        field="experience.vehicle_type",
        value=value,
        evidence=evidence,
        confidence=confidence,
    )
    return out


def _output_with_signal(name: str, confidence: float = 0.9) -> BusinessRouteOutput:
    out = BusinessRouteOutput()
    out.business_signals.append(BusinessSignal(name=name, evidence="evidencia", confidence=confidence))
    return out


# ── vehicle_type validation ───────────────────────────────────────────────────

class TestVehicleTypeFact:
    def test_sencillo_explicit_kept(self):
        text = "Me interesa para sencillo"
        out = _output_with_vehicle_fact("sencillo", "para sencillo")
        result = validate_business_output(out, text)
        assert "experience.vehicle_type" in result.explicit_facts
        assert result.explicit_facts["experience.vehicle_type"].value == "sencillo"

    def test_full_explicit_kept(self):
        text = "manejo full"
        out = _output_with_vehicle_fact("full", "manejo full")
        result = validate_business_output(out, text)
        assert "experience.vehicle_type" in result.explicit_facts

    def test_fullero_resolves_to_full(self):
        text = "soy fullero desde hace 5 años"
        out = _output_with_vehicle_fact("full", "fullero")
        result = validate_business_output(out, text)
        assert "experience.vehicle_type" in result.explicit_facts

    def test_quinta_rueda_rejected_and_ambiguity_added(self):
        text = "opero quinta rueda"
        out = _output_with_vehicle_fact("full", "quinta rueda")
        result = validate_business_output(out, text)
        # fact rejected
        assert "experience.vehicle_type" not in result.explicit_facts
        # auto-correction: jerga signal and flag
        assert result.has_signal("jerga_ambigua_falta_unidad")
        assert "vehicle_type_ambiguous" in result.flag_names()
        # validation error recorded
        assert any("vehicle_type_rejected" in e for e in result.validation_errors)

    def test_trailer_rejected_and_ambiguity_added(self):
        text = "manejo trailer"
        out = _output_with_vehicle_fact("full", "trailer")
        result = validate_business_output(out, text)
        assert "experience.vehicle_type" not in result.explicit_facts
        assert result.has_signal("jerga_ambigua_falta_unidad")
        assert "vehicle_type_ambiguous" in result.flag_names()

    def test_torton_rejected_and_escuelita_added(self):
        text = "manejé torton varios años"
        out = _output_with_vehicle_fact("full", "torton")
        result = validate_business_output(out, text)
        assert "experience.vehicle_type" not in result.explicit_facts
        assert result.has_signal("considerar_escuelita_transmontes")
        assert not result.has_signal("jerga_ambigua_falta_unidad")

    def test_rabon_rejected_and_escuelita_added(self):
        text = "trabajé en rabón"
        out = _output_with_vehicle_fact("full", "rabon")
        result = validate_business_output(out, text)
        assert "experience.vehicle_type" not in result.explicit_facts
        assert result.has_signal("considerar_escuelita_transmontes")

    def test_evidence_not_in_text_removes_fact(self):
        text = "busco información"
        out = _output_with_vehicle_fact("sencillo", "sencillo")
        result = validate_business_output(out, text)
        assert "experience.vehicle_type" not in result.explicit_facts
        assert any("fact_evidence_not_in_text" in e for e in result.validation_errors)

    def test_empty_evidence_removes_fact(self):
        text = "Me interesa para sencillo"
        out = _output_with_vehicle_fact("sencillo", "")
        result = validate_business_output(out, text)
        assert "experience.vehicle_type" not in result.explicit_facts
        assert any("fact_evidence_not_in_text" in e for e in result.validation_errors)

    def test_low_confidence_fact_removed(self):
        text = "manejo sencillo"
        out = _output_with_vehicle_fact("sencillo", "sencillo", confidence=0.5)
        result = validate_business_output(out, text)
        assert "experience.vehicle_type" not in result.explicit_facts
        assert any("fact_low_confidence" in e for e in result.validation_errors)

    def test_confidence_at_threshold_kept(self):
        text = "manejo sencillo"
        out = _output_with_vehicle_fact("sencillo", "sencillo", confidence=0.7)
        result = validate_business_output(out, text)
        assert "experience.vehicle_type" in result.explicit_facts


# ── business signals validation ───────────────────────────────────────────────

class TestBusinessSignals:
    def test_valid_signal_kept(self):
        out = _output_with_signal("pago_condiciones", confidence=0.9)
        result = validate_business_output(out, "km cargado")
        assert result.has_signal("pago_condiciones")

    def test_unknown_signal_removed(self):
        out = _output_with_signal("señal_inventada", confidence=0.9)
        result = validate_business_output(out, "texto cualquiera")
        assert not result.has_signal("señal_inventada")
        assert any("unknown_signal" in e for e in result.validation_errors)

    def test_low_confidence_signal_removed(self):
        out = _output_with_signal("pago_condiciones", confidence=0.3)
        result = validate_business_output(out, "texto")
        assert not result.has_signal("pago_condiciones")
        assert any("signal_low_confidence" in e for e in result.validation_errors)

    def test_signal_at_min_threshold_kept(self):
        out = _output_with_signal("pago_condiciones", confidence=0.4)
        result = validate_business_output(out, "texto")
        assert result.has_signal("pago_condiciones")


# ── requires_human enforcement ────────────────────────────────────────────────

class TestRequiresHuman:
    def test_operador_b1_forces_requires_human(self):
        out = BusinessRouteOutput()
        out.business_signals.append(
            BusinessSignal(name="considerar_operador_b1", evidence="B1", confidence=0.95)
        )
        result = validate_business_output(out, "busco vacante B1")
        assert result.requires_human is True

    def test_reingreso_forces_requires_human(self):
        out = BusinessRouteOutput()
        out.business_signals.append(
            BusinessSignal(name="reingreso_verificar", evidence="reingreso", confidence=0.9)
        )
        result = validate_business_output(out, "sería como reingreso")
        assert result.requires_human is True

    def test_no_human_signal_leaves_requires_human_false(self):
        out = _output_with_signal("pago_condiciones", confidence=0.9)
        out.requires_human = False
        result = validate_business_output(out, "km cargado")
        assert result.requires_human is False

    def test_requires_human_already_true_stays_true(self):
        out = _output_with_signal("pago_condiciones")
        out.requires_human = True
        result = validate_business_output(out, "km cargado")
        assert result.requires_human is True


# ── city fact conflict detection ──────────────────────────────────────────────

class TestCityConflict:
    def test_same_city_no_conflict(self):
        text = "soy de Monterrey"
        out = BusinessRouteOutput()
        out.explicit_facts["candidate.city"] = ExplicitFact(
            field="candidate.city", value="Monterrey", evidence="soy de Monterrey"
        )
        result = validate_business_output(out, text, canonical_profile={"candidate.city": "Monterrey"})
        assert result.explicit_facts["candidate.city"].needs_confirmation is False

    def test_different_city_flags_confirmation(self):
        text = "soy de Torreón"
        out = BusinessRouteOutput()
        out.explicit_facts["candidate.city"] = ExplicitFact(
            field="candidate.city", value="Torreón", evidence="soy de Torreón"
        )
        result = validate_business_output(out, text, canonical_profile={"candidate.city": "Monterrey"})
        assert result.explicit_facts["candidate.city"].needs_confirmation is True
        assert any("city_conflict" in e for e in result.validation_errors)

    def test_no_canonical_profile_no_conflict(self):
        text = "soy de Saltillo"
        out = BusinessRouteOutput()
        out.explicit_facts["candidate.city"] = ExplicitFact(
            field="candidate.city", value="Saltillo", evidence="soy de Saltillo"
        )
        result = validate_business_output(out, text, canonical_profile=None)
        assert result.explicit_facts["candidate.city"].needs_confirmation is False


# ── clean pass-through ────────────────────────────────────────────────────────

class TestCleanOutput:
    def test_valid_output_unchanged(self):
        text = "manejo sencillo, busco vacante"
        out = BusinessRouteOutput()
        out.explicit_facts["experience.vehicle_type"] = ExplicitFact(
            field="experience.vehicle_type",
            value="sencillo",
            evidence="sencillo",
            confidence=0.95,
        )
        out.business_signals.append(
            BusinessSignal(name="objetivo_full_sencillo", evidence="sencillo", confidence=0.95)
        )
        result = validate_business_output(out, text)
        assert "experience.vehicle_type" in result.explicit_facts
        assert result.has_signal("objetivo_full_sencillo")
        # no spurious errors (city conflict errors are expected 0 here)
        assert not any("vehicle_type" in e for e in result.validation_errors)

    def test_empty_output_passes(self):
        out = BusinessRouteOutput()
        result = validate_business_output(out, "hola buenas tardes")
        assert result.shadow_error == ""
        assert result.validation_errors == []
