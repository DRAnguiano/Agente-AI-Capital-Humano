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

AGE_LIMIT_EXCLUSIVE = 50
AGE_DISQUALIFICATION_REPLY = (
    "Gracias por su interés. Por el momento el perfil de esta vacante considera "
    "operadores menores de 50 años, por lo que no podemos continuar con su solicitud."
)
RENEWAL_PROOF_QUESTION = (
    "Su {documento} vence en menos de 3 meses. ¿Ya tiene el papel o comprobante "
    "de renovación?"
)
RENEWAL_PROOF_REQUIRED_REPLY = (
    "Entiendo. Para continuar necesitamos que tenga el papel o comprobante de "
    "renovación. Cuando lo tenga, continuamos con su registro."
)

_NUMBER_WORDS = {
    "un": 1,
    "una": 1,
    "uno": 1,
    "dos": 2,
    "tres": 3,
    "cuatro": 4,
    "cinco": 5,
    "seis": 6,
    "siete": 7,
    "ocho": 8,
    "nueve": 9,
    "diez": 10,
}


def _to_int(value: Any) -> int | None:
    text = normalize_text(str(value or "")).strip()
    if text.isdigit():
        return int(text)
    m = re.search(r"\b(\d{1,2})\b", text)
    if m:
        return int(m.group(1))
    return None


def is_age_disqualified(facts: dict[str, Any]) -> bool:
    age = _to_int(facts.get("candidate.age"))
    return age is not None and age >= AGE_LIMIT_EXCLUSIVE


def _number_token_to_int(token: str) -> int | None:
    token = normalize_text(token)
    if token.isdigit():
        return int(token)
    return _NUMBER_WORDS.get(token)


def _expiry_within_three_months(expiration_text: Any) -> bool:
    t = normalize_text(str(expiration_text or ""))
    if not t:
        return False
    if any(word in t for word in ("vencido", "vencida", "caducado", "caducada")):
        return True
    m = re.search(
        r"\b(\d{1,2}|un|una|uno|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez)\s+"
        r"(dias?|semanas?|mes(?:es)?)\b",
        t,
    )
    if not m:
        return False
    amount = _number_token_to_int(m.group(1))
    unit = m.group(2)
    if amount is None:
        return False
    if unit.startswith("dia") or unit.startswith("semana"):
        return True
    if unit.startswith("mes"):
        return amount <= 3
    return False


def _renewal_proof_state(facts: dict[str, Any], document_key: str) -> str:
    specific = facts.get(f"{document_key}.renewal_proof")
    general = facts.get("documents.renewal_proof")
    return normalize_text(str(specific or general or ""))


def _renewal_question_for_short_expiry(facts: dict[str, Any]) -> str | None:
    checks = (
        ("license.expiration_text", "license", "licencia federal"),
        ("medical.apto_expiration_text", "medical", "apto médico"),
    )
    for exp_key, proof_key, label in checks:
        if _expiry_within_three_months(facts.get(exp_key)):
            proof = _renewal_proof_state(facts, proof_key)
            if proof in {"no", "nel", "nop", "ninguno", "sin papel", "sin comprobante"}:
                return RENEWAL_PROOF_REQUIRED_REPLY
            if proof not in {"si", "sí", "yes", "true", "tengo", "ya tengo"}:
                return RENEWAL_PROOF_QUESTION.format(documento=label)
    return None


def _has_labor_document(facts: dict[str, Any]) -> bool:
    return (
        facts.get("documents.labor_letters") in {"sí", "si", "available"}
        or facts.get("documents.labor_letters_status") in {"available", "sí", "si"}
        or facts.get("documents.proof") in {"cartas", "semanas_imss", "sí", "si"}
    )


