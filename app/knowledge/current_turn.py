import datetime
import re
from typing import Any

from app.knowledge.text_normalizer import normalize_text

try:
    from zoneinfo import ZoneInfo as _ZoneInfo
    _TZ_CENTRO = _ZoneInfo("America/Mexico_City")
except Exception:
    _TZ_CENTRO = None


def _profile_complete_closing() -> str:
    """Closing message shown when all profile fields have been collected."""
    now = datetime.datetime.now(tz=_TZ_CENTRO) if _TZ_CENTRO else datetime.datetime.now()
    en_horario = (
        now.weekday() < 5
        and datetime.time(8, 0) <= now.time() <= datetime.time(17, 30)
    )
    msg = (
        "¡Gracias por completar tu información! Para avanzar en tu proceso, "
        "te pedimos que vayas subiendo tus documentos: licencia federal, apto médico y cartas laborales. "
        "Una vez que los verifiquemos y todo esté en orden, nos comunicaremos contigo "
        "siempre que sigas interesado."
    )
    if not en_horario:
        msg += (
            " Nuestro horario de atención es de lunes a viernes de 08:00 a 17:30 hrs (centro de México). "
            "Si gustas, dinos un horario en ese rango para agendarte una llamada, "
            "y sube tus documentos para que en cuanto arranque el sistema de oficina podamos continuar con tu candidatura."
        )
    return msg


LOCAL_LAGUNA = ["torreon", "torreon coahuila", "gomez palacio", "lerdo", "matamoros"]

# Detect the topic of the last bot question for context-aware "si" interpretation
_TOPIC_APTO = re.compile(r"\bapto\b", re.IGNORECASE)
_TOPIC_LICENSE_VIGENTE = re.compile(
    r"\blicencia\b.{0,80}(?:\bvigente\b|\bvigencia\b|\bal\s+corriente\b)"
    r"|(?:\bvigente\b|\bvigencia\b).{0,80}\blicencia\b",
    re.IGNORECASE | re.DOTALL,
)
_TOPIC_LETTERS = re.compile(r"\bcartas?\s+laborales?\b", re.IGNORECASE)


def _extract_context_confirmation_facts(norm_message: str, last_bot_message: str) -> dict[str, Any]:
    """Infer profile facts when the candidate gives a short affirmation.

    Example: bot asks '¿Tu apto médico está vigente?' and candidate replies
    'si de hace 6 meses me queda todavia' → infer medical.apto_status=vigente.
    """
    t = norm_message.strip()

    # Negaciones / desinterés: si aparecen, NO se interpreta como confirmación.
    # Cubre "ya no", "ya conseguí trabajo", "ya me hablaron de otro trabajo", etc.
    _neg_hints = {
        "no", "nel", "nop", "tampoco", "nunca",
        "otro", "otra",
        "consegui", "conseguí", "encontre", "encontré",
        "vencido", "vencida", "vencio", "venció", "caducado", "caducada",
    }
    has_negation = any(tok in _neg_hints for tok in t.split())

    strong_yes = (
        t == "si"
        or (t.startswith("si ") and not t.startswith("si no "))
        or t.startswith("si,")
        or t.startswith("claro")
        or t.startswith("correcto")
        or t.startswith("exacto")
        or t in {"simon", "sip"}
    )
    # Confirmaciones suaves/ambiguas: solo válidas si no hay negación en el mensaje.
    soft_yes = (
        t in {"ok", "okay", "oka", "va", "sale", "dale", "ya"}
        or t.startswith(("ok ", "va ", "sale ", "dale ", "ya "))
    )
    # La negación bloquea cualquier confirmación (incluye "si no, ...").
    is_yes = (strong_yes or soft_yes) and not has_negation
    if not is_yes:
        return {}

    facts: dict[str, Any] = {}
    if _TOPIC_APTO.search(last_bot_message):
        facts["medical.apto_status"] = "vigente"
    if _TOPIC_LICENSE_VIGENTE.search(last_bot_message):
        facts["license.status"] = "vigente"
    if _TOPIC_LETTERS.search(last_bot_message):
        facts["documents.labor_letters"] = "sí"
    return facts


def is_question(text: str | None) -> bool:
    raw = text or ""
    norm = normalize_text(raw)
    if "?" in raw or "¿" in raw:
        return True
    return bool(re.match(r"^(cuanto|cuanta|cuantos|cuantas|cuando|donde|que|como|cual|pagan|tienen|hay|manejan)\b", norm))


