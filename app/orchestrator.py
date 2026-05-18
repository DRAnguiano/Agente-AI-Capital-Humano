import re
from typing import Any

from .db import (
    create_handoff,
    find_city_catalog_match,
    get_conversation_state,
    log_event,
    save_message,
    save_rag_audit,
    update_candidate_profile,
    update_stage,
    upsert_conversation,
)
from .indexer import call_llm, retrieve_context_for_guardrail
from .persona_config import SYSTEM_PROMPT


def _norm(text: str) -> str:
    text = (text or "").lower().strip()
    replacements = {
        "á": "a",
        "é": "e",
        "í": "i",
        "ó": "o",
        "ú": "u",
        "ñ": "n",
    }
    for a, b in replacements.items():
        text = text.replace(a, b)
    return text


def _history_text(messages: list[dict[str, Any]]) -> str:
    if not messages:
        return "No hay historial previo."

    lines = []
    for item in messages[-8:]:
        role = item.get("role", "user")
        msg = item.get("message", "")
        lines.append(f"{role}: {msg}")
    return "\n".join(lines)


def _strip_followup_questions(text: str) -> str:
    if not text:
        return text

    banned_patterns = [
        r"\n*¿Quieres que te aclare algo más de la vacante\?\s*$",
        r"\n*¿Quieres que te aclare algo más\?\s*$",
        r"\n*¿Tienes alguna otra duda\?\s*$",
        r"\n*¿Te gustaría saber algo más\?\s*$",
        r"\n*¿Deseas que te comparta más información\?\s*$",
        r"\n*¿Quieres que te ayude con algo más\?\s*$",
        r"\n*¿Hay algo más que quieras saber\?\s*$",
        r"\n*¿Te puedo ayudar con algo más\?\s*$",
    ]

    cleaned = text.strip()
    for pattern in banned_patterns:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE).strip()

    return cleaned