def _contextual_expiration_text(norm_message: str) -> str | None:
    m = re.fullmatch(
        r"(?:como\s+)?(?:en\s+)?"
        r"(\d{1,2}|un|una|uno|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez)"
        r"\s+(dias?|semanas?|mes(?:es)?|ano|anos|anio|anios)",
        norm_message.strip(),
    )
    if not m:
        return None
    n = _number_token_to_int(m.group(1))
    if n is None:
        return None
    unit = m.group(2)
    unit_label = "años" if unit in {"ano", "anos", "anio", "anios"} else unit
    return f"vence en {n} {unit_label}"

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

    # "si" CONDICIONAL (if), no afirmativo: "si me cuentas un chiste te digo..."
    # no confirma nada — sin esta guarda, el guard infería license.status=vigente
    # y pisaba la respuesta correcta (smoke 2026-06-12 19:46). Acotado a
    # pronombre+verbo de petición para NO bloquear confirmaciones reales tipo
    # "si me queda todavia un año".
    _conditional_si = bool(re.match(
        r"^si\s+(?:me|te|le|nos|les|usted|tu)\s+"
        r"(?:cuenta|cuentas|dice|dices|da|das|pasa|pasas|explica|explicas|manda|mandas|dan|dicen)\b",
        t,
    ))
    strong_yes = not _conditional_si and (
        t == "si"
        or (t.startswith("si ") and not t.startswith("si no "))
        or t.startswith("si,")
        or t.startswith("claro")
        or t.startswith("correcto")
        or t.startswith("exacto")
        or t in {"simon", "sip"}
    )
    # "ya" de RECLAMO no es confirmación: "ya le habia dicho que 10 años"
    # re-confirmaba apto vigente (smoke 2026-06-12 16:16).
    _ya_reclamo = bool(re.match(r"^ya\s+(?:le|te|les|lo|la|se|los|las)\b", t))
    # Confirmaciones suaves/ambiguas: solo válidas si no hay negación en el mensaje.
    soft_yes = not _ya_reclamo and (
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

        # Respuesta elíptica numérica: "10" / "10 años" tras la pregunta de
        # años de experiencia (smoke 2026-06-12 16:16: "10 años" no se entendió).
        if "experience.years" not in facts:
            last_norm = normalize_text(last_bot_message)
            if "experiencia" in last_norm and re.search(r"\bcuantos anos\b", last_norm):
                m = re.fullmatch(r"(\d{1,2})(?:\s*(?:anos|años))?", text)
                if m:
                    facts["experience.years"] = f"{m.group(1)} años"

        exp_text = _contextual_expiration_text(text)
        if exp_text:
            last_norm = normalize_text(last_bot_message)
            if "license.expiration_text" not in facts and "licencia" in last_norm and "vence" in last_norm:
                facts["license.expiration_text"] = exp_text
            if "medical.apto_expiration_text" not in facts and "apto" in last_norm and "vence" in last_norm:
                facts["medical.apto_expiration_text"] = exp_text

    # Fields only needed by the debounce guard, not persisted to lead_memory.
    if any(t in text for t in ("cuanto pagan", "pago", "sueldo", "compensacion", "kilometro", "km")):
        facts["interest.payment"] = "asked"
    if any(t in text for t in ("que rutas", "rutas tienen", "bases", "cedis")):
        facts["interest.routes"] = "asked"

    city_norm = normalize_text(facts.get("candidate.city") or "")
    facts["location.is_local_laguna"] = city_norm in LOCAL_LAGUNA

    return facts


# Entradas de campaña/interés (incluye el mensaje default de la publicación de
# Facebook). El interés NO es un dato de perfil: detona la apertura, no el ack.
CAMPAIGN_INTEREST_TERMS = (
    "me interesa la vacante",
    "me interesa el puesto",
    "me interesa el trabajo",
    "me interesa la chamba",
    "informacion de la vacante",
    "info de la vacante",
    "informes de la vacante",
)


def is_campaign_or_interest_entry(message: str | None) -> bool:
    """True si el mensaje es una entrada de campaña/interés sin pregunta.

    En primer contacto debe responderse con el saludo oficial de Mundo, nunca
    con el ack del guard ("Perfecto, lo dejo registrado").
    """
    if is_question(message):
        return False
    t = normalize_text(message or "")
    return any(term in t for term in CAMPAIGN_INTEREST_TERMS)


# Facts que NO cuentan como señal de perfil para el guard: el interés en la
# vacante no es un dato del candidato (regla de negocio 2026-06-12).
_NON_PROFILE_SIGNAL_KEYS = {"candidate.vacancy_accepted"}


def has_current_turn_profile_signal(message: str | None, last_bot_message: str | None = None) -> bool:
    facts = extract_current_turn_facts(message, last_bot_message)
    # location.is_local_laguna is always computed — exclude it from the signal check
    return any(
        key.startswith(("candidate.", "license.", "medical.", "documents.", "experience."))
        and key not in _NON_PROFILE_SIGNAL_KEYS
        for key in facts
    )


# Pregunta de negocio EMBEBIDA sin "?" ni inicio interrogativo (jerga real:
# "soy d gomez palasio, que rutas ay y dan voleto pa ir a torreon"). Si está
# presente, el orquestador debe responder la duda — el guard no secuestra el
# turno; los facts se persisten igual en la extracción del orquestador.
_EMBEDDED_QUESTION_RE = re.compile(
    r"\b(?:que|cuanto|cuanta|cuantos|cuantas|cuando|como|cual|cuales|donde|a donde|"
    r"pa donde|pa onde|hay|ay|dan|necesitan?|nececitan?|ocupan?|piden?|sirve)\b"
    r"[^.]{0,60}?"
    r"\b(?:rutas?|corridas?|vueltas?|tramos?|pagan?|pago|sueldo|salario|boletos?|"
    r"prestaciones|vacantes?|tiran|descansos?|bonos?|requisitos?|cartas?|documentos?)\b"
    # ...o el orden inverso: "cartas... ¿cuantas necesita?"
    r"|\b(?:cartas?|documentos?)\b[^.]{0,60}?\b(?:cuantas?|cuantos?|necesitan?|nececitan?|ocupan?|sirven?)\b"
    # ...o cantidad con referente implícito: "¿cuantas necesita?" (cartas del contexto)
    r"|\bcuant[oa]s?\s+(?:se\s+)?(?:necesit\w*|nececit\w*|ocup\w*|pid\w*)\b"
)


def has_embedded_business_question(message: str | None) -> bool:
    return bool(_EMBEDDED_QUESTION_RE.search(normalize_text(message or "")))


def should_prioritize_current_turn(message: str | None, last_bot_message: str | None = None) -> bool:
    """Evita que RAG/memoria pisen una respuesta clara del candidato."""
    if is_question(message) or has_embedded_business_question(message):
        return False
    return has_current_turn_profile_signal(message, last_bot_message)


def next_question_from_missing_facts(facts: dict[str, Any]) -> str:
    if not facts.get("candidate.city"):
        return "Para continuar, ¿en qué ciudad te encuentras actualmente?"
    if not facts.get("candidate.age"):
        return "Gracias. ¿Cuántos años tiene?"
    if is_age_disqualified(facts):
        return AGE_DISQUALIFICATION_REPLY
    if not facts.get("experience.vehicle_type"):
        return (
            "¿Su experiencia es en tracto full o en sencillo? "
            "Las vacantes disponibles son para operadores de tracto full o sencillo."
        )
    if not facts.get("license.category"):
        return "Gracias. ¿Qué tipo de licencia federal tiene y cuándo vence?"
    if not facts.get("license.expiration_text"):
        return "¿En cuánto tiempo se le vence su licencia federal?"
    renewal_question = _renewal_question_for_short_expiry(facts)
    if renewal_question:
        return renewal_question
    if not facts.get("medical.apto_expiration_text"):
        return "¿Cuándo vence su apto médico?"
    renewal_question = _renewal_question_for_short_expiry(facts)
    if renewal_question:
        return renewal_question
    if not facts.get("experience.years"):
        return "Perfecto. ¿Cuántos años de experiencia tiene como operador?"
    if not _has_labor_document(facts):
        return "¿Cuenta con cartas laborales o semanas del IMSS?"
    return _profile_complete_closing()


# Quita un "Perfecto" inicial (+ puntuación de cierre, sin tocar ¿/¡) de la pregunta
# cuando el ack ya abre con "Perfecto", para no duplicar el prefijo.
_LEADING_PERFECTO = re.compile(r"^perfecto\s*[,.:;!]*\s*", re.IGNORECASE)


def _strip_leading_perfecto(text: str) -> str:
    stripped = _LEADING_PERFECTO.sub("", text, count=1)
    if stripped and stripped[0].isalpha() and stripped[0].islower():
        stripped = stripped[0].upper() + stripped[1:]
    return stripped


def _join_ack_and_question(prefix: str, question: str | None) -> str:
    """Une el ack y la siguiente pregunta evitando un doble prefijo "Perfecto".

    Puro: no extrae facts ni mete lógica de negocio. Si el ack ya abre con
    "Perfecto" y la pregunta también, se quita el "Perfecto" inicial de la
    pregunta. Sin ack (prefix vacío), la pregunta se conserva tal cual.
    """
    prefix = (prefix or "").strip()
    question = (question or "").strip()
    if not prefix:
        return question
    if not question:
        return prefix
    if prefix.lower().startswith("perfecto") and question.lower().startswith("perfecto"):
        question = _strip_leading_perfecto(question)
    return f"{prefix} {question}".strip()


def build_current_turn_ack(message: str | None, merged_facts: dict[str, Any] | None = None, last_bot_message: str | None = None) -> str:
    current = extract_current_turn_facts(message, last_bot_message)
    # Full profile for deciding what to ask next; only current turn for the ack prefix.
    facts = {**(merged_facts or {}), **current}

    if is_age_disqualified(facts):
        return AGE_DISQUALIFICATION_REPLY

    detected = []
    if current.get("candidate.city"):
        detected.append(f"ciudad {current['candidate.city']}")
    if current.get("license.category"):
        detected.append(f"licencia tipo {current['license.category']}")
    if current.get("license.expiration_text"):
        detected.append(f"licencia vence {current['license.expiration_text']}")
    if current.get("medical.apto_status") == "vigente":
        detected.append("apto médico vigente")
    if current.get("medical.apto_expiration_text"):
        detected.append(f"apto vence {current['medical.apto_expiration_text']}")
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
        detected.append("experiencia en camión sencillo")
    elif vt == "full":
        # Solo full confirma tracto full; jerga (quinta rueda/tráiler) nunca
        # llega aquí como vehicle_type y no debe afirmarse como full.
        detected.append("experiencia en tracto full")

    if detected:
        prefix = "Perfecto, registro " + ", ".join(detected) + "."
    else:
        prefix = "Perfecto, lo dejo registrado."

    return _join_ack_and_question(prefix, next_question_from_missing_facts(facts))