def extract_current_turn_facts(message: str | None, last_bot_message: str | None = None) -> dict[str, Any]:
    """Dict view of profile facts for the debounce guard in tasks_chatwoot.

    Delegates extraction to profile_extractor (single source of truth) and adds
    the debounce-specific fields: interest.payment, interest.routes,
    location.is_local_laguna.

    When last_bot_message is provided, also infers facts from short confirmations
    ("si", "claro") based on what the bot last asked.
    """
    from app.lead_memory.profile_extractor import extract_profile_facts_as_dict

    raw = (message or "").strip()
    if not raw:
        return {}

    facts = extract_profile_facts_as_dict(raw)
    text = normalize_text(raw)

    # Context-aware: infer field from "si" when we know what was last asked
    if last_bot_message:
        for k, v in _extract_context_confirmation_facts(text, last_bot_message).items():
            if k not in facts:
                facts[k] = v

    # Fields only needed by the debounce guard, not persisted to lead_memory.
    if any(t in text for t in ("cuanto pagan", "pago", "sueldo", "compensacion", "kilometro", "km")):
        facts["interest.payment"] = "asked"
    if any(t in text for t in ("que rutas", "rutas tienen", "bases", "cedis")):
        facts["interest.routes"] = "asked"

    city_norm = normalize_text(facts.get("candidate.city") or "")
    facts["location.is_local_laguna"] = city_norm in LOCAL_LAGUNA

    return facts


def has_current_turn_profile_signal(message: str | None, last_bot_message: str | None = None) -> bool:
    facts = extract_current_turn_facts(message, last_bot_message)
    # location.is_local_laguna is always computed — exclude it from the signal check
    return any(
        key.startswith(("candidate.", "license.", "medical.", "documents.", "experience."))
        for key in facts
    )


def should_prioritize_current_turn(message: str | None, last_bot_message: str | None = None) -> bool:
    """Evita que RAG/memoria pisen una respuesta clara del candidato."""
    if is_question(message):
        return False
    return has_current_turn_profile_signal(message, last_bot_message)


def next_question_from_missing_facts(facts: dict[str, Any]) -> str:
    if not facts.get("candidate.city"):
        return "Para continuar, ¿en qué ciudad te encuentras actualmente?"
    if not facts.get("license.category") and not facts.get("license.status"):
        return "Gracias. ¿Qué tipo de licencia federal tienes y está vigente?"
    if not facts.get("experience.years"):
        return "Perfecto. ¿Cuántos años de experiencia tienes como operador?"
    if not facts.get("experience.vehicle_type"):
        duration = facts.get("experience.years", "")
        return (
            f"¿Y esa experiencia ({duration}) es en quinta rueda/full o en camión sencillo? "
            "Las vacantes disponibles son para operadores de quinta rueda/full."
        )
    if not facts.get("medical.apto_status"):
        escuelita = facts.get("experience.vehicle_type") == "sencillo"
        prefix = (
            "Anotado — la experiencia en sencillo se toma como escuelita y se valora. "
            "Las vacantes son para quinta rueda/full; Capital Humano evaluará tu perfil. "
        ) if escuelita else ""
        return f"{prefix}Gracias. ¿Tu apto médico está vigente?"
    if not facts.get("documents.labor_letters"):
        return "¿Cuentas con cartas laborales?"
    return _profile_complete_closing()


def build_current_turn_ack(message: str | None, merged_facts: dict[str, Any] | None = None, last_bot_message: str | None = None) -> str:
    current = extract_current_turn_facts(message, last_bot_message)
    # Full profile for deciding what to ask next; only current turn for the ack prefix.
    facts = {**(merged_facts or {}), **current}

    detected = []
    if current.get("candidate.city"):
        detected.append(f"ciudad {current['candidate.city']}")
    if current.get("license.category"):
        detected.append(f"licencia tipo {current['license.category']}")
    if current.get("medical.apto_status") == "vigente":
        detected.append("apto médico vigente")
    if current.get("documents.general_status") == "vigente":
        detected.append("documentación vigente")
    if current.get("documents.labor_letters") == "sí":
        detected.append("cartas laborales")
    if current.get("candidate.age"):
        detected.append(f"{current['candidate.age']} años")
    if current.get("experience.years"):
        detected.append(f"{current['experience.years']} de experiencia")
    vt = current.get("experience.vehicle_type")
    if vt == "sencillo":
        detected.append("experiencia en camión sencillo (escuelita)")
    elif vt in ("quinta_rueda", "full") or current.get("experience.fifth_wheel") == "sí":
        detected.append("experiencia en quinta rueda/full")

    if detected:
        prefix = "Perfecto, registro " + ", ".join(detected) + "."
    else:
        prefix = "Perfecto, lo dejo registrado."

    return f"{prefix} {next_question_from_missing_facts(facts)}"