def detect_intent_and_risk(message: str) -> dict[str, Any]:
    m = _norm(message)

    high_risk_patterns = [
        "me aseguran que me van a contratar",
        "demanda",
        "demandar",
        "acoso",
        "discriminacion",
        "problema legal",
        "problemas legales",
        "antecedentes penales",
        "me corrieron",
        "accidente no reportado",
        "no reporte un accidente",
        "lesionado",
        "incapacidad",
        "embarazada",
        "enfermedad",
        "droga",
        "drogas",
        "antidoping",
        "no paso antidoping",
        "no pasaria antidoping",
        "mota",
        "marihuana",
        "cristal",
        "perico",
        "cocaina",
        "foco",
        "piedra",
        "alcohol en ruta",
        "tomar en ruta",
        "tomo en ruta",
        "manejo tomado",
        "manejo borracho",
        "manejar borracho",
        "manejo cansado",
        "manejo sin dormir",
        "uso sustancias",
        "sustancias para aguantar",
        "pelea",
        "peleas",
        "golpee",
        "golpear",
        "violencia",
        "arma",
        "armas",
        "robo",
        "robe",
        "robé",
        "huachicol",
        "combustible robado",
        "mercancia robada",
        "mercancía robada",
        "abandone unidad",
        "abandoné unidad",
        "abandono de unidad",
        "documentos falsos",
        "documento falso",
        "licencia falsa",
        "apto falso",
        "factura falsa",
    ]

    rcontrol_neutral_patterns = [
        "r-control",
        "r control",
        "recurso confiable",
    ]

    boletin_patterns = [
        "boletinado",
        "boletinada",
        "me boletinaron",
        "estoy boletinado",
        "estoy boletinada",
        "me reportaron",
        "reportado en r-control",
        "reportado en r control",
        "incidencia en r-control",
        "incidencia en r control",
        "tengo una incidencia",
        "incidencia activa",
        "mala referencia",
        "me quemaron",
        "salí mal",
        "sali mal",
        "problema con una empresa anterior",
        "bronca con una empresa anterior",
    ]

    followup_time_patterns = [
        "cuanto tiempo",
        "cuánto tiempo",
        "kuanto tiempo",
        "en cuanto tiempo",
        "en cuánto tiempo",
        "en kuanto tiempo",
        "cuando me responden",
        "cuándo me responden",
        "cuando me responde",
        "cuándo me responde",
        "cuando me rezponde",
        "kuando me responde",
        "kuando me rezponde",
        "en cuanto me responden",
        "en cuánto me responden",
        "en kuanto me responden",
        "me urge",
        "urge",
        "tengo prisa",
        "ocupo respuesta",
        "me interesa mucho",
        "ando buscando trabajo ya",
        "me pueden contestar",
        "me pueden responder",
    ]

    documents_complete_patterns = [
        "ya subi documentos",
        "ya subí documentos",
        "ya mande documentos",
        "ya mandé documentos",
        "ya envie documentos",
        "ya envié documentos",
        "ya comparti documentos",
        "ya compartí documentos",
        "ya entregue documentos",
        "ya entregué documentos",
        "ya subi todo",
        "ya subí todo",
        "ya mande todo",
        "ya mandé todo",
        "ya envie todo",
        "ya envié todo",
        "ya entregue todo",
        "ya entregué todo",
        "ya tengo toda la documentacion",
        "ya tengo toda la documentación",
        "ya tengo mis documentos",
        "que sigue",
        "qué sigue",
        "cual es el siguiente paso",
        "cuál es el siguiente paso",
        "ya quedo mi proceso",
        "ya quedó mi proceso",
    ]

    foraneo_travel_patterns = [
        "soy foraneo",
        "soy foráneo",
        "vengo de fuera",
        "soy de fuera",
        "foraneo",
        "foráneo",
        "boleto",
        "autobus",
        "autobús",
        "camion a torreon",
        "camión a torreón",
        "camion para torreon",
        "camión para torreón",
        "me compran boleto",
        "me pagan el viaje",
        "me apoyan con el boleto",
        "apoyo de traslado",
        "traslado a torreon",
        "traslado a torreón",
        "ir a torreon",
        "ir a torreón",
        "viaje a torreon",
        "viaje a torreón",
    ]

    salary_patterns = [
        "cuanto pagan exactamente",
        "cuánto pagan exactamente",
        "sueldo exacto",
        "salario exacto",
        "me aseguran el sueldo",
        "cuanto me van a pagar",
        "cuánto me van a pagar",
        "me garantizan el sueldo",
        "me prometen el sueldo",
    ]

    ambiguous_slang_patterns = [
        "me gusta cachimbear",
        "me gusta mucho cachimbear",
        "ando en cachimbas",
        "me gusta andar en cachimbas",
        "me quedo en la cachimba",
        "me gusta la cachimba",
        "me gusta el ambiente de carretera",
        "me gusta convivir en ruta",
        "me gusta el desmadre en ruta",
    ]

    rag_patterns = [
        "documentos",
        "que piden",
        "qué piden",
        "requisitos",
        "prestaciones",
        "bono",
        "bonos",
        "pago",
        "pagos",
        "sueldo",
        "salario",
        "apto medico",
        "apto médico",
        "licencia",
        "viajes",
        "viaticos",
        "viáticos",
        "patios",
        "base",
        "bases",
        "r-control",
        "r control",
        "recurso confiable",
        "cachimba",
        "cachimbear",
        "codigo 10",
        "código 10",
        "10-4",
        "10-8",
        "10-20",
        "10-28",
        "horario",
        "capital humano",
        "seguimiento",
    ]

    if any(p in m for p in high_risk_patterns):
        return {
            "intent": "sensitive_handoff",
            "risk_level": "high",
            "requires_human": True,
            "requires_rag": False,
            "requires_clarification": False,
            "reason": "tema_sensible",
        }

    if any(p in m for p in boletin_patterns):
        return {
            "intent": "rcontrol_or_incident_handoff",
            "risk_level": "high",
            "requires_human": True,
            "requires_rag": False,
            "requires_clarification": False,
            "reason": "boletin_o_incidencia",
        }

    if any(p in m for p in followup_time_patterns):
        return {
            "intent": "followup_time_question",
            "risk_level": "low",
            "requires_human": False,
            "requires_rag": False,
            "requires_clarification": False,
            "reason": "pregunta_tiempo_respuesta",
        }

    if any(p in m for p in documents_complete_patterns):
        return {
            "intent": "documents_complete_followup",
            "risk_level": "low",
            "requires_human": False,
            "requires_rag": False,
            "requires_clarification": False,
            "reason": "documentacion_o_siguiente_paso",
        }

    if any(p in m for p in foraneo_travel_patterns):
        return {
            "intent": "foraneo_travel_question",
            "risk_level": "low",
            "requires_human": False,
            "requires_rag": False,
            "requires_clarification": False,
            "reason": "foraneo_o_boleto",
        }

    if any(p in m for p in salary_patterns):
        return {
            "intent": "salary_sensitive",
            "risk_level": "medium",
            "requires_human": True,
            "requires_rag": True,
            "requires_clarification": False,
            "reason": "sueldo_o_compromiso_economico",
        }

    if any(p in m for p in ambiguous_slang_patterns):
        return {
            "intent": "ambiguous_slang_clarification",
            "risk_level": "medium",
            "requires_human": False,
            "requires_rag": False,
            "requires_clarification": True,
            "reason": "jerga_ambigua",
        }

    if any(p in m for p in rcontrol_neutral_patterns):
        return {
            "intent": "document_question",
            "risk_level": "low",
            "requires_human": False,
            "requires_rag": True,
            "requires_clarification": False,
            "reason": None,
        }

    if "?" in message or any(p in m for p in rag_patterns):
        return {
            "intent": "document_question",
            "risk_level": "low",
            "requires_human": False,
            "requires_rag": True,
            "requires_clarification": False,
            "reason": None,
        }

    return {
        "intent": "candidate_answer",
        "risk_level": "low",
        "requires_human": False,
        "requires_rag": False,
        "requires_clarification": False,
        "reason": None,
    }


