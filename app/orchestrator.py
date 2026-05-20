import re
from enum import Enum
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


# ==========================================
# 1. ENUMS PARA CONTROL DE ESTADOS E INTENCIONES
# ==========================================

class Stage(str, Enum):
    START = "START"
    NEW_LEAD = "NEW_LEAD"
    ASK_CITY = "ASK_CITY"
    ASK_LICENSE = "ASK_LICENSE"
    ASK_EXPERIENCE = "ASK_EXPERIENCE"
    ASK_APTO = "ASK_APTO"
    ASK_AVAILABILITY = "ASK_AVAILABILITY"
    PROFILE_READY = "PROFILE_READY"
    CLARIFY_AMBIGUOUS_SLANG = "CLARIFY_AMBIGUOUS_SLANG"
    HUMAN_REVIEW_REQUIRED = "HUMAN_REVIEW_REQUIRED"


class Intent(str, Enum):
    SENSITIVE_HANDOFF = "sensitive_handoff"
    RCONTROL_HANDOFF = "rcontrol_or_incident_handoff"
    FOLLOWUP_TIME = "followup_time_question"
    DOCUMENTS_COMPLETE = "documents_complete_followup"
    FORANEO_TRAVEL = "foraneo_travel_question"
    SALARY_SENSITIVE = "salary_sensitive"
    AMBIGUOUS_SLANG = "ambiguous_slang_clarification"
    DOCUMENT_QUESTION = "document_question"
    CANDIDATE_ANSWER = "candidate_answer"
    FOREIGN_VALIDATION = "foreign_location_validation"
    SLANG_SAFE = "slang_clarified_safe"
    SLANG_RISKY = "slang_clarification_risky"
    CONDITIONAL_AVAILABILITY = "conditional_availability"


PROFILE_STAGES = {
    Stage.ASK_CITY.value,
    Stage.ASK_LICENSE.value,
    Stage.ASK_EXPERIENCE.value,
    Stage.ASK_APTO.value,
    Stage.ASK_AVAILABILITY.value,
}


# ==========================================
# 2. RESPUESTAS ESTÁTICAS CONTROLADAS
# ==========================================

STATIC_REPLIES = {
    Intent.AMBIGUOUS_SLANG.value: (
        "Para no malinterpretarte, ¿te refieres a hacer paradas en cachimbas "
        "para comer o descansar durante ruta?"
    ),

    Intent.SENSITIVE_HANDOFF.value: (
        "Te entiendo. Sabemos que este rubro puede ser muy exigente por las cargas de trabajo y el tiempo en carretera. "
        "Por eso aquí cuidamos mucho la seguridad del operador y manejamos política de cero tolerancia en temas de sustancias "
        "o alcohol relacionados con operación.\n\n"
        "La intención no es juzgarte, sino cuidar tu seguridad, tu estabilidad laboral, familiar y personal. "
        "Este punto debe revisarlo Capital Humano antes de continuar con cualquier avance del proceso."
    ),

    Intent.FOLLOWUP_TIME.value: (
        "Me da gusto que te interese avanzar en tu proceso. "
        "¿A qué hora te gustaría que podamos llamarte? "
        "Así dejo registrado el horario para que un agente de reclutamiento le dé seguimiento.\n\n"
        "Si tu documentación ya está completa y legible, eso ayuda a que tu proceso avance más rápido; "
        "la confirmación final la realiza Capital Humano."
    ),

    Intent.DOCUMENTS_COMPLETE.value: (
        "Perfecto. Si ya compartiste tu documentación completa, tu proceso queda en una etapa avanzada de revisión. "
        "Capital Humano valida documentos, disponibilidad y vacante antes de confirmar el siguiente paso.\n\n"
        "Tu información ya queda registrada en seguimiento; evita reenviar documentos repetidos salvo que RH te lo solicite."
    ),

    Intent.FORANEO_TRAVEL.value: (
        "Si eres foráneo y tu perfil avanza, Capital Humano puede validar apoyo de boleto de autobús, "
        "siempre que aplique según la base, ubicación autorizada y etapa del proceso.\n\n"
        "Ese apoyo no se confirma automáticamente por este medio; debe validarlo directamente Capital Humano. "
        "Compárteme tu ciudad o base de origen para dejarlo registrado."
    ),

    Intent.CONDITIONAL_AVAILABILITY.value: (
        "Tiene sentido. Entonces no lo tomo como disponibilidad confirmada todavía. "
        "Lo voy a dejar marcado como disponibilidad condicionada a ruta, pago o condiciones para que Capital Humano lo valide contigo."
    ),

    "RESTRICTIVE_LOCKED": (
        "Te entiendo. Aun así, por seguridad mantenemos la política de cero tolerancia en temas de sustancias "
        "o alcohol relacionados con operación.\n\n"
        "La intención no es juzgarte, sino cuidar tu seguridad, tu estabilidad laboral, familiar y personal. "
        "Como empresa también invertimos tiempo, seguimiento y apoyo en cada proceso, por eso es importante avanzar "
        "con información clara desde el inicio.\n\n"
        "Si hay algo que pueda afectar los filtros de seguridad o la validación de Capital Humano, es mejor comentarlo con honestidad."
    ),

    "DEFAULT_PROFILE_END": (
        "Tu perfil ya quedó registrado. Si tienes una duda específica sobre la vacante, "
        "documentos, prestaciones o seguimiento, puedes escribírmela por aquí."
    ),
}


# ==========================================
# 3. UTILIDADES DE TEXTO
# ==========================================

def _stage_value(value: str | Stage | None) -> str:
    if isinstance(value, Stage):
        return value.value
    return value or Stage.START.value


