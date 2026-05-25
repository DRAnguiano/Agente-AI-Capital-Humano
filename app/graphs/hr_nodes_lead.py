import json
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from app.db import (
    find_city_catalog_match,
    log_event,
    sync_conversation_risk_from_profile,
    update_candidate_profile,
)
from app.graphs.hr_state import HRState
from app.indexer import call_llm


MAX_NOTE_CHARS = 3500
CALLBACK_LOCAL_TZ = ZoneInfo(os.getenv("CALLBACK_LOCAL_TIMEZONE", "America/Monterrey"))
CALLBACK_STATUS_REQUESTED = "REQUESTED"


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


def _clean_phone(value: Any) -> str | None:
    if value is None:
        return None
    digits = re.sub(r"\D+", "", str(value))
    if 8 <= len(digits) <= 15:
        return digits
    return None


def _clean_age(value: Any) -> int | None:
    if value is None:
        return None
    match = re.search(r"\d{1,2}", str(value))
    if not match:
        return None
    age = int(match.group(0))
    if 18 <= age <= 75:
        return age
    return None


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


def _normalize_callback_text(value: str | None) -> str:
    return (value or "").strip().lower().replace("á", "a").replace("é", "e").replace("í", "i").replace("ó", "o").replace("ú", "u")


def _callback_schedule(callback_window: str | None) -> dict[str, Any]:
    """
    Convert a natural callback request into an operational local follow-up time.

    This intentionally uses server time + configured local timezone instead of web search.
    Web search is nondeterministic for a simple clock calculation and can create noisy
    behavior in production chats.
    """
    now = datetime.now(CALLBACK_LOCAL_TZ)
    window = _clean_text(callback_window, 120)
    text = _normalize_callback_text(window)

    schedule: dict[str, Any] = {
        "callback_requested_at": now.isoformat(),
        "callback_requested_at_utc": now.astimezone(timezone.utc).isoformat(),
        "callback_status": CALLBACK_STATUS_REQUESTED,
        "callback_timezone": str(CALLBACK_LOCAL_TZ),
    }

    if window:
        schedule["callback_window"] = window

    relative_minutes = None
    minute_match = re.search(r"\b(\d{1,3})\s*(?:min|mins|minuto|minutos)\b", text)
    hour_match_relative = re.search(r"\b(\d{1,2})\s*(?:h|hr|hrs|hora|horas)\b", text)

    if "media hora" in text:
        relative_minutes = 30
    elif "un cuarto" in text or "15 minutos" in text:
        relative_minutes = 15
    elif minute_match:
        relative_minutes = int(minute_match.group(1))
    elif hour_match_relative and "a las" not in text:
        relative_minutes = int(hour_match_relative.group(1)) * 60

    due = None
    source = None

    if relative_minutes is not None:
        due = now + timedelta(minutes=relative_minutes)
        source = "relative_window"
    else:
        explicit_match = re.search(
            r"(?:a\s+las\s+)?\b(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.?m\.?|p\.?m\.?)?\b",
            text,
        )
        if explicit_match:
            hour = int(explicit_match.group(1))
            minute = int(explicit_match.group(2) or 0)
            meridian = (explicit_match.group(3) or "").replace(".", "")

            if 0 <= hour <= 23 and 0 <= minute <= 59:
                if meridian == "pm" and hour < 12:
                    hour += 12
                elif meridian == "am" and hour == 12:
                    hour = 0

                due = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                if due < now:
                    due += timedelta(days=1)
                source = "explicit_time"

    if due:
        schedule.update(
            {
                "callback_due_at": due.isoformat(),
                "callback_due_at_utc": due.astimezone(timezone.utc).isoformat(),
                "callback_due_local_date": due.strftime("%Y-%m-%d"),
                "callback_due_local_time": due.strftime("%H:%M hrs"),
                "callback_due_label": due.strftime("%Y-%m-%d %H:%M hrs"),
                "callback_schedule_source": source,
            }
        )

    return schedule


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
    license_expiry_text = _clean_text(facts.get("license_expiry_text") or facts.get("licencia_vencimiento"), 120)
    license_needs_review = bool(facts.get("license_needs_review", False))

    if license_expiry_text and license_status in {None, "INCIERTO"}:
        license_status = "SI_PROBABLE"
        license_needs_review = True

    medical_status = _clean_choice(facts.get("medical_status") or facts.get("apto_medico"), {"SI", "NO", "INCIERTO", "SI_PROBABLE"})
    medical_expiry_text = _clean_text(facts.get("medical_expiry_text") or facts.get("apto_vencimiento"), 120)
    if medical_expiry_text and medical_status in {None, "INCIERTO"}:
        medical_status = "SI_PROBABLE"

    extracted = {
        "full_name": _clean_text(facts.get("full_name") or facts.get("nombre_completo"), 120),
        "age": _clean_age(facts.get("age") or facts.get("edad")),
        "phone": _clean_phone(facts.get("phone") or facts.get("telefono")),
        "city_raw": city_raw,
        "license_status": license_status,
        "license_type": _clean_text(facts.get("license_type") or facts.get("tipo_licencia"), 40),
        "license_expiry_text": license_expiry_text,
        "license_needs_review": license_needs_review,
        "experience_text": _clean_text(facts.get("experience_text") or facts.get("experiencia_quinta_rueda"), 120),
        "medical_status": medical_status,
        "medical_expiry_text": medical_expiry_text,
        "availability_travel": _clean_choice(facts.get("availability_travel") or facts.get("disponibilidad_viajar"), {"SI", "NO", "INCIERTO"}),
        "callback_requested": bool(facts.get("callback_requested", False)),
        "callback_window": _clean_text(facts.get("callback_window") or facts.get("horario_llamada"), 120),
        "candidate_questions": _compact_list(facts.get("candidate_questions") or facts.get("dudas")),
        "objections": _compact_list(facts.get("objections") or facts.get("objeciones")),
        "risk_notes": _compact_list(facts.get("risk_notes") or facts.get("riesgos")),
        "summary_note": _clean_text(facts.get("summary_note") or facts.get("observacion"), 300),
    }

    return extracted