def _clean_city_text(message: str) -> str:
    """
    Limpia respuestas tipo:
    - Soy de Nuevo Laredo
    - Vivo en Torreón
    - Estoy en San Diego California
    - Radico en Gómez
    """
    raw = (message or "").strip()
    if not raw:
        return raw

    cleaned = raw.strip(" .,!¡¿?;:'\"").strip()

    patterns = [
        r"^(soy\s+de|soi\s+de|vivo\s+en|vivo\s+por|estoy\s+en|ando\s+en|radico\s+en|resido\s+en|me\s+ubico\s+en|me\s+encuentro\s+en)\s+",
        r"^(de\s+)",
        r"^(en\s+)",
    ]

    for pattern in patterns:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE).strip()

    cleaned = cleaned.strip(" .,!¡¿?;:'\"").strip()

    if len(cleaned) > 100:
        return raw

    return cleaned or raw


def _city_fields_from_catalog(message: str, current_stage: str | None) -> dict[str, Any]:
    """
    Consulta rh_city_catalog para normalizar ciudad.

    Solo busca ciudad cuando estamos en una etapa donde tiene sentido:
    START / NEW_LEAD / ASK_CITY.
    """
    stage = current_stage or "START"

    if stage not in {"START", "NEW_LEAD", "ASK_CITY"}:
        return {}

    if not message or len(message.strip()) > 120:
        return {}

    cleaned_city = _clean_city_text(message)

    match = find_city_catalog_match(cleaned_city) or find_city_catalog_match(message)

    if not match:
        if stage == "ASK_CITY" and len(cleaned_city.strip()) <= 60:
                        return {
                "ciudad": cleaned_city.strip(),
                "ciudad_raw": message.strip(),
                "estado_region": None,
                "pais_codigo": None,
                "pais_nombre": None,
                "city_group": "No catalogada",
                "is_local_laguna": False,
                "is_foreign_country": False,
                "location_requires_ch_validation": True,
                "location_needs_travel_validation": True,
                "city_catalog_alias": None,
                "city_catalog_id": None,
                "observaciones": "Ciudad no encontrada en catálogo; validar manualmente si aplica.",
                "_city_catalog": None,
                "_city_requires_ch_validation": True,
            }
        return {}

    observaciones = (
        "Ciudad normalizada por catálogo: "
        f"{match.get('canonical_city')} / {match.get('state_region')} / "
        f"{match.get('country_code')} / {match.get('city_group')}."
    )

    if match.get("requires_ch_validation"):
        observaciones += " Requiere validación de Capital Humano por ubicación."

    return {
        "ciudad": match.get("canonical_city"),
        "ciudad_raw": message.strip(),
        "estado_region": match.get("state_region"),
        "pais_codigo": match.get("country_code"),
        "pais_nombre": match.get("country_name"),
        "city_group": match.get("city_group"),
        "is_local_laguna": bool(match.get("is_local_laguna")),
        "is_foreign_country": bool(match.get("is_foreign_country")),
        "location_requires_ch_validation": bool(match.get("requires_ch_validation")),
        "location_needs_travel_validation": bool(match.get("needs_travel_validation")),
        "city_catalog_alias": match.get("alias_text"),
        "city_catalog_id": match.get("id"),
        "observaciones": observaciones,
        "_city_catalog": match,
        "_city_requires_ch_validation": bool(match.get("requires_ch_validation")),
    }