def _intent_value(value: str | Intent | None) -> str:
    if isinstance(value, Intent):
        return value.value
    return value or Intent.CANDIDATE_ANSWER.value


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
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _history_text(messages: list[dict[str, Any]]) -> str:
    if not messages:
        return "No hay historial previo."

    lines = []
    for item in messages[-8:]:
        role = item.get("role", "user")
        msg = item.get("message", "")
        lines.append(f"{role}: {msg}")
    return "\n".join(lines)


def _source_payload(item: dict[str, Any]) -> dict[str, Any]:
    """
    Normaliza fuentes para auditoría y respuesta.

    Con Rerank activo, indexer.py puede devolver:
    - score: score final usado por filtros
    - rerank_score: score de Cohere Rerank
    - chroma_score: score original de Chroma
    """
    payload: dict[str, Any] = {
        "source": item.get("source"),
        "score": round(item.get("score") or 0, 4),
    }

    if item.get("rerank_score") is not None:
        payload["rerank_score"] = round(item.get("rerank_score") or 0, 4)

    if item.get("chroma_score") is not None:
        payload["chroma_score"] = round(item.get("chroma_score") or 0, 4)

    if item.get("id"):
        payload["id"] = item.get("id")

    return payload


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
        r"\n*Si tienes más dudas sobre .*?, puedo ayudarte a resolverlas\.?\s*$",
        r"\n*Si tienes más dudas.*, puedo ayudarte.*$",
        r"\n*Si hay algo más que quieras saber.*, puedo buscar.*$",
        r"\n*No olvides que Capital Humano puede validar cualquier duda.*$",
        r"\n*Capital Humano puede confirmar los detalles exactos.*$",
        r"\n*Estoy aquí para ayudarte.*$",
        r"\n*Puedo ayudarte a resolver.*$",
    ]

    cleaned = text.strip()
    for pattern in banned_patterns:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE | re.DOTALL).strip()

    return cleaned


def _is_neutral_greeting(message: str) -> bool:
    m = _norm(message)

    greetings = {
        "hola",
        "hola buenas noches",
        "hola buenas tardes",
        "hola buenos dias",
        "hola buenos días",
        "buenas noches",
        "buenas tardes",
        "buenos dias",
        "buenos días",
        "buen dia",
        "buen día",
        "buenas",
        "que tal",
        "qué tal",
        "q tal",
        "hola que tal",
        "hola qué tal",
    }

    if m in greetings:
        return True

    greeting_starts = [
        "hola buenas",
        "buenas",
        "buen dia",
        "buen día",
        "buenas tardes",
        "buenas noches",
    ]

    return any(m.startswith(g) for g in greeting_starts) and len(m) <= 60


def _is_question(message: str) -> bool:
    raw = message or ""
    m = _norm(raw)

    if not m:
        return False

    # Saludos comunes que empiezan con "qué/que" pero no son pregunta documental.
    greeting_starts = [
        "que tal",
        "qué tal",
        "q tal",
        "que onda",
        "qué onda",
        "hola",
        "buen dia",
        "buen día",
        "buenas",
    ]

    if any(m.startswith(g) for g in greeting_starts) and "?" not in raw and "¿" not in raw:
        return False

    if "?" in raw or "¿" in raw:
        return True

    question_starts = [
        "cuanto",
        "cuanta",
        "cuantas",
        "cuantos",
        "cuando",
        "kuando",
        "donde",
        "adonde",
        "a donde",
        "que ",
        "ke ",
        "qué ",
        "cual",
        "cuál",
        "como",
        "cómo",
        "pagan",
        "dan",
        "tienen",
        "hacen",
        "asen",
        "acen",
        "aceptan",
        "manejan",
        "ai ",
        "hay ",
        "sabe",
        "saben",
    ]

    return any(m.startswith(q) for q in question_starts)


def _contains_any(text: str, patterns: list[str]) -> bool:
    return any(pattern in text for pattern in patterns)


def _is_meta_complaint_or_confusion(message: str) -> bool:
    m = _norm(message)

    patterns = [
        "no me respondio",
        "no me respondio lo que le pregunte",
        "no respondio",
        "no me contesto",
        "eso no fue lo que pregunte",
        "eso no fue lo que le pregunte",
        "eso no fue lo que pregunte",
        "no me esta respondiendo",
        "no me estas respondiendo",
        "de que habla",
        "no entiendo",
        "no le entiendo",
        "no entendi",
        "que quiere decir",
        "a que se refiere",
        "como?",
        "mande",
    ]

    return any(p in m for p in patterns)


def _yes_no_value(message: str) -> str | None:
    m = _norm(message)
    m = re.sub(r"^[,.;:¡!¿?\s]+|[,.;:¡!¿?\s]+$", "", m)

    if not m:
        return None

    negative_exact = {"no", "n", "nel", "nop", "negativo"}
    negative_starts = [
        "no ",
        "nel ",
        "nop ",
        "no tengo",
        "no cuento",
        "no la tengo",
        "no lo tengo",
        "no manejo",
        "no puedo",
        "no estoy",
        "vencida",
        "vencido",
        "se me vencio",
        "se me venció",
        "en tramite",
        "en trámite",
    ]

    if m in negative_exact or any(m.startswith(p) for p in negative_starts):
        return "NO"

    positive_exact = {
        "si",
        "sí",
        "s",
        "simon",
        "simón",
        "claro",
        "correcto",
        "afirmativo",
    }

    positive_starts = [
        "si ",
        "sí ",
        "si,",
        "sí,",
        "simon",
        "simón",
        "claro",
        "correcto",
        "afirmativo",
        "tengo",
        "cuento",
        "si tengo",
        "sí tengo",
        "si cuento",
        "sí cuento",
    ]

    positive_contains = [
        "si tengo",
        "sí tengo",
        "si cuento",
        "sí cuento",
        "tengo licencia",
        "cuento con licencia",
        "licencia vigente",
    ]

    if (
        m in positive_exact
        or any(m.startswith(p) for p in positive_starts)
        or any(p in m for p in positive_contains)
    ):
        return "SI"

    return None