def _fields_from_extraction(
    extracted: dict[str, Any],
    profile_snapshot: dict[str, Any],
    callback_schedule: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], list[str]]:
    fields: dict[str, Any] = {}
    notes: list[str] = []
    callback_schedule = callback_schedule or {}

    city_fields = _city_fields(extracted.get("city_raw"))
    fields.update(city_fields)

    if extracted.get("full_name"):
        fields["nombre_completo"] = extracted["full_name"]
    if extracted.get("age"):
        fields["edad"] = extracted["age"]
    if extracted.get("phone"):
        fields["telefono"] = extracted["phone"]
    if extracted.get("license_status"):
        status = extracted["license_status"]
        fields["licencia_federal"] = "SI" if status == "SI_PROBABLE" else status
    if extracted.get("license_type"):
        fields["tipo_licencia"] = extracted["license_type"]
    if extracted.get("experience_text"):
        fields["experiencia_quinta_rueda"] = extracted["experience_text"]
    if extracted.get("medical_status"):
        status = extracted["medical_status"]
        fields["apto_medico"] = "SI" if status == "SI_PROBABLE" else status
    if extracted.get("availability_travel"):
        fields["disponibilidad_viajar"] = extracted["availability_travel"]

    if extracted.get("license_expiry_text"):
        notes.append(f"Licencia/vigencia mencionada: {extracted['license_expiry_text']}")
    if extracted.get("license_needs_review"):
        notes.append("Requiere revisión CH por vigencia o condición de licencia")
        fields["requires_human"] = True
        fields["risk_level"] = "medium"
    if extracted.get("medical_expiry_text"):
        notes.append(f"Apto médico/vigencia mencionada: {extracted['medical_expiry_text']}")
        fields["requires_human"] = True
        fields["risk_level"] = "medium"
    if extracted.get("callback_requested"):
        window = extracted.get("callback_window") or "sin horario específico"
        due_time = callback_schedule.get("callback_due_local_time")
        due_label = callback_schedule.get("callback_due_label")
        if due_time:
            notes.append(
                f"Solicita llamada/contacto de Capital Humano: {window}. "
                f"Hora sugerida de contacto: {due_time} ({callback_schedule.get('callback_timezone')})"
            )
        else:
            notes.append(f"Solicita llamada/contacto de Capital Humano: {window}")
        if due_label:
            notes.append(f"Callback operativo agendable: {due_label}")
        fields["requires_human"] = True
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



