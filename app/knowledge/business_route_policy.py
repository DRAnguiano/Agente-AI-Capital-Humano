"""Policy validator para BusinessRouteOutput — determinista, sin LLM, sin DB.

Responsabilidades:
- Eliminar explicit_facts cuya evidencia no aparece literalmente en el texto.
- Rechazar vehicle_type facts donde el catálogo no confirma el término (NEEDS_CLARIFICATION
  o NON_TARGET) y agregar automáticamente la señal/flag correcta.
- Eliminar señales desconocidas o con confidence insuficiente.
- Forzar requires_human=True cuando hay señales que lo exigen (B1, reingreso).
- Marcar needs_confirmation cuando un city fact contradice el perfil canónico.
"""
from __future__ import annotations

from app.knowledge.business_route_schema import (
    AmbiguityFlag,
    BusinessRouteOutput,
    BusinessSignal,
    BUSINESS_SIGNALS,
    HUMAN_REQUIRED_SIGNALS,
    VALID_VEHICLE_TYPES,
)
from app.knowledge.normalize_domain_values import normalize_vehicle
from app.knowledge.text_normalizer import normalize_text

# --- constants ---

MIN_SIGNAL_CONFIDENCE = 0.4
MIN_FACT_CONFIDENCE = 0.7

_CONFIRMED = "confirmed"
_NEEDS_CLARIFICATION = "needs_clarification"


def _evidence_in_text(evidence: str, text: str) -> bool:
    if not evidence or not text:
        return False
    return normalize_text(evidence) in normalize_text(text)


def validate_business_output(
    output: BusinessRouteOutput,
    text: str,
    canonical_profile: dict | None = None,
) -> BusinessRouteOutput:
    """Validate and clean a BusinessRouteOutput in-place. Returns the same object.

    Args:
        output: classifier output to validate (mutated in-place).
        text: raw candidate message (used to verify evidence literals).
        canonical_profile: optional read-only profile dict for city conflict detection.
    """
    errors: list[str] = list(output.validation_errors)

    # ── 1. Validate explicit_facts ────────────────────────────────────────────
    bad_keys: list[str] = []

    for key, fact in output.explicit_facts.items():
        # Evidence must appear literally in the message
        if not _evidence_in_text(fact.evidence, text):
            errors.append(
                f"fact_evidence_not_in_text: {key}={fact.value!r} evidence={fact.evidence!r}"
            )
            bad_keys.append(key)
            continue

        if fact.confidence < MIN_FACT_CONFIDENCE:
            errors.append(f"fact_low_confidence: {key}={fact.value!r} conf={fact.confidence}")
            bad_keys.append(key)
            continue

        if key == "experience.vehicle_type":
            resolution = normalize_vehicle(fact.evidence)

            if resolution is None:
                errors.append(f"vehicle_type_no_catalog_match: evidence={fact.evidence!r}")
                bad_keys.append(key)
                continue

            if resolution.status != _CONFIRMED:
                errors.append(
                    f"vehicle_type_rejected: evidence={fact.evidence!r} "
                    f"status={resolution.status}"
                )
                bad_keys.append(key)

                # Auto-correct: add appropriate signal/flag that the LLM should have emitted
                if resolution.status == _NEEDS_CLARIFICATION:
                    if not output.has_signal("jerga_ambigua_falta_unidad"):
                        output.business_signals.append(
                            BusinessSignal(
                                name="jerga_ambigua_falta_unidad",
                                evidence=fact.evidence,
                                confidence=0.9,
                            )
                        )
                    if "vehicle_type_ambiguous" not in output.flag_names():
                        output.ambiguity_flags.append(
                            AmbiguityFlag(name="vehicle_type_ambiguous", evidence=fact.evidence)
                        )
                else:
                    # NON_TARGET: torton/rabón/reparto
                    if not output.has_signal("considerar_escuelita_transmontes"):
                        output.business_signals.append(
                            BusinessSignal(
                                name="considerar_escuelita_transmontes",
                                evidence=fact.evidence,
                                confidence=0.9,
                            )
                        )
                continue

            if fact.value not in VALID_VEHICLE_TYPES:
                errors.append(f"vehicle_type_invalid_value: {fact.value!r}")
                bad_keys.append(key)
                continue

        if key == "candidate.city" and canonical_profile:
            canon_city = canonical_profile.get("candidate.city") or (
                canonical_profile.get("facts") or {}
            ).get("candidate.city")
            if canon_city and normalize_text(str(canon_city)) != normalize_text(fact.value):
                fact.needs_confirmation = True
                errors.append(f"city_conflict: canonical={canon_city!r} new={fact.value!r}")

    for k in bad_keys:
        output.explicit_facts.pop(k, None)

    # ── 2. Validate business_signals ─────────────────────────────────────────
    valid_signals: list[BusinessSignal] = []
    for sig in output.business_signals:
        if sig.name not in BUSINESS_SIGNALS:
            errors.append(f"unknown_signal: {sig.name}")
            continue
        if sig.confidence < MIN_SIGNAL_CONFIDENCE:
            errors.append(f"signal_low_confidence: {sig.name} conf={sig.confidence}")
            continue
        valid_signals.append(sig)
    output.business_signals = valid_signals

    # ── 3. Enforce requires_human ─────────────────────────────────────────────
    if any(s.name in HUMAN_REQUIRED_SIGNALS for s in output.business_signals):
        output.requires_human = True

    output.validation_errors = errors
    return output
