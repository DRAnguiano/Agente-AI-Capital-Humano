from typing import Any

from app.db import log_event, update_candidate_profile, update_stage
from app.graphs.hr_state import HRState
from app.indexer import call_llm
from app.orchestrator import Stage, decide_next_stage, extract_profile_fields


PRIVATE_PROFILE_KEYS = {"_city_catalog", "_city_requires_ch_validation"}


def _public_profile_fields(fields: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in fields.items()
        if key not in PRIVATE_PROFILE_KEYS and not key.startswith("_")
    }


def _is_clarification_followup_safe(state: HRState) -> bool:
    detection = state.get("route_detection") or {}
    return detection.get("clarification_followup") in {"safe", "confused_or_meta"}


def extract_profile_fields_node(state: HRState) -> dict[str, Any]:
    """
    Extract candidate profile fields from the inbound message.

    Reuses the currently validated legacy extraction logic while moving the
    orchestration responsibility to LangGraph.
    """
    if _is_clarification_followup_safe(state):
        return {
            "extracted_fields": {},
            "profile_updates": {},
            "profile_private_context": {},
            "events": [
                {
                    "type": "profile_fields_extraction_skipped",
                    "reason": "clarification_followup_safe",
                }
            ],
        }

    message = state.get("message") or ""
    current_stage = state.get("current_stage") or "START"
    fields = extract_profile_fields(message, current_stage)
    public_fields = _public_profile_fields(fields)

    return {
        "extracted_fields": public_fields,
        "profile_updates": public_fields,
        "profile_private_context": {
            key: value
            for key, value in fields.items()
            if key in PRIVATE_PROFILE_KEYS or key.startswith("_")
        },
        "events": [
            {
                "type": "profile_fields_extracted",
                "field_names": sorted(public_fields.keys()),
            }
        ],
    }


def _natural_profile_prompt(state: HRState) -> str:
    lead = state.get("lead_ingestion") or {}
    profile = state.get("profile_snapshot") or {}
    message = state.get("message") or ""
    current_stage = state.get("current_stage") or "START"

    return f"""
Eres Mundo, asistente de Capital Humano de Transmontes.
Responde como asesor de reclutamiento, no como formulario.

Objetivo:
- Reconoce la información útil que el candidato acaba de compartir.
- Si hay datos que requieren revisión, dilo con calma.
- No repitas preguntas ya contestadas.
- No reinicies el proceso.
- Si falta un dato importante, pregunta solo uno y de forma natural.
- Invita a continuar sin hostigar.
- Responde breve, claro y en español mexicano natural.

Contexto de etapa actual: {current_stage}
Mensaje del candidato: {message}
Perfil actualizado: {profile}
Extracción de lead: {lead}

Reglas:
- Si la licencia o apto vencen pronto, indica que Capital Humano debe revisar vigencia.
- Si no hay ciudad en el perfil, pregunta ciudad al final, pero reconoce antes lo ya capturado.
- No digas que ya está contratado.
- No inventes requisitos ni pagos.

Respuesta:
""".strip()


def natural_lead_profile_response_node(state: HRState) -> dict[str, Any]:
    """
    Respond naturally after non-blocking lead ingestion.

    This avoids forcing the legacy profile form when the candidate already shared
    useful facts in a free-form message.
    """
    conversation_key = state.get("conversation_key")
    current_stage = state.get("current_stage") or "START"
    lead = state.get("lead_ingestion") or {}

    try:
        reply = call_llm(_natural_profile_prompt(state)).strip()
    except Exception:
        profile = state.get("profile_snapshot") or {}
        name = profile.get("nombre_completo") or ""
        city = profile.get("ciudad")
        prefix = f"Gracias, {name}." if name else "Gracias por la información."
        review = " Si la licencia o el apto vencen pronto, Capital Humano debe revisar la vigencia antes de avanzar."
        missing_city = " ¿De qué ciudad nos escribes?" if not city else " Si gustas, seguimos revisando tu perfil para ver cómo avanzar."
        reply = f"{prefix}{review}{missing_city}"

    if conversation_key:
        log_event(
            conversation_key=conversation_key,
            event_type="natural_profile_reply_generated",
            stage_from=current_stage,
            stage_to=current_stage,
            intent=state.get("intent") or "profile_natural_capture",
            risk_level=state.get("risk_level") or "low",
            requires_human=bool((state.get("profile_snapshot") or {}).get("requires_human", False)),
            metadata={
                "lead_updated": bool(lead.get("updated", False)),
                "updated_fields": lead.get("updated_fields", []),
                "graph_route": "profile",
            },
        )

    return {
        "next_stage": current_stage,
        "reply": reply,
        "text": reply,
        "profile_updated": bool(lead.get("updated", False)),
        "stage_updated": False,
        "profile_event_logged": True,
        "route_stub_used": False,
        "events": [
            {
                "type": "natural_profile_reply_generated",
                "stage_preserved": True,
                "lead_updated": bool(lead.get("updated", False)),
                "updated_fields": lead.get("updated_fields", []),
            }
        ],
    }


def update_profile_and_stage_node(state: HRState) -> dict[str, Any]:
    """
    Persist profile updates, advance stage, and generate the next profile reply.

    This replaces the first profile branch responsibilities from the legacy
    orchestrator for diagnostic graph paths.
    """
    conversation_key = state.get("conversation_key")
    current_stage = state.get("current_stage") or "START"
    fields = state.get("profile_updates") or {}
    intent = state.get("intent") or "candidate_answer"
    risk_level = state.get("risk_level") or "low"
    requires_human = bool(state.get("requires_human", False))

    if _is_clarification_followup_safe(state):
        next_stage = Stage.ASK_CITY.value
        reply = "Gracias por aclararlo. Para continuar, ¿en qué ciudad te encuentras actualmente?"
    else:
        next_stage, reply = decide_next_stage(current_stage, fields)

    profile_updated = False
    stage_updated = False
    event_logged = False

    if conversation_key:
        if fields:
            update_candidate_profile(conversation_key, fields)
            profile_updated = True

        update_stage(
            conversation_key=conversation_key,
            stage_to=next_stage,
            intent=intent,
            risk_level=risk_level,
            requires_human=requires_human,
        )
        stage_updated = True

        log_event(
            conversation_key=conversation_key,
            event_type="profile_graph_step_completed",
            stage_from=current_stage,
            stage_to=next_stage,
            intent=intent,
            risk_level=risk_level,
            requires_human=requires_human,
            metadata={
                "field_names": sorted(fields.keys()),
                "graph_route": "profile",
                "clarification_followup": (state.get("route_detection") or {}).get("clarification_followup"),
            },
        )
        event_logged = True

    return {
        "next_stage": next_stage,
        "reply": reply,
        "text": reply,
        "profile_updated": profile_updated,
        "stage_updated": stage_updated,
        "profile_event_logged": event_logged,
        "route_stub_used": False,
        "events": [
            {
                "type": "profile_stage_decided",
                "stage_from": current_stage,
                "stage_to": next_stage,
                "profile_updated": profile_updated,
                "field_names": sorted(fields.keys()),
                "clarification_followup": (state.get("route_detection") or {}).get("clarification_followup"),
            }
        ],
    }
