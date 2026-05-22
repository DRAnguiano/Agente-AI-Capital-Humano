from typing import Any

from app.graphs.hr_state import HRState


MISSING_PROFILE_FIELDS = [
    ("nombre_completo", "nombre completo", "¿Me confirmas tu nombre completo?"),
    ("ciudad", "ciudad", "¿De qué ciudad nos escribes?"),
    ("telefono", "teléfono", "¿Me compartes tu número de teléfono?"),
    ("licencia_federal", "licencia federal", "¿Cuentas con licencia federal vigente y qué tipo es?"),
    ("disponibilidad_viajar", "disponibilidad para viajar", "¿Tienes disponibilidad para viajar?"),
    ("experiencia_quinta_rueda", "experiencia", "¿Cuánta experiencia tienes manejando quinta rueda?"),
]


def _next_missing_profile_field(profile: dict[str, Any]) -> dict[str, str | None]:
    for key, label, question in MISSING_PROFILE_FIELDS:
        if not profile.get(key):
            return {"key": key, "label": label, "question": question}
    return {"key": None, "label": None, "question": None}


def _substance_analysis(state: HRState) -> dict[str, Any]:
    return state.get("substance_disclosure_analysis") or {}


def _has_restrictive_substance_signal(state: HRState) -> bool:
    analysis = _substance_analysis(state)
    return bool(
        analysis.get("detected")
        and (
            analysis.get("status") == "ACTIVE_OR_INTENDED_USE"
            or analysis.get("operational_risk") == "high"
            or analysis.get("requires_review") is True
        )
    )


def _has_analytics_substance_signal(state: HRState) -> bool:
    analysis = _substance_analysis(state)
    return bool(
        analysis.get("detected")
        and analysis.get("analytics_flag") is True
        and not _has_restrictive_substance_signal(state)
    )


def _has_expiring_documents(state: HRState) -> bool:
    lead = state.get("lead_ingestion") or {}
    extracted = lead.get("extracted") or {}
    profile = state.get("profile_snapshot") or {}
    return bool(
        extracted.get("license_expiry_text")
        or extracted.get("medical_expiry_text")
        or profile.get("requires_human")
        or state.get("requires_human")
    ) and not _has_analytics_substance_signal(state)


def plan_profile_followup_node(state: HRState) -> dict[str, Any]:
    """
    Plan the next profile follow-up as graph state.

    This keeps response generation from deciding which field to ask for. The
    natural reply node can focus on wording the acknowledgement and then append
    the exact question selected by the graph.
    """
    profile = state.get("profile_snapshot") or {}
    lead = state.get("lead_ingestion") or {}
    substance = _substance_analysis(state)
    restrictive_substance = _has_restrictive_substance_signal(state)
    analytics_substance = _has_analytics_substance_signal(state)

    next_missing = _next_missing_profile_field(profile)
    exact_question = next_missing.get("question")
    should_ask = bool(exact_question) and not restrictive_substance
    has_expiring_documents = _has_expiring_documents(state)

    review_message = None
    if restrictive_substance:
        review_message = "Por seguridad operativa, Capital Humano debe revisar este punto antes de continuar."
    elif has_expiring_documents:
        review_message = "Capital Humano debe revisar la vigencia de tus documentos antes de avanzar."
    elif analytics_substance:
        review_message = "Queda registrada una señal para revisión interna y análisis posterior; podemos continuar con tus datos."

    plan = {
        "should_ask": should_ask,
        "field_key": next_missing.get("key") if should_ask else None,
        "field_label": next_missing.get("label") if should_ask else None,
        "exact_question": exact_question if should_ask else None,
        "max_questions": 1 if should_ask else 0,
        "has_expiring_documents": has_expiring_documents,
        "has_restrictive_substance_signal": restrictive_substance,
        "has_substance_analytics_signal": analytics_substance,
        "substance_disclosure_analysis": substance,
        "review_message": review_message,
        "can_suggest_upload_documents": not has_expiring_documents and not restrictive_substance,
        "lead_updated": bool(lead.get("updated", False)),
        "updated_fields": lead.get("updated_fields", []),
        "callback_schedule": lead.get("callback_schedule") or {},
    }

    return {
        "profile_followup_plan": plan,
        "events": [
            {
                "type": "profile_followup_planned",
                "should_ask": should_ask,
                "field_key": plan["field_key"],
                "has_expiring_documents": has_expiring_documents,
                "has_restrictive_substance_signal": restrictive_substance,
                "has_substance_analytics_signal": analytics_substance,
            }
        ],
    }
