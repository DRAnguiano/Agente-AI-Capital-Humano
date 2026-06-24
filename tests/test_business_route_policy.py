"""Tests for business_route_policy.py — deterministic, no LLM, no DB."""
import pytest
from app.knowledge.business_route_schema import (
    AmbiguityFlag,
    AMBIGUITY_FLAG_NAMES,
    BusinessRouteOutput,
    BusinessSignal,
    ExplicitFact,
    PROFILE_CONTEXT_ACTIONS,
    RequestedInfoItem,
    VALID_REQUESTED_INFO_CATEGORIES,
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


# ── ambiguity_flag vehicle_type_ambiguous evidence validation ─────────────────

class TestVehicleTypeAmbiguousFlag:
    def test_non_vehicle_evidence_removes_flag(self):
        # 'Voi Acer' means 'voy a hacer'; meaningful language but not vehicle-domain evidence.
        out = BusinessRouteOutput()
        out.ambiguity_flags.append(AmbiguityFlag(name="vehicle_type_ambiguous", evidence="Voi Acer"))
        result = validate_business_output(out, "Pero como le Voi Acer para irme a Manzanillo")
        assert "vehicle_type_ambiguous" not in result.flag_names()
        assert any("vehicle_type_ambiguous_invalid_evidence" in e for e in result.validation_errors)

    def test_non_vehicle_evidence_records_evidence_in_error(self):
        # Error message must include the rejected evidence so it's traceable in CSV.
        out = BusinessRouteOutput()
        out.ambiguity_flags.append(AmbiguityFlag(name="vehicle_type_ambiguous", evidence="Voi Acer"))
        result = validate_business_output(out, "Pero como le Voi Acer para irme a Manzanillo")
        error_text = " ".join(result.validation_errors)
        assert "vehicle_type_ambiguous_invalid_evidence" in error_text
        assert "Voi Acer" in error_text

    def test_quinta_rueda_evidence_keeps_flag(self):
        """'quinta rueda' is NEEDS_CLARIFICATION — flag must be kept."""
        out = BusinessRouteOutput()
        out.ambiguity_flags.append(AmbiguityFlag(name="vehicle_type_ambiguous", evidence="quinta rueda"))
        result = validate_business_output(out, "opero quinta rueda")
        assert "vehicle_type_ambiguous" in result.flag_names()
        assert not any("vehicle_type_ambiguous_invalid_evidence" in e for e in result.validation_errors)

    def test_trailer_evidence_keeps_flag(self):
        out = BusinessRouteOutput()
        out.ambiguity_flags.append(AmbiguityFlag(name="vehicle_type_ambiguous", evidence="trailer"))
        result = validate_business_output(out, "manejo trailer")
        assert "vehicle_type_ambiguous" in result.flag_names()

    def test_trailero_evidence_keeps_flag(self):
        out = BusinessRouteOutput()
        out.ambiguity_flags.append(AmbiguityFlag(name="vehicle_type_ambiguous", evidence="trailero"))
        result = validate_business_output(out, "soy trailero")
        assert "vehicle_type_ambiguous" in result.flag_names()

    def test_empty_evidence_removes_flag(self):
        out = BusinessRouteOutput()
        out.ambiguity_flags.append(AmbiguityFlag(name="vehicle_type_ambiguous", evidence=""))
        result = validate_business_output(out, "algo")
        assert "vehicle_type_ambiguous" not in result.flag_names()
        assert any("vehicle_type_ambiguous_invalid_evidence" in e for e in result.validation_errors)

    @pytest.mark.parametrize("evidence", [
        "quinta rueda",
        "5ta rueda",
        "tráiler",
        "trailer",
        "trailero",
        "tractocamión",
        "tractocamion",
    ])
    def test_ambiguous_vehicle_catalog_keeps_flag(self, evidence):
        # Each cataloged vehicular term must be accepted as valid vehicle_type_ambiguous evidence.
        out = BusinessRouteOutput()
        out.ambiguity_flags.append(AmbiguityFlag(name="vehicle_type_ambiguous", evidence=evidence))
        result = validate_business_output(out, f"manejo {evidence}")
        assert "vehicle_type_ambiguous" in result.flag_names(), (
            f"vehicle_type_ambiguous stripped for evidence={evidence!r} — "
            f"verify normalize_vehicle catalog"
        )
        assert not any(
            "vehicle_type_ambiguous_invalid_evidence" in e for e in result.validation_errors
        )

    def test_other_flags_not_affected(self):
        # Non-vehicle flags pass through policy without evidence check.
        out = BusinessRouteOutput()
        out.ambiguity_flags.append(AmbiguityFlag(name="multimedia_no_ocr", evidence="<Multimedia omitido>"))
        out.ambiguity_flags.append(AmbiguityFlag(name="context_missing", evidence="se fueron"))
        result = validate_business_output(out, "se fueron <Multimedia omitido>")
        assert "multimedia_no_ocr" in result.flag_names()
        assert "context_missing" in result.flag_names()


# ── catálogo: ambiguity flag names ────────────────────────────────────────────

class TestUnknownAmbiguityFlag:
    def test_unknown_flag_removed_with_error(self):
        out = BusinessRouteOutput()
        out.ambiguity_flags.append(AmbiguityFlag(name="vehicle_type_confirmed", evidence="x"))
        result = validate_business_output(out, "algo")
        assert "vehicle_type_confirmed" not in result.flag_names()
        assert any("unknown_ambiguity_flag" in e and "vehicle_type_confirmed" in e
                   for e in result.validation_errors)

    @pytest.mark.parametrize("name", sorted(AMBIGUITY_FLAG_NAMES - {"vehicle_type_ambiguous"}))
    def test_catalog_flags_kept(self, name):
        # Todo flag del catálogo (salvo vehicle_type_ambiguous, que exige evidencia
        # vehicular) pasa sin error.
        out = BusinessRouteOutput()
        out.ambiguity_flags.append(AmbiguityFlag(name=name, evidence="evidencia"))
        result = validate_business_output(out, "evidencia en texto")
        assert name in result.flag_names()
        assert not any("unknown_ambiguity_flag" in e for e in result.validation_errors)


# ── catálogo: profile_context_action ──────────────────────────────────────────

class TestProfileContextAction:
    def test_unknown_action_falls_back_to_continue_profiling(self):
        out = BusinessRouteOutput()
        out.profile_context_action = "continue_profilingg"  # typo del LLM
        result = validate_business_output(out, "algo")
        assert result.profile_context_action == "continue_profiling"
        assert any("unknown_profile_context_action" in e and "continue_profilingg" in e
                   for e in result.validation_errors)

    @pytest.mark.parametrize("action", sorted(PROFILE_CONTEXT_ACTIONS))
    def test_catalog_actions_kept(self, action):
        out = BusinessRouteOutput()
        out.profile_context_action = action
        result = validate_business_output(out, "algo")
        assert result.profile_context_action == action
        assert not any("unknown_profile_context_action" in e for e in result.validation_errors)


# ── catálogo: policy_answer_keys ──────────────────────────────────────────────

class TestPolicyAnswerKeys:
    def test_unknown_key_removed_with_error(self):
        out = BusinessRouteOutput()
        out.policy_answer_keys = ["clave_inventada"]
        result = validate_business_output(out, "algo")
        assert "clave_inventada" not in result.policy_answer_keys
        assert any("unknown_policy_answer_key" in e and "clave_inventada" in e
                   for e in result.validation_errors)

    def test_known_key_kept(self):
        out = BusinessRouteOutput()
        out.policy_answer_keys = ["no_pagares_en_blanco"]
        result = validate_business_output(out, "firman pagarés en blanco?")
        assert result.policy_answer_keys == ["no_pagares_en_blanco"]
        assert not any("unknown_policy_answer_key" in e for e in result.validation_errors)


# ── catálogo: requested_info categories ───────────────────────────────────────

class TestRequestedInfoCategories:
    def test_unknown_category_removed_with_error(self):
        out = BusinessRouteOutput()
        out.requested_info.append(RequestedInfoItem(category="salary_info", evidence="sueldo"))
        result = validate_business_output(out, "cuánto pagan de sueldo")
        assert not any(r.category == "salary_info" for r in result.requested_info)
        assert any("unknown_requested_info_category" in e and "salary_info" in e
                   for e in result.validation_errors)

    def test_valid_category_kept_alongside_unknown(self):
        out = BusinessRouteOutput()
        out.requested_info.append(RequestedInfoItem(category="salary", evidence="sueldo"))
        out.requested_info.append(RequestedInfoItem(category="ubicacion", evidence="dónde"))
        result = validate_business_output(out, "cuánto pagan y dónde están")
        assert [r.category for r in result.requested_info] == ["salary"]
        assert any("unknown_requested_info_category" in e for e in result.validation_errors)

    @pytest.mark.parametrize("category", sorted(VALID_REQUESTED_INFO_CATEGORIES))
    def test_all_catalog_categories_kept(self, category):
        out = BusinessRouteOutput()
        out.requested_info.append(RequestedInfoItem(category=category, evidence="evidencia"))
        result = validate_business_output(out, "evidencia")
        assert any(r.category == category for r in result.requested_info)
        assert not any("unknown_requested_info_category" in e for e in result.validation_errors)


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