def _is_conditional_availability(message: str) -> bool:
    m = _norm(message)

    patterns = [
        "depende",
        "si conviene",
        "si me conviene",
        "segun",
        "según",
        "segun ruta",
        "según ruta",
        "depende la ruta",
        "depende del pago",
        "depende cuanto paguen",
        "depende cuánto paguen",
        "depende hasta donde",
        "depende hasta dónde",
        "depende el viaje",
        "si pagan bien",
        "si esta bueno el pago",
        "si está bueno el pago",
        "si me sale",
        "si me queda",
    ]

    return any(p in m for p in patterns)


# ==========================================
# 4. SUSTANCIAS / RIESGO CON NEGACIONES
# ==========================================

def _is_substance_question(message: str) -> bool:
    m = _norm(message)

    patterns = [
        "hacen antidoping",
        "hacen anti doping",
        "hacen antidopaje",
        "asen antidoping",
        "asen antidopin",
        "acen antidoping",
        "acen antidopin",
        "hay antidoping",
        "hay antidopin",
        "ai antidoping",
        "ai antidopin",
        "piden antidoping",
        "piden antidopin",
        "prueba antidoping",
        "prueba antidopin",
        "prueba toxicológica",
        "prueba toxicologica",
        "prueba de drogas",
        "examen toxicológico",
        "examen toxicologico",
        "que pasa si salgo positivo",
        "qué pasa si salgo positivo",
        "ke pasa si salgo positivo",
        "salen positivos",
        "como manejan el tema de uso de drogas",
        "cómo manejan el tema de uso de drogas",
        "como manejan uso de drogas",
        "uso de drogas",
        "tema de drogas",
        "medicamento controlado",
        "medicamento recetado",
        "aceptan medicamento",
        "uso medicamento",
    ]

    return _is_question(message) and any(p in m for p in patterns)


def _is_substance_negation(message: str) -> bool:
    m = _norm(message)

    patterns = [
        "no me drogo",
        "yo no me drogo",
        "no consumo drogas",
        "no uso drogas",
        "no uso sustancias",
        "no consumo sustancias",
        "no me gusta la droga",
        "no me gusta para nada",
        "no uso mota",
        "no fumo mota",
        "no tomo en ruta",
        "no manejo tomado",
        "no manejo borracho",
        "no uso nada",
        "nunca me drogo",
        "nunca he usado drogas",
        "nunca consumo drogas",
    ]

    return any(p in m for p in patterns)


def _is_substance_admission(message: str) -> bool:
    m = _norm(message)

    if _is_substance_question(message):
        return False

    if _is_substance_negation(message):
        return False

    admission_patterns = [
        "me drogo",
        "me drgo",
        "si me drogo",
        "sí me drogo",
        "me encanta la droga",
        "me encanta la dr0ga",
        "me gusta la droga",
        "uso drogas",
        "uso sustancias",
        "consumo drogas",
        "consumo sustancias",
        "fumo mota",
        "uso mota",
        "marihuana",
        "cristal",
        "perico",
        "cocaina",
        "cocaína",
        "foco",
        "piedra",
        "sustancias para aguantar",
        "alcohol en ruta",
        "tomo en ruta",
        "manejo tomado",
        "manejo borracho",
    ]

    return any(p in m for p in admission_patterns)


def _is_fatigue_or_stimulant_risk(message: str) -> bool:
    m = _norm(message)

    risky_patterns = [
        "ritalin",
        "ritalín",
        "metilfenidato",
        "aderall",
        "adderall",
        "anfetamina",
        "anfetaminas",
        "metanfetamina",
        "metanfetaminas",
        "pastillas para aguantar",
        "pastilla para aguantar",
        "algo para aguantar",
        "algo pa aguantar",
        "para aguantar el viaje",
        "para aguantar la ruta",
        "para no dormir",
        "para no quedarme dormido",
        "para no quedarse dormido",
        "me ayuda a aguantar",
        "me ayuda para aguantar",
        "me meto algo para aguantar",
        "ocupo algo para aguantar",
        "necesito algo para aguantar",
        "uso algo para aguantar",
        "suelo usarlo",
        "suelo usarlo para aguantar",
        "echarse un ritalin",
        "echarme un ritalin",
        "me echo un ritalin",
        "me tomo un ritalin",
        "cuando esta duro el jale",
        "cuando está duro el jale",
    ]

    if "lavar vidrios" in m and any(x in m for x in ["ritalin", "ritalín", "usar", "usarlo", "aguantar"]):
        return True

    return any(p in m for p in risky_patterns)


# ==========================================
# 5. DETECCIÓN DE INTENCIÓN Y RIESGO
# ==========================================