def extract_profile_fields(message: str, current_stage: str | None) -> dict[str, Any]:
    m = _norm(message)
    fields: dict[str, Any] = {}

    age_match = re.search(r"\b(\d{2})\s*(anos|años)?\b", m)
    if age_match:
        age = int(age_match.group(1))
        if 18 <= age <= 75:
            fields["edad"] = age

    city_fields = _city_fields_from_catalog(message, current_stage)
    if city_fields:
        fields.update(city_fields)

    if "federal" in m or "licencia" in m:
        fields["licencia_federal"] = (
            "SI" if any(x in m for x in ["si", "sí", "tengo", "cuento", "federal"]) else "NO"
        )

        type_match = re.search(r"\b(tipo\s*)?([abe])\b", m)
        if type_match:
            fields["tipo_licencia"] = type_match.group(2).upper()

    if "apto" in m or "medico" in m or "médico" in m:
        fields["apto_medico"] = (
            "SI" if any(x in m for x in ["si", "sí", "tengo", "vigente", "cuento"]) else "NO"
        )

    if "viajar" in m or "disponibilidad" in m or "foraneo" in m or "foráneo" in m or "foraneas" in m:
        fields["disponibilidad_viajar"] = (
            "SI" if any(x in m for x in ["si", "sí", "tengo", "disponible", "cuento"]) else "NO"
        )

    exp_match = re.search(r"\b(\d{1,2})\s*(anos|años|año)\b", m)
    if exp_match and any(x in m for x in ["experiencia", "manejando", "quinta", "rueda", "tracto"]):
        fields["experiencia_quinta_rueda"] = f"{exp_match.group(1)} años"

    if current_stage == "ASK_LICENSE" and not fields.get("licencia_federal"):
        fields["licencia_federal"] = (
            "SI" if any(x in m for x in ["si", "sí", "tengo", "cuento", "federal"]) else "NO"
        )

    if current_stage == "ASK_EXPERIENCE" and not fields.get("experiencia_quinta_rueda"):
        fields["experiencia_quinta_rueda"] = message.strip()

    if current_stage == "ASK_APTO" and not fields.get("apto_medico"):
        fields["apto_medico"] = (
            "SI" if any(x in m for x in ["si", "sí", "tengo", "vigente", "cuento"]) else "NO"
        )

    if current_stage == "ASK_AVAILABILITY" and not fields.get("disponibilidad_viajar"):
        fields["disponibilidad_viajar"] = (
            "SI" if any(x in m for x in ["si", "sí", "tengo", "disponible", "cuento"]) else "NO"
        )

    return fields


