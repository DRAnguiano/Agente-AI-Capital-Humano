import json
import os
import re
from datetime import datetime, timezone
from typing import Any

from app.db import find_city_catalog_match, log_event, update_candidate_profile
from app.graphs.hr_state import HRState
from app.indexer import call_llm


MAX_NOTE_CHARS = 3500


def _env_bool(name: str, default: bool = True) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _json_from_text(text: str) -> dict[str, Any]:
    raw = (text or "").strip()
    if not raw:
        return {}

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
    if not match:
        return {}

    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return {}


def _clean_text(value: Any, max_len: int = 240) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text[:max_len]


def _clean_choice(value: Any, allowed: set[str]) -> str | None:
    if value is None:
        return None
    text = str(value).strip().upper()
    return text if text in allowed else None


def _compact_list(items: Any, max_items: int = 8) -> list[str]:
    if not isinstance(items, list):
        return []
    output: list[str] = []
    for item in items:
        text = _clean_text(item, 180)
        if text and text not in output:
            output.append(text)
        if len(output) >= max_items:
            break
    return output


def _merge_notes(existing: Any, new_notes: list[str]) -> str | None:
    existing_text = str(existing or "").strip()
    clean_notes = [note for note in new_notes if note]
    if not clean_notes:
        return existing_text or None

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    block = f"[{stamp}] " + " | ".join(clean_notes)

    if block in existing_text:
        return existing_text

    merged = f"{existing_text}\n{block}".strip() if existing_text else block
    if len(merged) > MAX_NOTE_CHARS:
        merged = merged[-MAX_NOTE_CHARS:]
    return merged


def _city_fields(city_raw: str | None) -> dict[str, Any]:
    if not city_raw:
        return {}

    match = find_city_catalog_match(city_raw)
    if not match:
        return {"ciudad_raw": city_raw}

    return {
        "ciudad": match.get("canonical_city"),
        "ciudad_raw": city_raw,
        "estado_region": match.get("state_region"),
        "pais_codigo": match.get("country_code"),
        "pais_nombre": match.get("country_name"),
        "city_group": match.get("city_group"),
        "is_local_laguna": match.get("is_local_laguna"),
        "is_foreign_country": match.get("is_foreign_country"),
        "location_requires_ch_validation": match.get("requires_ch_validation"),
        "location_needs_travel_validation": match.get("needs_travel_validation"),
        "city_catalog_alias": match.get("alias_text"),
        "city_catalog_id": match.get("id"),
    }