def detect_intent_and_risk(message: str) -> dict[str, Any]:
    m = _norm(message)

    if _is_neutral_greeting(message):
        return {
            "intent": Intent.CANDIDATE_ANSWER.value,
            "risk_level": "low",
            "requires_human": False,
            "requires_rag": False,
            "requires_clarification": False,
            "reason": "saludo_neutral",
        }

    if _is_meta_complaint_or_confusion(message):
        return {
            "intent": Intent.CANDIDATE_ANSWER.value,
            "risk_level": "low",
            "requires_human": False,
            "requires_rag": False,
            "requires_clarification": False,
            "reason": "queja_o_confusion_sin_dato_de_perfil",
        }

    # Sustancias: separar pregunta, negación y admisión.
    if _is_substance_question(message):
        return {
            "intent": Intent.DOCUMENT_QUESTION.value,
            "risk_level": "low",
            "requires_human": False,
            "requires_rag": True,
            "requires_clarification": False,
            "reason": "pregunta_sustancias_antidoping",
        }

    if _is_substance_admission(message):
        return {
            "intent": Intent.SENSITIVE_HANDOFF.value,
            "risk_level": "high",
            "requires_human": True,
            "requires_rag": False,
            "requires_clarification": False,
            "reason": "comentario_sobre_sustancias_o_alcohol_validar_ch",
        }

    if _is_fatigue_or_stimulant_risk(message):
        return {
            "intent": Intent.SENSITIVE_HANDOFF.value,
            "risk_level": "high",
            "requires_human": True,
            "requires_rag": False,
            "requires_clarification": False,
            "reason": "comentario_sobre_estimulantes_fatiga_o_seguridad_operativa",
        }

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
        "sali mal",
        "salí mal",
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
        "cuando me hablan",
        "cuándo me hablan",
        "cuando me ablan",
        "cuando me llaman",
        "cuándo me llaman",
        "cuando me yaman",
        "me urge",
        "urge",
        "tengo prisa",
        "ocupo respuesta",
        "me interesa mucho",
        "ando buscando trabajo ya",
        "me pueden contestar",
        "me pueden responder",
        "me pueden llamar",
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

    salary_sensitive_patterns = [
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
        "kilometro",
        "kilómetro",
        "km",
        "ruta",
        "rutas",
        "destinos",
        "descanso",
        "descansos",
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
        "antidoping",
        "anti doping",
        "antidopin",
        "antidopaje",
        "doping",
        "drogas",
        "sustancias",
        "ritalin",
        "ritalín",
        "rabon",
        "rabón",
        "torton",
        "quinta rueda",
        "full",
    ]

    if any(p in m for p in high_risk_patterns):
        return {
            "intent": Intent.SENSITIVE_HANDOFF.value,
            "risk_level": "high",
            "requires_human": True,
            "requires_rag": False,
            "requires_clarification": False,
            "reason": "tema_sensible",
        }

    if any(p in m for p in boletin_patterns):
        return {
            "intent": Intent.RCONTROL_HANDOFF.value,
            "risk_level": "high",
            "requires_human": True,
            "requires_rag": False,
            "requires_clarification": False,
            "reason": "boletin_o_incidencia",
        }

    if any(p in m for p in followup_time_patterns):
        return {
            "intent": Intent.FOLLOWUP_TIME.value,
            "risk_level": "low",
            "requires_human": True,
            "requires_rag": False,
            "requires_clarification": False,
            "reason": "seguimiento_o_solicitud_de_llamada",
        }

    if any(p in m for p in documents_complete_patterns):
        return {
            "intent": Intent.DOCUMENTS_COMPLETE.value,
            "risk_level": "low",
            "requires_human": False,
            "requires_rag": False,
            "requires_clarification": False,
            "reason": "documentacion_o_siguiente_paso",
        }

    if any(p in m for p in foraneo_travel_patterns):
        return {
            "intent": Intent.FORANEO_TRAVEL.value,
            "risk_level": "low",
            "requires_human": False,
            "requires_rag": False,
            "requires_clarification": False,
            "reason": "foraneo_o_boleto",
        }

    if any(p in m for p in salary_sensitive_patterns):
        return {
            "intent": Intent.SALARY_SENSITIVE.value,
            "risk_level": "medium",
            "requires_human": True,
            "requires_rag": True,
            "requires_clarification": False,
            "reason": "sueldo_o_compromiso_economico",
        }

    if any(p in m for p in ambiguous_slang_patterns):
        return {
            "intent": Intent.AMBIGUOUS_SLANG.value,
            "risk_level": "medium",
            "requires_human": False,
            "requires_rag": False,
            "requires_clarification": True,
            "reason": "jerga_ambigua",
        }

    if _is_conditional_availability(message):
        return {
            "intent": Intent.CONDITIONAL_AVAILABILITY.value,
            "risk_level": "medium",
            "requires_human": True,
            "requires_rag": False,
            "requires_clarification": False,
            "reason": "disponibilidad_condicionada",
        }

    if "?" in message or "¿" in message or any(p in m for p in rag_patterns):
        return {
            "intent": Intent.DOCUMENT_QUESTION.value,
            "risk_level": "low",
            "requires_human": False,
            "requires_rag": True,
            "requires_clarification": False,
            "reason": None,
        }

    return {
        "intent": Intent.CANDIDATE_ANSWER.value,
        "risk_level": "low",
        "requires_human": False,
        "requires_rag": False,
        "requires_clarification": False,
        "reason": None,
    }


# ==========================================
# 6. EXTRACCIÓN DE CAMPOS
# ==========================================

def _clean_city_text(message: str) -> str:
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


def _looks_like_city_answer(message: str) -> bool:
    m = _norm(message)

    if _is_question(message) or _is_meta_complaint_or_confusion(message):
        return False

    bad_patterns = [
        "no me respondio",
        "pregunte",
        "no entiendo",
        "eso no",
        "licencia",
        "pago",
        "sueldo",
        "kilometro",
        "kilómetro",
        "ruta",
        "bases",
        "drogas",
        "droga",
        "ritalin",
        "ritalín",
        "cachimba",
        "cachimbear",
        "documentos",
        "prestaciones",
        "antidoping",
        "doping",
    ]

    if any(p in m for p in bad_patterns):
        return False

    location_cues = [
        "soy de ",
        "soi de ",
        "vivo en ",
        "vivo por ",
        "estoy en ",
        "ando en ",
        "radico en ",
        "resido en ",
        "me ubico en ",
        "me encuentro en ",
        "de ",
        "en ",
    ]

    if any(m.startswith(cue) for cue in location_cues):
        return True

    words = m.split()
    return 1 <= len(words) <= 3 and len(m) <= 40