def decide_next_stage(current_stage: str | None, fields: dict[str, Any]) -> tuple[str, str]:
    stage = current_stage or "START"

    if stage in ["START", "NEW_LEAD"]:
        if fields.get("ciudad"):
            return "ASK_LICENSE", "Gracias. ¿Cuentas con licencia federal vigente?"
        return "ASK_CITY", "Hola, gracias por tu interés. Para iniciar, ¿en qué ciudad te encuentras actualmente?"

    if stage == "ASK_CITY":
        return "ASK_LICENSE", "Gracias. ¿Cuentas con licencia federal vigente?"

    if stage == "ASK_LICENSE":
        return "ASK_EXPERIENCE", "Perfecto. ¿Cuántos años de experiencia tienes manejando quinta rueda?"

    if stage == "ASK_EXPERIENCE":
        return "ASK_APTO", "Gracias. ¿Cuentas con apto médico vigente?"

    if stage == "ASK_APTO":
        return "ASK_AVAILABILITY", "Bien. ¿Tienes disponibilidad para viajar o realizar rutas foráneas?"

    if stage == "ASK_AVAILABILITY":
        return "PROFILE_READY", "Gracias. Con esto ya tengo tu información base; voy a dejar tu perfil listo para revisión de RH."

    if stage == "PROFILE_READY":
        return "PROFILE_READY", ""

    if stage == "CLARIFY_AMBIGUOUS_SLANG":
        return "ASK_CITY", "Gracias por aclararlo. Para continuar, ¿en qué ciudad te encuentras actualmente?"

    if stage == "HUMAN_REVIEW_REQUIRED":
        return "HUMAN_REVIEW_REQUIRED", "Tu caso está canalizado con RH para revisión."

    return "ASK_CITY", "Para continuar, ¿en qué ciudad te encuentras actualmente?"


def answer_with_rag(
    conversation_key: str,
    user_message: str,
    history: str,
    top_k: int | None = 3,
) -> dict[str, Any]:
    ctx = retrieve_context_for_guardrail(user_message, top_k=top_k)
    valid_ctx = [item for item in ctx if (item["score"] or 0) >= 0.30]

    if valid_ctx:
        context_text = "\n\n---\n\n".join(item["text"] for item in valid_ctx)
    else:
        context_text = "No se encontro informacion en los manuales para esta pregunta."

    prompt = f"""
{SYSTEM_PROMPT}

=== HISTORIAL RECIENTE ===
{history}

=== CONTEXTO RECUPERADO DE MANUALES RH ===
{context_text}

=== PREGUNTA DEL CANDIDATO ===
{user_message}

INSTRUCCIONES:
1. Responde solo con base en el contexto recuperado.
2. Si no hay informacion suficiente, dilo con claridad y no inventes.
3. No prometas sueldo, contratacion, beneficios ni condiciones no confirmadas.
4. Responde breve, natural y en español.
5. No hagas preguntas de seguimiento. Solo responde la duda documental.
6. No termines con frases como "¿Quieres que te aclare algo más?" o "¿Tienes otra duda?".

RESPUESTA:
"""

    answer = _strip_followup_questions(call_llm(prompt).strip())

    sources = [
        {"source": item["source"], "score": round(item["score"], 4)}
        for item in valid_ctx
    ]

    save_rag_audit(
        conversation_key=conversation_key,
        user_message=user_message,
        answer=answer,
        sources=sources,
        top_k=top_k,
        min_score=0.30,
    )

    return {
        "answer": answer,
        "sources": sources,
    }