def _normalize_extraction(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload or {}
    facts = data.get("facts") if isinstance(data.get("facts"), dict) else data

    city_raw = _clean_text(facts.get("city_raw") or facts.get("ciudad_raw") or facts.get("city"))
    license_status = _clean_choice(
        facts.get("license_status") or facts.get("licencia_federal"),
        {"SI", "NO", "INCIERTO", "SI_PROBABLE"},
    )

    extracted = {
        "city_raw": city_raw,
        "license_status": license_status,
        "license_type": _clean_text(facts.get("license_type") or facts.get("tipo_licencia"), 40),
        "license_expiry_text": _clean_text(facts.get("license_expiry_text") or facts.get("licencia_vencimiento"), 120),
        "license_needs_review": bool(facts.get("license_needs_review", False)),
        "experience_text": _clean_text(facts.get("experience_text") or facts.get("experiencia_quinta_rueda"), 120),
        "medical_status": _clean_choice(facts.get("medical_status") or facts.get("apto_medico"), {"SI", "NO", "INCIERTO"}),
        "availability_travel": _clean_choice(facts.get("availability_travel") or facts.get("disponibilidad_viajar"), {"SI", "NO", "INCIERTO"}),
        "candidate_questions": _compact_list(facts.get("candidate_questions") or facts.get("dudas")),
        "objections": _compact_list(facts.get("objections") or facts.get("objeciones")),
        "risk_notes": _compact_list(facts.get("risk_notes") or facts.get("riesgos")),
        "summary_note": _clean_text(facts.get("summary_note") or facts.get("observacion"), 300),
    }

    return extracted


def _fields_from_extraction(extracted: dict[str, Any], profile_snapshot: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    fields: dict[str, Any] = {}
    notes: list[str] = []

    city_fields = _city_fields(extracted.get("city_raw"))
    fields.update(city_fields)

    if extracted.get("license_status"):
        status = extracted["license_status"]
        fields["licencia_federal"] = "SI" if status == "SI_PROBABLE" else status
    if extracted.get("license_type"):
        fields["tipo_licencia"] = extracted["license_type"]
    if extracted.get("experience_text"):
        fields["experiencia_quinta_rueda"] = extracted["experience_text"]
    if extracted.get("medical_status"):
        fields["apto_medico"] = extracted["medical_status"]
    if extracted.get("availability_travel"):
        fields["disponibilidad_viajar"] = extracted["availability_travel"]

    if extracted.get("license_expiry_text"):
        notes.append(f"Licencia/vigencia mencionada: {extracted['license_expiry_text']}")
    if extracted.get("license_needs_review"):
        notes.append("Requiere revisión CH por vigencia o condición de licencia")
        fields["requires_human"] = True
        fields["risk_level"] = "medium"
    for question in extracted.get("candidate_questions") or []:
        notes.append(f"Duda del candidato: {question}")
    for objection in extracted.get("objections") or []:
        notes.append(f"Objeción/interés: {objection}")
    for risk in extracted.get("risk_notes") or []:
        notes.append(f"Revisión sugerida: {risk}")
    if extracted.get("summary_note"):
        notes.append(extracted["summary_note"])

    merged_notes = _merge_notes(profile_snapshot.get("observaciones"), notes)
    if merged_notes:
        fields["observaciones"] = merged_notes

    return fields, notes


def ingest_lead_node(state: HRState) -> dict[str, Any]:
    if not _env_bool("LEAD_INGESTION_ENABLED", True):
        return {
            "lead_ingestion": {"enabled": False},
            "events": [{"type": "lead_ingestion_skipped", "reason": "disabled"}],
        }

    message = state.get("message") or ""
    conversation_key = state.get("conversation_key")
    profile_snapshot = state.get("profile_snapshot") or {}
    memory = state.get("conversation_memory") or {}

    if not message.strip():
        return {"lead_ingestion": {"enabled": True, "updated": False, "reason": "empty_message"}}

    prompt = f"""
You extract lead facts from Mexican trucking recruiting chats.
Do not answer the candidate. Return JSON only.

The candidate may write fragmented messages, informal spelling, short follow-ups,
regional expressions, or multiple ideas in one message.
Extract facts that are useful for a recruiter lead note. Do not force a form flow.

Allowed values:
- license_status: SI, NO, SI_PROBABLE, INCIERTO
- medical_status: SI, NO, INCIERTO
- availability_travel: SI, NO, INCIERTO

Mark license_needs_review=true when the candidate says the license expires soon,
is about to expire, is not fully current, or needs renewal/validation.

=== CURRENT PROFILE ===
{json.dumps(profile_snapshot, ensure_ascii=False, default=str)}

=== CONVERSATION MEMORY ===
{json.dumps(memory, ensure_ascii=False, default=str)}

=== CURRENT MESSAGE ===
{message}

Return JSON:
{{
  "facts": {{
    "city_raw": null,
    "license_status": null,
    "license_type": null,
    "license_expiry_text": null,
    "license_needs_review": false,
    "experience_text": null,
    "medical_status": null,
    "availability_travel": null,
    "candidate_questions": [],
    "objections": [],
    "risk_notes": [],
    "summary_note": null
  }}
}}
""".strip()

    try:
        raw = call_llm(prompt)
        parsed = _json_from_text(raw)
        extracted = _normalize_extraction(parsed)
    except Exception as exc:
        return {
            "lead_ingestion": {
                "enabled": True,
                "updated": False,
                "reason": "extraction_exception",
                "error": f"{type(exc).__name__}: {exc}",
            },
            "events": [{"type": "lead_ingestion_failed", "error": f"{type(exc).__name__}: {exc}"}],
        }

    fields, notes = _fields_from_extraction(extracted, profile_snapshot)
    updated = bool(fields)

    if conversation_key and fields:
        update_candidate_profile(conversation_key, fields)
        log_event(
            conversation_key=conversation_key,
            event_type="lead_ingested",
            stage_from=state.get("current_stage"),
            stage_to=state.get("current_stage"),
            intent=state.get("intent"),
            risk_level=fields.get("risk_level") or state.get("risk_level") or "low",
            requires_human=bool(fields.get("requires_human", False)),
            metadata={"extracted": extracted, "updated_fields": sorted(fields.keys()), "notes": notes},
        )

    merged_profile = {**profile_snapshot, **fields}

    return {
        "profile_snapshot": merged_profile,
        "lead_ingestion": {
            "enabled": True,
            "updated": updated,
            "extracted": extracted,
            "updated_fields": sorted(fields.keys()),
            "notes": notes,
        },
        "events": [
            {
                "type": "lead_ingested",
                "updated": updated,
                "updated_fields": sorted(fields.keys()),
                "notes_count": len(notes),
            }
        ],
    }