def _city_fields_from_catalog(message: str, current_stage: str | None) -> dict[str, Any]:
    stage = _stage_value(current_stage)

    if stage not in {Stage.START.value, Stage.NEW_LEAD.value, Stage.ASK_CITY.value}:
        return {}

    if not message or len(message.strip()) > 120:
        return {}

    if _is_question(message) or _is_meta_complaint_or_confusion(message):
        return {}

    cleaned_city = _clean_city_text(message)
    match = find_city_catalog_match(cleaned_city) or find_city_catalog_match(message)

    if not match:
        if (
            stage == Stage.ASK_CITY.value
            and len(cleaned_city.strip()) <= 60
            and _looks_like_city_answer(message)
        ):
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
    stage = _stage_value(current_stage)
    m = _norm(message)
    fields: dict[str, Any] = {}

    is_question = _is_question(message)

    age_match = re.search(r"\b(\d{2})\s*(anos|años)?\b", m)
    if age_match:
        age = int(age_match.group(1))
        if 18 <= age <= 75:
            fields["edad"] = age

    city_fields = _city_fields_from_catalog(message, stage)
    if city_fields:
        fields.update(city_fields)

    if ("federal" in m or "licencia" in m or stage == Stage.ASK_LICENSE.value) and not is_question:
        yes_no = _yes_no_value(message)
        if yes_no:
            fields["licencia_federal"] = yes_no

        type_match = re.search(r"\b(tipo\s*)?([abe])\b", m)
        if type_match:
            fields["tipo_licencia"] = type_match.group(2).upper()

    if not is_question and ("apto" in m or "medico" in m or "médico" in m):
        yes_no = _yes_no_value(message)
        if yes_no:
            fields["apto_medico"] = yes_no

    if not is_question and (
        "viajar" in m
        or "disponibilidad" in m
        or "foraneo" in m
        or "foráneo" in m
        or "foraneas" in m
        or stage == Stage.ASK_AVAILABILITY.value
    ):
        if _is_conditional_availability(message):
            fields["disponibilidad_viajar"] = "CONDICIONADA"
            fields["observaciones"] = (
                "Disponibilidad condicionada a ruta, pago o condiciones; requiere validación de Capital Humano."
            )
        else:
            yes_no = _yes_no_value(message)
            if yes_no:
                fields["disponibilidad_viajar"] = yes_no

    exp_match = re.search(r"\b(\d{1,2})\s*(anos|años|año)\b", m)
    if exp_match and any(x in m for x in ["experiencia", "manejando", "quinta", "rueda", "tracto"]):
        fields["experiencia_quinta_rueda"] = f"{exp_match.group(1)} años"

    if stage == Stage.ASK_EXPERIENCE.value and not fields.get("experiencia_quinta_rueda") and not is_question:
        exp_stage_match = re.search(r"\b(\d{1,2})\s*(anos|años|año)\b", m)
        if exp_stage_match:
            fields["experiencia_quinta_rueda"] = f"{exp_stage_match.group(1)} años"
        elif len(message.strip()) <= 80 and not _is_meta_complaint_or_confusion(message):
            fields["experiencia_quinta_rueda"] = message.strip()

    elif stage == Stage.ASK_APTO.value and not fields.get("apto_medico") and not is_question:
        yes_no = _yes_no_value(message)
        if yes_no:
            fields["apto_medico"] = yes_no

    elif stage == Stage.ASK_AVAILABILITY.value and not fields.get("disponibilidad_viajar") and not is_question:
        if _is_conditional_availability(message):
            fields["disponibilidad_viajar"] = "CONDICIONADA"
            fields["observaciones"] = (
                "Disponibilidad condicionada a ruta, pago o condiciones; requiere validación de Capital Humano."
            )
        else:
            yes_no = _yes_no_value(message)
            if yes_no:
                fields["disponibilidad_viajar"] = yes_no

    return fields


# ==========================================
# 7. MÁQUINA DE ESTADOS CON VALIDACIÓN
# ==========================================

def _pending_question_for_stage(stage: str | Stage | None) -> str:
    stage_value = _stage_value(stage)

    if stage_value in {Stage.START.value, Stage.NEW_LEAD.value, Stage.ASK_CITY.value}:
        return "Para continuar, ¿en qué ciudad te encuentras actualmente?"

    if stage_value == Stage.ASK_LICENSE.value:
        return "Para continuar, ¿cuentas con licencia federal vigente?"

    if stage_value == Stage.ASK_EXPERIENCE.value:
        return "Para revisar si tu perfil aplica, ¿cuántos años tienes manejando quinta rueda?"

    if stage_value == Stage.ASK_APTO.value:
        return "Para continuar, ¿cuentas con apto médico vigente?"

    if stage_value == Stage.ASK_AVAILABILITY.value:
        return "Para terminar tu registro inicial, ¿tienes disponibilidad para viajar o realizar rutas foráneas?"

    if stage_value == Stage.HUMAN_REVIEW_REQUIRED.value:
        return "Tu caso ya está canalizado con Capital Humano para revisión."

    return "Para continuar, ¿en qué ciudad te encuentras actualmente?"


def _has_required_answer_for_stage(stage: str | Stage | None, fields: dict[str, Any]) -> bool:
    stage_value = _stage_value(stage)

    if stage_value in {Stage.START.value, Stage.NEW_LEAD.value, Stage.ASK_CITY.value}:
        return bool(fields.get("ciudad"))

    if stage_value == Stage.ASK_LICENSE.value:
        return fields.get("licencia_federal") in {"SI", "NO"}

    if stage_value == Stage.ASK_EXPERIENCE.value:
        return bool(fields.get("experiencia_quinta_rueda"))

    if stage_value == Stage.ASK_APTO.value:
        return fields.get("apto_medico") in {"SI", "NO"}

    if stage_value == Stage.ASK_AVAILABILITY.value:
        return fields.get("disponibilidad_viajar") in {"SI", "NO"}

    return False


