import os
from typing import Any

import httpx

from .db import get_conn

PENDING_TEXT = "Pendiente"


def _text(value: Any, default: str = "No disponible") -> str:
    if value is None:
        return default
    value = str(value).strip()
    return value or default


def _risk(value: str | None) -> str:
    return {"low": "Bajo", "medium": "Medio", "high": "Alto"}.get((value or "").lower(), value or "No disponible")


def _stage(value: str | None) -> str:
    return {
        "new": "Nuevo",
        "interested": "Interesado",
        "vacancy_info_shared": "Información de vacante compartida",
        "profiled_viable": "Perfil viable",
        "potential_candidate_documents_pending": "Pendiente de documentos",
        "followup_pending": "Seguimiento pendiente",
        "profile_ready": "Perfil listo",
        "human_review_required": "Revisión de Capital Humano",
        "closed": "Cerrado",
        "discarded": "Descartado",
    }.get((value or "").lower(), value or "No disponible")


def _normalize_labels(labels) -> list[str]:
    return sorted({str(label or "").strip().lower() for label in (labels or []) if str(label or "").strip()})


def _facts_map(rows: list[dict[str, Any]]) -> dict[str, str]:
    facts = {}
    for row in rows:
        group = str(row.get("fact_group") or "").strip().lower()
        key = str(row.get("fact_key") or "").strip().lower()
        value = str(row.get("fact_value") or "").strip()
        if group and key and value:
            facts[f"{group}.{key}"] = value
    return facts


def _fact(facts: dict[str, str], *keys: str, default: str = PENDING_TEXT) -> str:
    for key in keys:
        if facts.get(key):
            return facts[key]
    return default


