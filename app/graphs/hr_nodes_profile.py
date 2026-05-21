from typing import Any

from app.db import log_event, update_candidate_profile, update_stage
from app.graphs.hr_state import HRState
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