def decide_next_stage(current_stage: str | None, fields: dict[str, Any]) -> tuple[str, str]:
    stage = _stage_value(current_stage)

    if stage in {Stage.START.value, Stage.NEW_LEAD.value}:
        if fields.get("ciudad"):
            return Stage.ASK_LICENSE.value, "Gracias. ¿Cuentas con licencia federal vigente?"
        return Stage.ASK_CITY.value, "Hola, gracias por tu interés. Para iniciar, ¿en qué ciudad te encuentras actualmente?"

    if stage == Stage.ASK_CITY.value:
        if fields.get("ciudad"):
            return Stage.ASK_LICENSE.value, "Gracias. ¿Cuentas con licencia federal vigente?"
        return Stage.ASK_CITY.value, _pending_question_for_stage(stage)

    if stage == Stage.ASK_LICENSE.value:
        if fields.get("licencia_federal") in {"SI", "NO"}:
            return Stage.ASK_EXPERIENCE.value, "Perfecto. ¿Cuántos años de experiencia tienes manejando quinta rueda?"
        return Stage.ASK_LICENSE.value, _pending_question_for_stage(stage)

    if stage == Stage.ASK_EXPERIENCE.value:
        if fields.get("experiencia_quinta_rueda"):
            return Stage.ASK_APTO.value, "Gracias. ¿Cuentas con apto médico vigente?"
        return Stage.ASK_EXPERIENCE.value, _pending_question_for_stage(stage)

    if stage == Stage.ASK_APTO.value:
        if fields.get("apto_medico") in {"SI", "NO"}:
            return Stage.ASK_AVAILABILITY.value, "Bien. ¿Tienes disponibilidad para viajar o realizar rutas foráneas?"
        return Stage.ASK_APTO.value, _pending_question_for_stage(stage)

    if stage == Stage.ASK_AVAILABILITY.value:
        if fields.get("disponibilidad_viajar") == "SI":
            return Stage.PROFILE_READY.value, (
                "Gracias. Con esto ya tengo tu información base; voy a dejar tu perfil listo para revisión de Capital Humano."
            )
        if fields.get("disponibilidad_viajar") == "NO":
            return Stage.ASK_AVAILABILITY.value, (
                "Gracias por aclararlo. Lo dejo registrado, pero Capital Humano tendría que validar si hay una opción que se ajuste a tu disponibilidad."
            )
        if fields.get("disponibilidad_viajar") == "CONDICIONADA":
            return Stage.ASK_AVAILABILITY.value, STATIC_REPLIES[Intent.CONDITIONAL_AVAILABILITY.value]
        return Stage.ASK_AVAILABILITY.value, _pending_question_for_stage(stage)

    if stage == Stage.PROFILE_READY.value:
        return Stage.PROFILE_READY.value, ""

    if stage == Stage.CLARIFY_AMBIGUOUS_SLANG.value:
        return Stage.ASK_CITY.value, "Gracias por aclararlo. Para continuar, ¿en qué ciudad te encuentras actualmente?"

    if stage == Stage.HUMAN_REVIEW_REQUIRED.value:
        return Stage.HUMAN_REVIEW_REQUIRED.value, STATIC_REPLIES["RESTRICTIVE_LOCKED"]

    return Stage.ASK_CITY.value, _pending_question_for_stage(Stage.ASK_CITY.value)


# ==========================================
# 8. RAG
# ==========================================

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
2. Si no hay información suficiente, dilo con claridad y no inventes.
3. No prometas sueldo, contratación, beneficios, rutas, descansos, pago por kilómetro ni condiciones no confirmadas.
4. Si el contexto recuperado trae una cifra o condición específica, puedes mencionarla como "según la información disponible", aclarando que Capital Humano confirma la información final.
5. Si el contexto no trae una cifra o condición específica, no la inventes y di que Capital Humano debe confirmarla.
6. Responde breve, natural y en español.
7. No hagas preguntas de seguimiento. Solo responde la duda documental.
8. No termines con frases como "¿Quieres que te aclare algo más?", "¿Tienes otra duda?", "puedo ayudarte" o similares.
9. Si el dato debe validarlo Capital Humano, dilo de forma natural.

RESPUESTA:
"""

    answer = _strip_followup_questions(call_llm(prompt).strip())

    sources = [_source_payload(item) for item in valid_ctx]

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


def answer_sensitive_with_rag(
    conversation_key: str,
    user_message: str,
    history: str,
    top_k: int | None = 5,
) -> dict[str, Any]:
    ctx = retrieve_context_for_guardrail(user_message, top_k=top_k)
    valid_ctx = [item for item in ctx if (item["score"] or 0) >= 0.20]

    if valid_ctx:
        context_text = "\n\n---\n\n".join(item["text"] for item in valid_ctx)
    else:
        context_text = "No se encontro informacion suficiente en los manuales RH."

    prompt = f"""
{SYSTEM_PROMPT}

=== HISTORIAL RECIENTE ===
{history}

=== CONTEXTO RECUPERADO DE MANUALES RH ===
{context_text}

=== MENSAJE DEL CANDIDATO ===
{user_message}

OBJETIVO:
Responder de forma humana, empática y firme a un candidato que habla sobre sustancias, alcohol, cansancio extremo,
seguridad en ruta o condiciones difíciles del trabajo operativo.

REGLAS OBLIGATORIAS:
1. No juzgues ni regañes al candidato.
2. Reconoce que el trabajo en carretera puede ser exigente solo si el contexto lo permite.
3. Mantén clara la política de cero tolerancia en sustancias o alcohol relacionados con operación.
4. Puedes explicar beneficios, seguridad, monitoreo, descanso, rutas o pagos solo si aparecen en el contexto recuperado.
5. No inventes pagos, descansos, rutas, monitoreo, esquemas, prestaciones ni condiciones.
6. No prometas contratación.
7. No digas que el candidato quedó descartado.
8. No menciones que internamente se creó una nota, alerta, handoff o revisión.
9. No hagas más de una pregunta al final.
10. Si no hay contexto suficiente, usa una respuesta breve basada en la política general de cero tolerancia y pide continuar con datos reales del proceso.
11. Cierra con un tono humano, orientado a seguridad y proceso formal.
12. No termines con frases genéricas como "puedo ayudarte" o "si tienes más dudas".

