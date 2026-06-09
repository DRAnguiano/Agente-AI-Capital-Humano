import os
from typing import Any

import httpx

from .db import get_conn

PENDING_TEXT = "Pendiente"

OFFICIAL_LABELS: frozenset[str] = frozenset({
    "aclaracion_pendiente",
    "bot_activo",
    "cecati",
    "disponible_acudir",
    "documentos",
    "escuelita",
    "falta_apto",
    "falta_ciudad",
    "falta_experiencia",
    "falta_licencia",
    "falta_unidad",
    "foraneo",
    "jerga_ambigua",
    "local_laguna",
    "objetivo_full_sencillo",
    "perfil_listo",
    "reingreso_verificar",
    "requiere_agente",
    "requiere_revision_ch",
    "riesgo_alto",
    "seguimiento",
    "urgente",
    "validar_traslado",
})


def _text(value: Any, default: str = "No disponible") -> str:
    if value is None:
        return default
    value = str(value).strip()
    return value or default


def _human_fact(value: Any, default: str = PENDING_TEXT) -> str:
    raw = _text(value, default)
    mapping = {
        "asked": "Preguntó",
        "sí": "Sí",
        "si": "Sí",
        "yes": "Sí",
        "true": "Sí",
        "vigente": "Vigente",
        "mencionada": "Mencionada",
        "pending_update": "Pendiente de actualización",
        "pending_candidate_will_send": "Pendiente, candidato enviará",
        "pendiente_por_candidato": "Pendiente, candidato enviará",
        "en_ruta_o_no_disponible_ahora": "En ruta / no disponible ahora",
    }
    return mapping.get(raw, raw)


def _is_yes(value: Any) -> bool:
    return str(value or "").strip().lower() in {"sí", "si", "yes", "true", "1"}


def _is_vigente(value: Any) -> bool:
    return str(value or "").strip().lower() in {"vigente", "sí", "si", "yes", "true"}



def _risk(value: str | None) -> str:
    return {"low": "Bajo", "medium": "Medio", "high": "Alto"}.get((value or "").lower(), value or "No disponible")


# _temperatura eliminado (Fase 0 / F26): la "temperatura" del lead es subjetiva si no
# está estrictamente calculada; se deprecó y ya no se muestra en la nota privada.


def _stage(value: str | None) -> str:
    return {
        "new": "Nuevo",
        "interested": "Interesado",
        "vacancy_info_shared": "Información de vacante compartida",
        "profiled_viable": "Perfil viable",
        "potential_candidate_documents_pending": "Pendiente de documentos",
        "followup_pending": "Seguimiento pendiente",
        "documents_pending": "Pendiente de documentos",
        "profile_hint_collected": "Perfil en captura",
        "profile_ready": "Perfil listo",
        "apto_pending_update": "Apto pendiente de actualización",
        "human_review_required": "Revisión de Capital Humano",
        "closed": "Cerrado",
        "discarded": "Descartado",
    }.get((value or "").lower(), value or "No disponible")


def _normalize_labels(labels) -> list[str]:
    return sorted({str(label or "").strip().lower() for label in (labels or []) if str(label or "").strip()})


def _filter_official_labels(labels) -> list[str]:
    return [lbl for lbl in _normalize_labels(labels) if lbl in OFFICIAL_LABELS]


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


def _expiry_urgency(expiration_text: str) -> str | None:
    """Classify document expiry urgency from free-text like 'vence en 2 semanas'."""
    if not expiration_text:
        return None
    t = expiration_text.lower()
    # Urgent: days or weeks
    if any(w in t for w in ("día", "dia", "días", "dias", "semana", "semanas")):
        return "urgente"
    # Watch: months 1–5
    for n in range(1, 6):
        if f"{n} mes" in t or f"{n} mes" in t:
            return "revisar"
    # OK: 6+ months or years — no urgency label
    return None


def calculate_candidate_labels(context: dict[str, Any]) -> list[str]:
    lead = context.get("lead") or {}
    facts = context.get("facts") or {}
    facts_summary = lead.get("facts_summary") or {}
    labels = {"bot_activo"}

    if lead.get("requires_human"):
        labels.update({"requiere_agente", "requiere_revision_ch"})
    if (lead.get("risk_level") or "").lower() == "high":
        labels.add("riesgo_alto")

    has_license    = bool(facts.get("license.category"))
    has_medical    = facts.get("medical.apto_status") in {"vigente", "sí", "si"}
    has_experience = (
        facts.get("experience.fifth_wheel") in {"sí", "si", "yes", "true"}
        or bool(facts.get("experience.vehicle_type"))
        or bool(facts.get("experience.years"))
    )
    has_letters    = facts.get("documents.labor_letters_status") in {"available", "sí", "si"} or \
                     facts.get("documents.labor_letters") in {"available", "sí", "si"}

    if not has_license:
        labels.add("falta_licencia")
    if not has_medical:
        labels.add("falta_apto")
    if not has_letters and (has_license or has_experience):
        labels.add("documentos")

    if has_medical:
        labels.discard("falta_apto")

    if facts.get("documents.submission_status") == "pending_candidate_will_send":
        labels.add("seguimiento")
    if facts.get("candidate.availability_status") == "en_ruta_o_no_disponible_ahora":
        labels.add("seguimiento")

    city = (facts.get("candidate.city") or "").lower()
    if city and not any(local in city for local in ["torreón", "torreon", "gómez palacio", "gomez palacio", "lerdo", "matamoros"]):
        labels.update({"foraneo", "validar_traslado"})

    accepted = facts.get("candidate.vacancy_accepted") in {"sí", "si", "yes", "true"}
    if has_experience and has_license and has_medical and accepted:
        labels.update({"perfil_listo", "requiere_revision_ch"})
        labels.discard("falta_licencia")
        labels.discard("falta_apto")
        labels.discard("documentos")

    return _filter_official_labels(labels)