def get_lead_note_context(lead_key: str) -> dict[str, Any]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT lead_key, display_name, phone, source_channel, lead_status,
                       funnel_stage, next_best_action, memory_summary, facts_summary,
                       risk_level, requires_human, first_seen_at, last_seen_at, updated_at
                FROM rh_leads_v2
                WHERE lead_key = %(lead_key)s
                LIMIT 1;
                """,
                {"lead_key": lead_key},
            )
            lead = cur.fetchone()

            cur.execute(
                """
                SELECT lead_key, conversation_key, channel, channel_user_id,
                       chatwoot_account_id, chatwoot_inbox_id, chatwoot_conversation_id,
                       chatwoot_contact_id, is_primary, external_metadata, updated_at
                FROM rh_lead_conversations_v2
                WHERE lead_key = %(lead_key)s
                ORDER BY is_primary DESC, updated_at DESC
                LIMIT 1;
                """,
                {"lead_key": lead_key},
            )
            conversation = cur.fetchone()

            cur.execute(
                """
                SELECT fact_group, fact_key, fact_value, confidence, source,
                       source_message_id, source_text, updated_at
                FROM rh_lead_facts_v2
                WHERE lead_key = %(lead_key)s
                ORDER BY fact_group, fact_key, updated_at DESC;
                """,
                {"lead_key": lead_key},
            )
            facts_rows = cur.fetchall()

            cur.execute(
                """
                SELECT role, message, source_message_id, created_at
                FROM rh_lead_messages_v2
                WHERE lead_key = %(lead_key)s
                ORDER BY created_at DESC
                LIMIT 1;
                """,
                {"lead_key": lead_key},
            )
            last_message = cur.fetchone()

    facts_rows = [dict(row) for row in facts_rows or []]
    return {
        "lead": dict(lead) if lead else {},
        "conversation": dict(conversation) if conversation else {},
        "facts_rows": facts_rows,
        "facts": _facts_map(facts_rows),
        "last_message": dict(last_message) if last_message else {},
    }


def calculate_candidate_labels(context: dict[str, Any]) -> list[str]:
    lead = context.get("lead") or {}
    facts = context.get("facts") or {}
    facts_summary = lead.get("facts_summary") or {}
    labels = {"bot_activo"}

    if lead.get("requires_human"):
        labels.update({"requiere_agente", "requiere_revision_ch"})
    if (lead.get("risk_level") or "").lower() == "high":
        labels.add("riesgo_alto")
    if facts.get("documents.submission_status") or facts.get("interest.requirements_documents"):
        labels.add("documentos")
    if facts.get("documents.submission_status") == "pending_candidate_will_send":
        labels.add("seguimiento")
    if facts.get("candidate.availability_status") == "en_ruta_o_no_disponible_ahora":
        labels.add("seguimiento")

    city = (facts.get("candidate.city") or "").lower()
    if city and not any(local in city for local in ["torreón", "torreon", "gómez palacio", "gomez palacio", "lerdo", "matamoros"]):
        labels.update({"foraneo", "validar_traslado"})

    if isinstance(facts_summary, dict) and facts_summary.get("profile_missing_fields"):
        labels.add("aclaracion_pendiente")

    has_experience = facts.get("experience.fifth_wheel") in {"sí", "si", "yes", "true"}
    has_license = bool(facts.get("license.category"))
    has_medical = facts.get("medical.apto_status") in {"vigente", "sí", "si"}
    accepted = facts.get("candidate.vacancy_accepted") in {"sí", "si", "yes", "true"}
    if has_experience and has_license and has_medical and accepted:
        labels.update({"perfil_listo", "requiere_revision_ch"})
        labels.discard("aclaracion_pendiente")

    return _normalize_labels(labels)


def render_candidate_note(context: dict[str, Any], labels: list[str], fallback_last_message: str | None = None, channel_label: str | None = None) -> str:
    lead = context.get("lead") or {}
    conversation = context.get("conversation") or {}
    facts = context.get("facts") or {}
    last = context.get("last_message") or {}

    message = _text(last.get("message") or fallback_last_message, "Sin mensaje reciente")[:500]
    next_action = _text(lead.get("next_best_action"), "Continuar flujo automático según etapa actual.")
    memory = _text(lead.get("memory_summary"), "Candidato en seguimiento. Falta completar datos clave del perfil.")
    requires_human = "Sí" if lead.get("requires_human") else "No"

    fifth_wheel = _fact(facts, "experience.fifth_wheel")
    years = _fact(facts, "experience.years")
    license_category = _fact(facts, "license.category")
    medical_status = _fact(facts, "medical.apto_status")
    documents_status = _fact(facts, "documents.submission_status", "interest.requirements_documents")
    city = _fact(facts, "candidate.city")
    availability = _fact(facts, "candidate.availability_status")
    payment = _fact(facts, "interest.payment", default="No detectado")

    blocker = "Faltan datos base del perfil"
    if documents_status == "pending_candidate_will_send":
        blocker = "Esperando envío documental"
    elif fifth_wheel == PENDING_TEXT:
        blocker = "Falta confirmar experiencia en quinta rueda/full"
    elif license_category == PENDING_TEXT:
        blocker = "Falta validar licencia federal/tipo"
    elif medical_status == PENDING_TEXT:
        blocker = "Falta validar apto médico"

    return (
        "🤖 Nota IA: Seguimiento de candidato\n\n"
        f"Acción: {next_action}\n"
        f"Último mensaje: \"{message}\"\n\n"
        "👤 Contacto\n"
        f"Nombre: {_text(lead.get('display_name'))}\n"
        f"Teléfono: {_text(lead.get('phone'))}\n"
        f"Canal: {_text(channel_label or conversation.get('channel') or lead.get('source_channel'), 'Chatwoot')}\n\n"
        "🧠 Memoria breve\n"
        f"{memory}\n\n"
        "📋 Perfil detectado\n"
        f"Quinta rueda/full: {fifth_wheel}\n"
        f"Experiencia: {years}\n"
        f"Licencia: {license_category}\n"
        f"Apto médico: {medical_status}\n"
        f"Cartas/documentos: {documents_status}\n"
        f"Ciudad: {city}\n"
        f"Disponibilidad actual: {availability}\n"
        f"Interés en pago/compensación: {payment}\n\n"
        "📍 Embudo\n"
        f"Etapa: {_stage(lead.get('funnel_stage'))}\n"
        f"Bloqueo actual: {blocker}\n"
        f"Riesgo: {_risk(lead.get('risk_level'))}\n"
        f"Requiere humano: {requires_human}\n\n"
        "⏭️ Siguiente acción\n"
        f"{next_action}\n\n"
        "🏷️ Labels\n"
        f"{', '.join(labels) if labels else 'N/D'}"
    )


async def _chatwoot_post(path: str, body: dict[str, Any]) -> dict[str, Any]:
    base_url = os.getenv("CHATWOOT_BASE_URL", "").strip().rstrip("/")
    token = os.getenv("CHATWOOT_API_TOKEN", "").strip()
    if not base_url:
        raise RuntimeError("CHATWOOT_BASE_URL is not configured")
    if not token:
        raise RuntimeError("CHATWOOT_API_TOKEN is not configured")
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{base_url}{path}",
            headers={"api_access_token": token, "Content-Type": "application/json"},
            json=body,
        )
        response.raise_for_status()
        return response.json()


async def sync_chatwoot_candidate_note(*, lead_key: str, account_id: int | str, conversation_id: int | str, fallback_last_message: str | None = None, channel_label: str | None = None) -> dict[str, Any]:
    context = get_lead_note_context(lead_key)
    if not context.get("lead"):
        return {"ok": False, "skipped": True, "reason": "lead_not_found", "lead_key": lead_key}

    labels = calculate_candidate_labels(context)
    note = render_candidate_note(context, labels, fallback_last_message=fallback_last_message, channel_label=channel_label)

    note_response = await _chatwoot_post(
        f"/api/v1/accounts/{account_id}/conversations/{conversation_id}/messages",
        {"content": note, "message_type": "outgoing", "private": True},
    )
    labels_response = await _chatwoot_post(
        f"/api/v1/accounts/{account_id}/conversations/{conversation_id}/labels",
        {"labels": labels},
    )

    return {
        "ok": True,
        "lead_key": lead_key,
        "labels": labels,
        "note_message_id": note_response.get("id"),
        "labels_response": labels_response,
    }