RESPUESTA:
"""

    answer = _strip_followup_questions(call_llm(prompt).strip())

    sources = [_source_payload(item) for item in valid_ctx]

    save_rag_audit(
        conversation_key=conversation_key,
        user_message=user_message,
        answer=answer,
        sources=sources,
        top_k=top_k,
        min_score=0.20,
    )

    return {
        "answer": answer,
        "sources": sources,
    }


# ==========================================
# 9. JERGA AMBIGUA
# ==========================================

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
        "ritalin",
        "ritalín",
        "pastilla",
        "pastillas",
    ]

    if any(p in m for p in high_risk_patterns):
        return False

    return any(p in m for p in safe_patterns)


# ==========================================
# 10. RESPUESTA ÚNICA / DRY TAIL
# ==========================================

def _finalize_turn(
    conversation_key: str,
    reply: str,
    current_stage: str,
    next_stage: str,
    intent: str,
    risk_level: str,
    requires_human: bool,
    event_type: str,
    sources: list[dict[str, Any]] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    sources = sources or []
    metadata = metadata or {}

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
        event_type=event_type,
        stage_from=current_stage,
        stage_to=next_stage,
        intent=intent,
        risk_level=risk_level,
        requires_human=requires_human,
        metadata=metadata,
    )

    return {
        "status": "ok",
        "conversation_key": conversation_key,
        "reply": reply,
        "current_stage": next_stage,
        "requires_human": requires_human,
        "risk_level": risk_level,
        "intent": intent,
        "sources": sources,
    }


# ==========================================
# 11. ORQUESTADOR PRINCIPAL
# ==========================================

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
    current_stage = _stage_value(conversation.get("current_stage") or Stage.START.value)

    save_message(conversation_key, "user", message)

    # Candado operativo:
    # Si ya está en revisión humana, NO se desbloquea por mensajes posteriores.
    if current_stage == Stage.HUMAN_REVIEW_REQUIRED.value:
        detection = detect_intent_and_risk(message)
        intent = _intent_value(detection.get("intent"))
        history = _history_text(state["messages"])

        sensitive_result = answer_sensitive_with_rag(
            conversation_key=conversation_key,
            user_message=message,
            history=history,
            top_k=5,
        )

        reply = sensitive_result["answer"].strip() or STATIC_REPLIES["RESTRICTIVE_LOCKED"]
        sources = sensitive_result["sources"]

        log_event(
            conversation_key=conversation_key,
            event_type="restrictive_review_message_received",
            stage_from=current_stage,
            stage_to=current_stage,
            intent=intent,
            risk_level="high",
            requires_human=True,
            metadata={
                "external_message_id": external_message_id,
                "channel": channel,
                "reason": "human_review_lock",
                "candidate_message": message,
                "detected_reason": detection.get("reason"),
                "sources": sources,
            },
        )

        return _finalize_turn(
            conversation_key=conversation_key,
            reply=reply,
            current_stage=current_stage,
            next_stage=Stage.HUMAN_REVIEW_REQUIRED.value,
            intent=intent,
            risk_level="high",
            requires_human=True,
            event_type="restrictive_review_locked",
            sources=sources,
            metadata={
                "external_message_id": external_message_id,
                "channel": channel,
                "reason": "human_review_lock",
                "detected_reason": detection.get("reason"),
                "sources": sources,
            },
        )

    detection = detect_intent_and_risk(message)

    if current_stage == Stage.CLARIFY_AMBIGUOUS_SLANG.value:
        is_safe = _is_safe_clarification_response(message)

        if is_safe:
            detection = {
                "intent": Intent.SLANG_SAFE.value,
                "risk_level": "low",
                "requires_human": False,
                "requires_rag": False,
                "requires_clarification": False,
                "reason": "jerga_aclarada_segura",
            }
        elif _is_meta_complaint_or_confusion(message):
            detection = {
                "intent": Intent.CANDIDATE_ANSWER.value,
                "risk_level": "low",
                "requires_human": False,
                "requires_rag": False,
                "requires_clarification": False,
                "reason": "aclaracion_no_riesgosa_o_confusion",
            }
            current_stage = Stage.ASK_CITY.value
        else:
            detection = {
                "intent": Intent.SLANG_RISKY.value,
                "risk_level": "high",
                "requires_human": True,
                "requires_rag": False,
                "requires_clarification": False,
                "reason": "jerga_aclarada_con_riesgo",
            }

    intent = _intent_value(detection.get("intent"))
    risk_level = detection.get("risk_level") or "low"
    requires_human = bool(detection.get("requires_human", False))
    requires_clarification = bool(detection.get("requires_clarification", False))
    requires_rag = bool(detection.get("requires_rag", False))

    fields = extract_profile_fields(message, current_stage)

    city_catalog = fields.pop("_city_catalog", None) if fields else None
    city_requires_ch_validation = (
        bool(fields.pop("_city_requires_ch_validation", False)) if fields else False
    )

    # Si estamos perfilando y el candidato respondió claramente la pregunta pendiente,
    # no mandamos el mensaje al RAG aunque contenga palabras como "licencia", "apto" o "viajar".
    if (
        current_stage in PROFILE_STAGES
        and not _is_question(message)
        and requires_rag
        and _has_required_answer_for_stage(current_stage, fields)
    ):
        intent = Intent.CANDIDATE_ANSWER.value
        risk_level = "low"
        requires_human = False
        requires_rag = False
        requires_clarification = False
        detection = {
            **detection,
            "intent": intent,
            "risk_level": risk_level,
            "requires_human": requires_human,
            "requires_rag": requires_rag,
            "requires_clarification": requires_clarification,
            "reason": "respuesta_de_perfilamiento_detectada",
        }

    if city_requires_ch_validation and risk_level != "high":
        intent = Intent.FOREIGN_VALIDATION.value
        risk_level = "medium"
        requires_human = True

    if fields.get("disponibilidad_viajar") == "CONDICIONADA":
        intent = Intent.CONDITIONAL_AVAILABILITY.value
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

    # 1) Aclaración de jerga.
    if requires_clarification:
        return _finalize_turn(
            conversation_key=conversation_key,
            reply=STATIC_REPLIES[Intent.AMBIGUOUS_SLANG.value],
            current_stage=current_stage,
            next_stage=Stage.CLARIFY_AMBIGUOUS_SLANG.value,
            intent=intent,
            risk_level=risk_level,
            requires_human=False,
            event_type="clarification_requested",
            metadata={"reason": detection.get("reason")},
        )

    # 2) Riesgo alto / revisión humana restrictiva.
    if requires_human and risk_level == "high":
        create_handoff(
            conversation_key=conversation_key,
            reason=detection.get("reason") or "tema_sensible",
            risk_level=risk_level,
            summary=message,
        )

        return _finalize_turn(
            conversation_key=conversation_key,
            reply=STATIC_REPLIES[Intent.SENSITIVE_HANDOFF.value],
            current_stage=current_stage,
            next_stage=Stage.HUMAN_REVIEW_REQUIRED.value,
            intent=intent,
            risk_level="high",
            requires_human=True,
            event_type="human_handoff_created",
            metadata={"reason": detection.get("reason")},
        )

    # 3) Disponibilidad condicionada.
    if intent == Intent.CONDITIONAL_AVAILABILITY.value:
        create_handoff(
            conversation_key=conversation_key,
            reason="disponibilidad_condicionada",
            risk_level=risk_level,
            summary=message,
        )

        return _finalize_turn(
            conversation_key=conversation_key,
            reply=STATIC_REPLIES[Intent.CONDITIONAL_AVAILABILITY.value],
            current_stage=current_stage,
            next_stage=current_stage,
            intent=intent,
            risk_level=risk_level,
            requires_human=True,
            event_type="conditional_availability_marked",
            metadata={"reason": detection.get("reason"), "fields": fields},
        )

    # 4) Intenciones estáticas.
    if intent in {
        Intent.FOLLOWUP_TIME.value,
        Intent.DOCUMENTS_COMPLETE.value,
        Intent.FORANEO_TRAVEL.value,
    }:
        reply = STATIC_REPLIES[intent]

        if requires_human:
            create_handoff(
                conversation_key=conversation_key,
                reason=detection.get("reason") or "seguimiento_capital_humano",
                risk_level=risk_level,
                summary=message,
            )

        return _finalize_turn(
            conversation_key=conversation_key,
            reply=reply,
            current_stage=current_stage,
            next_stage=current_stage,
            intent=intent,
            risk_level=risk_level,
            requires_human=requires_human,
            event_type=f"{intent}_answered",
            metadata={"reason": detection.get("reason")},
        )

    # 5) Preguntas documentales / RAG.
    if requires_rag:
        rag_result = answer_with_rag(
            conversation_key=conversation_key,
            user_message=message,
            history=history,
            top_k=5,
        )

        sources = rag_result["sources"]
        answer = rag_result["answer"].strip()

        if current_stage in PROFILE_STAGES:
            if _has_required_answer_for_stage(current_stage, fields):
                next_stage, next_question = decide_next_stage(current_stage, fields)
                reply = f"{answer}\n\n{next_question}" if next_question else answer
            else:
                next_stage = current_stage
                # No insistir con la pregunta pendiente cada vez que el candidato está consultando documentos.
                reply = answer or _pending_question_for_stage(current_stage)
        else:
            next_stage = current_stage
            reply = answer or (
                "Ese punto debe validarlo Capital Humano para no darte información incorrecta."
            )

        if requires_human and risk_level == "medium":
            create_handoff(
                conversation_key=conversation_key,
                reason=detection.get("reason") or "requiere_validacion_rh",
                risk_level=risk_level,
                summary=message,
            )

        return _finalize_turn(
            conversation_key=conversation_key,
            reply=reply,
            current_stage=current_stage,
            next_stage=next_stage,
            intent=intent,
            risk_level=risk_level,
            requires_human=requires_human,
            event_type="rag_answered",
            sources=sources,
            metadata={
                "sources": sources,
                "fields": fields,
                "reason": detection.get("reason"),
            },
        )

    # Si el usuario se queja de que no se respondió, no lo tratamos como dato de perfil.
    if _is_meta_complaint_or_confusion(message):
        return _finalize_turn(
            conversation_key=conversation_key,
            reply=(
                "Tienes razón, déjame responderte de forma más directa. "
                "¿Me puedes repetir la duda específica para revisarla con la información disponible?"
            ),
            current_stage=current_stage,
            next_stage=current_stage,
            intent=Intent.CANDIDATE_ANSWER.value,
            risk_level="low",
            requires_human=False,
            event_type="meta_complaint_handled",
            metadata={"reason": detection.get("reason")},
        )

    # 6) Flujo normal de perfilamiento.
    next_stage, reply = decide_next_stage(current_stage, fields)

    if not reply:
        reply = STATIC_REPLIES["DEFAULT_PROFILE_END"]

    return _finalize_turn(
        conversation_key=conversation_key,
        reply=reply,
        current_stage=current_stage,
        next_stage=next_stage,
        intent=intent,
        risk_level=risk_level,
        requires_human=requires_human,
        event_type="stage_changed",
        metadata={
            "fields": fields,
            "city_catalog": city_catalog,
            "city_requires_ch_validation": city_requires_ch_validation,
        },
    )