def _clarification_reply_for_ambiguous_slang() -> str:
    return (
        "Para no malinterpretarte, ¿te refieres a hacer paradas en cachimbas "
        "para comer o descansar durante ruta?"
    )


def _safe_handoff_reply() -> str:
    return (
        "Por seguridad y cumplimiento, ese punto debe revisarlo directamente "
        "el equipo de RH. Voy a canalizar tu caso para que puedan orientarte correctamente."
    )


def _followup_time_reply() -> str:
    return (
        "Entiendo que te urge. Tu perfil ya quedó registrado para revisión de Capital Humano. "
        "El equipo atiende principalmente de 7:30 a.m. a 5:30 p.m.; si escribes fuera de ese horario, "
        "normalmente revisan el seguimiento en el siguiente horario hábil.\n\n"
        "Para no frenar tu proceso, asegúrate de tener lista tu documentación. "
        "Si ya la compartiste completa, tu proceso queda en una etapa avanzada de revisión, "
        "aunque la confirmación final la debe dar Capital Humano."
    )


def _documents_complete_reply() -> str:
    return (
        "Perfecto. Si ya compartiste tu documentación completa, tu proceso queda en una etapa avanzada de revisión. "
        "Capital Humano valida documentos, disponibilidad y vacante antes de confirmar el siguiente paso.\n\n"
        "Tu información ya queda registrada en seguimiento; evita reenviar documentos repetidos salvo que RH te lo solicite."
    )


def _foraneo_travel_reply() -> str:
    return (
        "Si eres foráneo y tu perfil avanza, Capital Humano puede validar apoyo de boleto de autobús a Torreón, "
        "siempre que aplique según la base, ubicación autorizada y etapa del proceso.\n\n"
        "Ese apoyo no se confirma automáticamente por este medio; debe validarlo directamente RH. "
        "Compárteme tu ciudad o base de origen para dejarlo registrado."
    )


def _is_safe_clarification_response(message: str) -> bool:
    m = _norm(message)

    safe_patterns = [
        "comer",
        "comida",
        "cenar",
        "desayunar",
        "descansar",
        "descanso",
        "banar",
        "bañar",
        "bañarme",
        "dormir",
        "esperar",
        "esperar turno",
        "cargar combustible",
        "echar diesel",
        "echar diésel",
        "solo paradas",
        "paradas",
        "ruta",
        "cachimba para comer",
    ]

    high_risk_patterns = [
        "tomar",
        "alcohol",
        "cerveza",
        "cheve",
        "droga",
        "drogas",
        "mota",
        "perico",
        "cristal",
        "pelea",
        "pelear",
        "golpear",
        "violencia",
        "desmadre",
        "mujeres",
        "pleito",
    ]

    if any(p in m for p in high_risk_patterns):
        return False

    return any(p in m for p in safe_patterns)