def render_candidate_note(context: dict[str, Any], labels: list[str], fallback_last_message: str | None = None, channel_label: str | None = None) -> str:
    lead = context.get("lead") or {}
    conversation = context.get("conversation") or {}
    facts = context.get("facts") or {}
    last = context.get("last_message") or {}

    message = _text(fallback_last_message or last.get("message"), "Sin mensaje reciente")[:500]

    fifth_wheel_raw = _fact(facts, "experience.fifth_wheel")
    vehicle_type_raw = _fact(facts, "experience.vehicle_type", default="")
    years = _fact(facts, "experience.years")
    license_category = _fact(facts, "license.category")
    license_exp_text = _fact(facts, "license.expiration_text", default="")
    medical_status_raw = _fact(facts, "medical.apto_status", "document.apto_status", "documents.general_status")
    apto_exp_text = _fact(facts, "medical.apto_expiration_text", default="")
    documents_status_raw = _fact(facts, "documents.submission_status", "documents.labor_letters", "interest.requirements_documents")
    city = _fact(facts, "candidate.city")
    availability_raw = _fact(facts, "candidate.availability_status")
    payment_raw = _fact(facts, "interest.payment", default="No detectado")

    if vehicle_type_raw == "sencillo":
        fifth_wheel = "Sencillo (escuelita – evalúa Cap. Humano)"
    elif vehicle_type_raw in ("quinta_rueda", "full"):
        fifth_wheel = "Sí"
    else:
        fifth_wheel = _human_fact(fifth_wheel_raw)
    medical_status = _human_fact(medical_status_raw)
    documents_status = _human_fact(documents_status_raw)
    availability = _human_fact(availability_raw)
    payment = _human_fact(payment_raw, "No detectado")

    next_action = _text(lead.get("next_best_action"), "Continuar flujo automático según etapa actual.")
    memory = _text(lead.get("memory_summary"), "Candidato en seguimiento. Falta completar datos clave del perfil.")
    stage_value = lead.get("funnel_stage")

    # Protección contra memoria vieja: si el apto está vigente, no pedir actualización.
    if _is_vigente(medical_status_raw):
        if "actualice apto" in next_action.lower() or "actualizar apto" in next_action.lower():
            next_action = "Continuar revisión del perfil; apto médico reportado como vigente."
        if "vencido" in memory.lower() or "próximo a vencer" in memory.lower() or "proximo a vencer" in memory.lower():
            memory = "El candidato reportó apto médico vigente."
        if str(stage_value or "").lower() == "apto_pending_update":
            stage_value = "profile_hint_collected"

    has_experience = _is_yes(fifth_wheel_raw) or fifth_wheel_raw != PENDING_TEXT or years != PENDING_TEXT
    has_license = license_category != PENDING_TEXT
    has_medical = _is_vigente(medical_status_raw)
    has_documents = documents_status_raw != PENDING_TEXT
    has_city = city != PENDING_TEXT

    blocker = "Faltan datos base del perfil"
    if has_experience and has_license and has_medical and has_documents and has_city:
        blocker = "Validar documentos con Capital Humano"
    elif documents_status_raw == "pending_candidate_will_send":
        blocker = "Esperando envío documental"
    elif not has_experience:
        blocker = "Falta confirmar experiencia en quinta rueda/full"
    elif vehicle_type_raw == "sencillo":
        blocker = "Experiencia en sencillo (escuelita) – Capital Humano valida viabilidad"
    elif not has_license:
        blocker = "Falta validar licencia federal/tipo"
    elif not has_medical:
        blocker = "Falta validar apto médico"
    elif not has_city:
        blocker = "Falta confirmar ciudad de residencia"

    requires_human = "Sí" if lead.get("requires_human") else "No"

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
        f"Licencia: {_human_fact(license_category)}"
        + (f" · vigencia {apto_exp_text}" if license_exp_text and license_exp_text != PENDING_TEXT else "") + "\n"
        f"Apto médico: {medical_status}"
        + (f" · {apto_exp_text}" if apto_exp_text and apto_exp_text != PENDING_TEXT else "") + "\n"
        f"Cartas/documentos: {documents_status}\n"
        f"Ciudad: {city}\n"
        f"Disponibilidad actual: {availability}\n"
        f"Interés en pago/compensación: {payment}\n\n"
        "📍 Embudo\n"
        f"Etapa: {_stage(stage_value)}\n"
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