def _drop_speculative_experience_from_lead(lead: dict) -> dict:
    """
    Remove speculative experience_text from lead extraction.

    The bot must not store "experiencia_quinta_rueda" when the candidate only
    asked whether they can continue or whether they are eligible.
    """
    if not isinstance(lead, dict):
        return lead

    extracted = lead.get("extracted")
    if not isinstance(extracted, dict):
        return lead

    exp = str(extracted.get("experience_text") or "").lower()

    speculative = any(marker in exp for marker in (
        "no está claro",
        "no esta claro",
        "no proporciona",
        "pregunta si",
        "pregunta sobre",
        "expresa interés",
        "expresa interes",
        "interés en conducir",
        "interes en conducir",
        "no menciona experiencia",
        "no indica experiencia",
        "posibilidad de conducir",
    ))

    if speculative:
        extracted["experience_text"] = None

        updated = lead.get("updated_fields")
        if isinstance(updated, list):
            lead["updated_fields"] = [
                item for item in updated
                if item != "experiencia_quinta_rueda"
            ]

    return lead


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
Only extract facts from the current message and clear conversation context.

Allowed values:
- license_status: SI, NO, SI_PROBABLE, INCIERTO
- medical_status: SI, NO, SI_PROBABLE, INCIERTO
- availability_travel: SI, NO, INCIERTO

If the candidate says a license expires soon or gives a future expiration window,
that usually implies they have a license. Use license_status=SI_PROBABLE and
license_needs_review=true unless they clearly say they do not have one.
If the candidate says their medical certificate/card expires soon, use
medical_status=SI_PROBABLE and medical_expiry_text with the mentioned timing.
If the candidate asks for a call, set callback_requested=true and capture the requested time window.

=== CURRENT PROFILE ===
{json.dumps(profile_snapshot, ensure_ascii=False, default=str)}

=== CONVERSATION MEMORY ===
{json.dumps(memory, ensure_ascii=False, default=str)}

=== CURRENT MESSAGE ===
{message}

Return JSON:
{{
  "facts": {{
    "full_name": null,
    "age": null,
    "phone": null,
    "city_raw": null,
    "license_status": null,
    "license_type": null,
    "license_expiry_text": null,
    "license_needs_review": false,
    "experience_text": null,
    "medical_status": null,
    "medical_expiry_text": null,
    "availability_travel": null,
    "callback_requested": false,
    "callback_window": null,
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

    callback_schedule = _callback_schedule(extracted.get("callback_window")) if extracted.get("callback_requested") else {}
    fields, notes = _fields_from_extraction(extracted, profile_snapshot, callback_schedule)
    updated = bool(fields)
    aggregate_risk_sync = None

    if conversation_key and fields:
        update_candidate_profile(conversation_key, fields)
        aggregate_risk_sync = sync_conversation_risk_from_profile(
            conversation_key,
            risk_level=fields.get("risk_level") or state.get("risk_level") or "low",
            requires_human=bool(fields.get("requires_human", False)),
            intent=state.get("intent"),
        )
        log_event(
            conversation_key=conversation_key,
            event_type="lead_ingested",
            stage_from=state.get("current_stage"),
            stage_to=state.get("current_stage"),
            intent=state.get("intent"),
            risk_level=fields.get("risk_level") or state.get("risk_level") or "low",
            requires_human=bool(fields.get("requires_human", False)),
            metadata={
                "extracted": extracted,
                "callback_schedule": callback_schedule,
                "updated_fields": sorted(fields.keys()),
                "notes": notes,
                "aggregate_risk_sync": aggregate_risk_sync,
            },
        )

    merged_profile = {**profile_snapshot, **fields}
    state_risk = aggregate_risk_sync.get("risk_level") if aggregate_risk_sync else state.get("risk_level")
    state_requires_human = (
        bool(aggregate_risk_sync.get("requires_human"))
        if aggregate_risk_sync
        else bool(state.get("requires_human", False)) or bool(fields.get("requires_human", False))
    )

    return {
        "profile_snapshot": merged_profile,
        "risk_level": state_risk,
        "requires_human": state_requires_human,
        "lead_ingestion": {
            "enabled": True,
            "updated": updated,
            "extracted": extracted,
            "callback_schedule": callback_schedule,
            "updated_fields": sorted(fields.keys()),
            "notes": notes,
            "aggregate_risk_sync": aggregate_risk_sync,
        },
        "events": [
            {
                "type": "lead_ingested",
                "updated": updated,
                "updated_fields": sorted(fields.keys()),
                "notes_count": len(notes),
                "callback_due_local_time": callback_schedule.get("callback_due_local_time"),
                "aggregate_risk_sync": aggregate_risk_sync,
            }
        ],
    }