def orchestrate_message(
    channel: str,
    channel_user_id: str,
    message: str,
    username: str | None = None,
    phone: str | None = None,
    external_message_id: str | None = None,
) -> dict[str, Any]:
    setup = upsert_conversation(
        channel=channel,
        channel_user_id=channel_user_id,
        username=username,
        phone=phone,
    )

    conversation_key = setup["conversation_key"]
    state = get_conversation_state(conversation_key)
    conversation = state["conversation"] or {}
    current_stage = conversation.get("current_stage") or "START"

    save_message(conversation_key, "user", message)

    detection = detect_intent_and_risk(message)

    if current_stage == "CLARIFY_AMBIGUOUS_SLANG":
        if _is_safe_clarification_response(message):
            detection = {
                "intent": "slang_clarified_safe",
                "risk_level": "low",
                "requires_human": False,
                "requires_rag": False,
                "requires_clarification": False,
                "reason": "jerga_aclarada_segura",
            }
        else:
            detection = {
                "intent": "slang_clarification_risky",
                "risk_level": "high",
                "requires_human": True,
                "requires_rag": False,
                "requires_clarification": False,
                "reason": "jerga_aclarada_con_riesgo",
            }

    profile_stages = {
        "ASK_CITY",
        "ASK_LICENSE",
        "ASK_EXPERIENCE",
        "ASK_APTO",
        "ASK_AVAILABILITY",
    }

    if (
        current_stage in profile_stages
        and "?" not in message
        and detection.get("intent") == "document_question"
    ):
        detection = {
            "intent": "candidate_answer",
            "risk_level": "low",
            "requires_human": False,
            "requires_rag": False,
            "requires_clarification": False,
            "reason": None,
        }

    intent = detection["intent"]
    risk_level = detection["risk_level"]
    requires_human = bool(detection["requires_human"])
    requires_clarification = bool(detection.get("requires_clarification", False))

    fields = extract_profile_fields(message, current_stage)

    city_catalog = fields.pop("_city_catalog", None) if fields else None
    city_requires_ch_validation = (
        bool(fields.pop("_city_requires_ch_validation", False)) if fields else False
    )

    if city_requires_ch_validation and risk_level != "high":
        intent = "foreign_location_validation"
        risk_level = "medium"
        requires_human = True

    if fields:
        fields["last_detected_intent"] = intent
        fields["risk_level"] = risk_level
        fields["requires_human"] = requires_human
        update_candidate_profile(conversation_key, fields)

    log_event(
        conversation_key=conversation_key,
        event_type="message_received",
        stage_from=current_stage,
        intent=intent,
        risk_level=risk_level,
        requires_human=requires_human,
        metadata={
            "external_message_id": external_message_id,
            "fields": fields,
            "channel": channel,
            "requires_clarification": requires_clarification,
            "reason": detection.get("reason"),
            "city_catalog": city_catalog,
            "city_requires_ch_validation": city_requires_ch_validation,
        },
    )

    history = _history_text(state["messages"])

    if intent in {
        "followup_time_question",
        "documents_complete_followup",
        "foraneo_travel_question",
    }:
        next_stage = current_stage or "PROFILE_READY"

        if intent == "followup_time_question":
            reply = _followup_time_reply()
            event_type = "followup_time_answered"
        elif intent == "documents_complete_followup":
            reply = _documents_complete_reply()
            event_type = "documents_complete_answered"
        else:
            reply = _foraneo_travel_reply()
            event_type = "foraneo_travel_answered"

        update_stage(
            conversation_key=conversation_key,
            stage_to=next_stage,
            intent=intent,
            risk_level=risk_level,
            requires_human=False,
        )

        save_message(conversation_key, "assistant", reply)

        log_event(
            conversation_key=conversation_key,
            event_type=event_type,
            stage_from=current_stage,
            stage_to=next_stage,
            intent=intent,
            risk_level=risk_level,
            requires_human=False,
            metadata={"reason": detection.get("reason")},
        )

        return {
            "status": "ok",
            "conversation_key": conversation_key,
            "reply": reply,
            "current_stage": next_stage,
            "requires_human": False,
            "risk_level": risk_level,
            "intent": intent,
            "sources": [],
        }

    if requires_clarification:
        next_stage = "CLARIFY_AMBIGUOUS_SLANG"
        reply = _clarification_reply_for_ambiguous_slang()

        update_stage(
            conversation_key=conversation_key,
            stage_to=next_stage,
            intent=intent,
            risk_level=risk_level,
            requires_human=False,
        )

        save_message(conversation_key, "assistant", reply)

        log_event(
            conversation_key=conversation_key,
            event_type="clarification_requested",
            stage_from=current_stage,
            stage_to=next_stage,
            intent=intent,
            risk_level=risk_level,
            requires_human=False,
            metadata={"reason": detection.get("reason")},
        )

        return {
            "status": "ok",
            "conversation_key": conversation_key,
            "reply": reply,
            "current_stage": next_stage,
            "requires_human": False,
            "risk_level": risk_level,
            "intent": intent,
            "sources": [],
        }

    if requires_human and risk_level == "high":
        next_stage = "HUMAN_REVIEW_REQUIRED"
        reply = _safe_handoff_reply()

        create_handoff(
            conversation_key=conversation_key,
            reason=detection.get("reason") or "tema_sensible",
            risk_level=risk_level,
            summary=message,
        )

        update_stage(
            conversation_key=conversation_key,
            stage_to=next_stage,
            intent=intent,
            risk_level=risk_level,
            requires_human=True,
        )

        save_message(conversation_key, "assistant", reply)

        log_event(
            conversation_key=conversation_key,
            event_type="human_handoff_created",
            stage_from=current_stage,
            stage_to=next_stage,
            intent=intent,
            risk_level=risk_level,
            requires_human=True,
            metadata={"reason": detection.get("reason")},
        )

        return {
            "status": "ok",
            "conversation_key": conversation_key,
            "reply": reply,
            "current_stage": next_stage,
            "requires_human": True,
            "risk_level": risk_level,
            "intent": intent,
            "sources": [],
        }

    if detection["requires_rag"]:
        rag_result = answer_with_rag(
            conversation_key=conversation_key,
            user_message=message,
            history=history,
            top_k=3,
        )

        next_stage, next_question = decide_next_stage(current_stage, fields)

        if requires_human:
            create_handoff(
                conversation_key=conversation_key,
                reason=detection.get("reason") or "requiere_validacion_rh",
                risk_level=risk_level,
                summary=message,
            )
            next_stage = "HUMAN_REVIEW_REQUIRED"
            if rag_result["answer"]:
                reply = f"{rag_result['answer']}\n\nPara confirmar ese punto con precisión, voy a canalizar tu caso con RH."
            else:
                reply = "Para confirmar ese punto con precisión, voy a canalizar tu caso con RH."
        else:
            if next_question:
                reply = f"{rag_result['answer']}\n\n{next_question}"
            else:
                reply = rag_result["answer"]

        update_stage(
            conversation_key=conversation_key,
            stage_to=next_stage,
            intent=intent,
            risk_level=risk_level,
            requires_human=requires_human,
        )

        save_message(conversation_key, "assistant", reply)

        log_event(
            conversation_key=conversation_key,
            event_type="rag_answered",
            stage_from=current_stage,
            stage_to=next_stage,
            intent=intent,
            risk_level=risk_level,
            requires_human=requires_human,
            metadata={"sources": rag_result["sources"]},
        )

        return {
            "status": "ok",
            "conversation_key": conversation_key,
            "reply": reply,
            "current_stage": next_stage,
            "requires_human": requires_human,
            "risk_level": risk_level,
            "intent": intent,
            "sources": rag_result["sources"],
        }

    next_stage, reply = decide_next_stage(current_stage, fields)

    if not reply:
        reply = (
            "Tu perfil ya quedó registrado. "
            "Si tienes una duda específica sobre la vacante, documentos, prestaciones o seguimiento, puedes escribírmela por aquí."
        )

    update_stage(
        conversation_key=conversation_key,
        stage_to=next_stage,
        intent=intent,
        risk_level=risk_level,
        requires_human=requires_human,
    )

    save_message(conversation_key, "assistant", reply)

    log_event(
        conversation_key=conversation_key,
        event_type="stage_changed",
        stage_from=current_stage,
        stage_to=next_stage,
        intent=intent,
        risk_level=risk_level,
        requires_human=requires_human,
        metadata={
            "fields": fields,
            "city_catalog": city_catalog,
            "city_requires_ch_validation": city_requires_ch_validation,
        },
    )

    return {
        "status": "ok",
        "conversation_key": conversation_key,
        "reply": reply,
        "current_stage": next_stage,
        "requires_human": requires_human,
        "risk_level": risk_level,
        "intent": intent,
        "sources": [],
    }