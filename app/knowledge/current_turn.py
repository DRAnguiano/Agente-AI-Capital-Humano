import datetime
import json
import os
import re
from typing import Any

from app.indexer import call_groq_json
from app.knowledge.business_hours import is_business_hours
from app.knowledge.text_normalizer import normalize_text

_EXTRACTOR_MODEL = os.getenv("GROQ_CLASSIFIER_MODEL", "llama-3.1-8b-instant")

_EXPIRATION_SYSTEM = """Eres un extractor de datos de reclutamiento.
Extrae la expresión de tiempo de vencimiento de un documento (licencia o apto médico) del mensaje del candidato.
Reglas:
- Si el candidato indica cuánto tiempo falta para que venza, devuélvela normalizada en español
- Formatos aceptados: "N años", "N meses", "N días", mes/año (ej. "diciembre 2026")
- Si el documento ya venció, devuelve "vencido"
- Si el mensaje es solo "sí", "vigente", "está bien" sin dato de tiempo, devuelve null
- Si no hay información de tiempo suficiente, devuelve null
Responde SOLO JSON sin texto extra: {"expiration_text": "<expresión>" | null}
Ejemplos:
- "Se me vence en 3 años" → {"expiration_text": "3 años"}
- "6 meses" → {"expiration_text": "6 meses"}
- "para diciembre" → {"expiration_text": "diciembre"}
- "al año" → {"expiration_text": "1 año"}
- "me falta como un año y medio" → {"expiration_text": "18 meses"}
- "ya vencida" → {"expiration_text": "vencido"}
- "vigente" → {"expiration_text": null}
- "sí" → {"expiration_text": null}"""

_AGE_SYSTEM = """Eres un extractor de datos de reclutamiento. El bot acaba de preguntar la EDAD del candidato.
Extrae la edad en años enteros de la respuesta. Rango plausible de adulto: 18–70.
Convierte palabras a números. Tabla de decenas en español:
  treinta=30, cuarenta=40, cincuenta=50, sesenta=60, setenta=70.
  "cincuenta y uno"=51, "cincuenta y dos"=52, "cincuenta y cinco"=55
  "sesenta y uno"=61, "sesenta y dos"=62
Si no hay edad clara o es ambiguo, devuelve null.
Responde SOLO JSON: {"age": <entero 18-70> | null}
Ejemplos:
- "35" → {"age": 35}
- "treinta y cinco años" → {"age": 35}
- "como unos 40" → {"age": 40}
- "tengo 28" → {"age": 28}
- "52" → {"age": 52}
- "cincuenta y un años" → {"age": 51}
- "tengo la edad de cincuenta y un años" → {"age": 51}
- "sesenta y dos" → {"age": 62}
- "no sé" → {"age": null}
- "25 años de experiencia" → {"age": null}"""

_EXPERIENCE_YEARS_SYSTEM = """Eres un extractor de datos de reclutamiento. El bot acaba de preguntar los AÑOS DE EXPERIENCIA del candidato como operador.
Extrae los años de experiencia de la respuesta. Normaliza a formato "N años".
Convierte palabras a números: "diez" → "10 años", "año y medio" → "1 año", "una década" → "10 años".
Si no hay dato numérico claro, devuelve null.
Responde SOLO JSON: {"years": "<N años>" | null}
Ejemplos:
- "10" → {"years": "10 años"}
- "diez" → {"years": "10 años"}
- "como 15 años" → {"years": "15 años"}
- "25 años manejando" → {"years": "25 años"}
- "10 y medio" → {"years": "10 años"}
- "desde 2010" → {"years": null}
- "poco tiempo" → {"years": null}"""



def _profile_complete_closing() -> str:
    """Closing message shown when all profile fields have been collected."""
    en_horario = is_business_hours()
    msg = (
        "¡Gracias por completar tu información! Para avanzar en tu proceso, "
        "te pedimos que vayas subiendo tus documentos: licencia federal, apto médico y cartas laborales. "
        "Una vez que los verifiquemos y todo esté en orden, nos comunicaremos contigo "
        "siempre que sigas interesado."
    )
    if en_horario:
        msg += (
            " Lo dejo registrado para que nuestro equipo pueda contactarte dentro del horario de atención."
        )
    else:
        msg += (
            " Nuestro horario de atención es de lunes a viernes de 08:00 a 17:30 hrs (centro de México). "
            "Si gustas, dinos un horario en ese rango para agendarte una llamada, "
            "y sube tus documentos para que en cuanto arranque el sistema de oficina podamos continuar con tu candidatura."
        )
    return msg


LOCAL_LAGUNA = ["torreon", "torreon coahuila", "gomez palacio", "lerdo", "matamoros"]

from app.settings import AGE_DISQUALIFICATION_LIMIT as AGE_LIMIT_EXCLUSIVE
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


def age_disqualification_reply(age: int | None = None) -> str:
    from app.indexer import call_groq_with_system
    from app.persona_config import SYSTEM_PROMPT
    context = (
        f"El candidato indicó que tiene {age} años. " if age else ""
    )
    prompt = (
        f"{context}Aplica la regla de descalificación por edad del perfil de operador. "
        "Genera únicamente el mensaje de respuesta al candidato."
    )
    return call_groq_with_system(SYSTEM_PROMPT, prompt, temperature=0.1, max_tokens=120)


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
                # 3.3: marcar cierre suave por vencido-sin-trámite (bot deja de empujar funnel)
                facts["funnel.status"] = "vencido_sin_tramite"
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
    try:
        raw = call_groq_json(norm_message, _EXPIRATION_SYSTEM, temperature=0.0, model=_EXTRACTOR_MODEL)
        data = json.loads(raw)
        val = data.get("expiration_text")
        return str(val).strip() if val else None
    except Exception:
        return None

# Detect the topic of the last bot question for context-aware "si" interpretation
# Señal estructural de pregunta cuantitativa embebida: "cuántas necesita",
# "cuánto pagan", etc. OR-fallback para cuando TIPC no clasifica has_embedded_question.
_EMBEDDED_Q_SIGNAL = re.compile(
    r"(?:cuantos?|cuantas?|cuanto\s+es|cuanto\s+queda|cuanto\s+vale)\s+",
    re.IGNORECASE,
)

_TOPIC_APTO = re.compile(r"\bapto\b", re.IGNORECASE)
_TOPIC_LICENSE_VIGENTE = re.compile(
    r"\blicencia\b.{0,80}(?:\bvigente\b|\bvigencia\b|\bal\s+corriente\b)"
    r"|(?:\bvigente\b|\bvigencia\b).{0,80}\blicencia\b",
    re.IGNORECASE | re.DOTALL,
)
_TOPIC_LETTERS = re.compile(r"\bcartas?\s+laborales?\b", re.IGNORECASE)


def _extract_context_confirmation_facts(norm_message: str, last_bot_message: str, _turn_signals=None) -> dict[str, Any]:
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
    # "ya" de RECLAMO no es confirmación: "ya le habia dicho que 10 años".
    # Guarda estructural: bare "ya" nunca es reclamo; solo cuando va seguido de
    # texto puede serlo. TIPC clasifica la intención dentro de ese sub-caso.
    _ya_reclamo = False
    if t.startswith("ya "):
        if _turn_signals is not None:
            _ya_reclamo = _turn_signals.is_ya_reclamo
        else:
            try:
                from app.knowledge.turn_intent_classifier import classify_turn_intent
                _ya_reclamo = classify_turn_intent(norm_message).is_ya_reclamo
            except Exception:
                _ya_reclamo = False
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


def extract_current_turn_facts(message: str | None, last_bot_message: str | None = None, turn_signals=None) -> dict[str, Any]:
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

    if turn_signals is None:
        try:
            from app.knowledge.turn_intent_classifier import classify_turn_intent
            turn_signals = classify_turn_intent(raw)
        except Exception:
            from app.knowledge.turn_intent_classifier import TurnIntentSignals
            turn_signals = TurnIntentSignals()

    facts = extract_profile_facts_as_dict(raw, turn_signals=turn_signals)
    text = normalize_text(raw)

    # Context-aware: infer field from "si" when we know what was last asked
    if last_bot_message:
        for k, v in _extract_context_confirmation_facts(text, last_bot_message, _turn_signals=turn_signals).items():
            if k not in facts:
                facts[k] = v

        # Respuesta elíptica numérica: "10" / "10 años" tras pregunta de edad o experiencia.
        # Usa solo la última frase interrogativa del mensaje del bot para evitar
        # que el acuse previo ("registro 30 años de experiencia. ¿Cuántos años tiene?")
        # contamine el contexto de la pregunta real.
        last_norm = normalize_text(last_bot_message)
        # Extraer la última pregunta del mensaje del bot (texto del último "?" hacia atrás).
        _q_parts = re.split(r"[.!]", last_norm)
        _last_question = normalize_text(_q_parts[-1]) if _q_parts else last_norm

        _ya_reclamo = getattr(turn_signals, "is_ya_reclamo", False)
        _age_question = re.search(r"\bcuantos anos\b", _last_question) and "experiencia" not in _last_question
        if _age_question and ("candidate.age" not in facts or _ya_reclamo):
            try:
                raw = call_groq_json(text, _AGE_SYSTEM, temperature=0.0, model=_EXTRACTOR_MODEL)
                val = json.loads(raw).get("age")
                if val is not None:
                    facts["candidate.age"] = str(int(val))
            except Exception:
                pass

        if "experience.years" not in facts:
            if re.search(r"\bcuantos anos\b", _last_question) and "experiencia" in _last_question:
                try:
                    raw = call_groq_json(text, _EXPERIENCE_YEARS_SYSTEM, temperature=0.0, model=_EXTRACTOR_MODEL)
                    val = json.loads(raw).get("years")
                    if val:
                        facts["experience.years"] = str(val)
                except Exception:
                    pass

        # P0-1: solo llamar al extractor LLM si el candidato mencionó algo de vencimiento.
        # Sin esta guarda el modelo alucina "vencido" sobre mensajes vacíos de fechas.
        _expiry_hints = ("vence", "vencen", "vencimiento", "caduca", "caduco",
                         "se me acaba", "me queda", "año", "anos", "meses", "mes")
        _has_expiry_context = (
            getattr(turn_signals, "has_expiry_context", False)
            or any(h in text for h in _expiry_hints)
        )
        if _has_expiry_context:
            exp_text = _contextual_expiration_text(text)
            if exp_text:
                last_norm = normalize_text(last_bot_message)
                if "license.expiration_text" not in facts and "licencia" in last_norm and "vence" in last_norm:
                    facts["license.expiration_text"] = exp_text
                if "medical.apto_expiration_text" not in facts and "apto" in last_norm and "vence" in last_norm:
                    facts["medical.apto_expiration_text"] = exp_text

        # 3.1: extracción de nombre cuando last_bot lo pidió
        _last_norm_name = normalize_text(last_bot_message)
        _asks_name = "nombre" in _last_norm_name and "?" in last_bot_message
        if _asks_name and "candidate.name" not in facts:
            _name_patterns = [
                re.search(r"\bme\s+llamo\s+([A-ZÁÉÍÓÚÜÑa-záéíóúüñ]{2,}(?:\s+[A-ZÁÉÍÓÚÜÑa-záéíóúüñ]{2,})?)", raw, re.IGNORECASE),
                re.search(r"\bsoy\s+([A-ZÁÉÍÓÚÜÑa-záéíóúüñ]{2,}(?:\s+[A-ZÁÉÍÓÚÜÑa-záéíóúüñ]{2,})?)", raw, re.IGNORECASE),
                re.search(r"\bmi\s+nombre\s+es\s+([A-ZÁÉÍÓÚÜÑa-záéíóúüñ]{2,}(?:\s+[A-ZÁÉÍÓÚÜÑa-záéíóúüñ]{2,})?)", raw, re.IGNORECASE),
            ]
            _name_skip = {
                "si", "no", "nel", "nop", "ok", "va", "dale", "sale", "claro", "exacto",
                "hola", "ola", "buenas", "buenos", "buen", "hey", "gracias", "perfecto",
                "listo", "entendido", "correcto", "anotado", "registrado",
                "full", "sencillo", "tracto", "torton", "rabon",
            }
            for _nm in _name_patterns:
                if _nm:
                    _cand = _nm.group(1).strip().title()
                    if _cand.lower() not in _name_skip and len(_cand) >= 3:
                        facts["candidate.name"] = _cand
                    break
            else:
                # Respuesta corta sin verbo = nombre directo (ej: "Juan García")
                _words = raw.strip().split()
                _candidate_name = raw.strip().title()
                if (1 <= len(_words) <= 3
                        and all(w[0].isupper() or w[0].isalpha() for w in _words if w)
                        and _candidate_name.lower() not in _name_skip
                        and len(_candidate_name) >= 3):
                    facts["candidate.name"] = _candidate_name

        # BUG-2: "No" bare como respuesta directa a pregunta de cartas/documentos
        _last_norm_docs = normalize_text(last_bot_message)
        _asks_cartas = any(t in _last_norm_docs for t in ("cartas", "membretadas", "documentos laborales", "documento laboral"))
        _bare_negation = text in {"no", "nop", "nel", "nope", "para nada", "tampoco", "negativo", "no tengo", "no cuento"}
        if _asks_cartas and _bare_negation and "documents.proof" not in facts:
            facts["documents.proof"] = "ninguno"

        # BUG-3: "al mismo tiempo / igual / los dos" tras pregunta de apto → heredar vencimiento de licencia
        _last_norm_apto = normalize_text(last_bot_message)
        _asks_apto = "apto" in _last_norm_apto and ("vence" in _last_norm_apto or "vigencia" in _last_norm_apto)
        _same_as_hints = ("igual", "mismo", "los dos", "ambos", "los 2", "tambien", "también",
                          "al mismo tiempo", "igual que", "igualmente", "los dos vencen")
        _says_same = any(h in text for h in _same_as_hints)
        if _asks_apto and _says_same and "medical.apto_expiration_text" not in facts:
            # Heredar desde licencia si ya está conocida
            _lic_exp = (merged_facts or {}).get("license.expiration_text") or facts.get("license.expiration_text")
            if _lic_exp:
                facts["medical.apto_expiration_text"] = _lic_exp

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
    "me interesa la vancate",
    "me interesa la bacante",
    "me interesa la bakante",
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


def has_embedded_business_question(message: str | None, turn_signals=None) -> bool:
    """True si el mensaje contiene una pregunta de negocio embebida (sin "?").

    Consume turn_signals.has_embedded_question cuando está disponible.
    OR-fallback: _EMBEDDED_Q_SIGNAL cubre casos que TIPC puede subestimar
    (e.g. "cuántas necesita?").
    Sin turn_signals: llama al TIPC internamente (compat tests).
    """
    text = normalize_text(message or "")
    if not text:
        return False
    if _EMBEDDED_Q_SIGNAL.search(text):
        return True
    if turn_signals is not None:
        return bool(turn_signals.has_embedded_question)
    try:
        from app.knowledge.turn_intent_classifier import classify_turn_intent
        return classify_turn_intent(message or "").has_embedded_question
    except Exception:
        return False


def should_prioritize_current_turn(message: str | None, last_bot_message: str | None = None) -> bool:
    """Evita que RAG/memoria pisen una respuesta clara del candidato."""
    if is_question(message) or has_embedded_business_question(message):
        return False
    return has_current_turn_profile_signal(message, last_bot_message)


def next_question_from_missing_facts(facts: dict[str, Any]) -> str:
    if not facts.get("candidate.name"):
        return "¿Me podría decir su nombre, por favor?"
    if not facts.get("candidate.city"):
        return "Gracias. ¿En qué ciudad se encuentra actualmente?"
    if not facts.get("candidate.age"):
        return "Gracias. ¿Cuántos años tiene?"
    if is_age_disqualified(facts):
        return age_disqualification_reply(_to_int(facts.get("candidate.age")))
    if not facts.get("experience.vehicle_type"):
        # 2.4: condición por licencia si ya se conoce (B→sencillo, E→ambas)
        cat = (facts.get("license.category") or "").upper()
        if cat == "B":
            return (
                "Con licencia tipo B la vacante disponible es de sencillo. "
                "¿Le interesa una vacante de operador sencillo?"
            )
        elif cat == "E":
            return "¿Le interesa una vacante de tracto full o de sencillo?"
        else:
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
        # 2.5: documento por residencia (local ZM Laguna acepta IMSS; foráneo exige membretadas)
        is_local = facts.get("location.is_local_laguna") == "true" or (
            normalize_text(facts.get("candidate.city") or "") in LOCAL_LAGUNA
        )
        _proof = facts.get("documents.proof")
        # P0-2: candidato negó tener cartas — ofrecer alternativa o cerrar sin loop
        if _proof == "ninguno":
            if is_local:
                return "¿Cuenta con su documento de semanas cotizadas del IMSS?"
            else:
                return (
                    "Para candidatos foráneos necesitamos 2 cartas laborales membretadas. "
                    "Si consigue ese documento, con gusto retomamos. Lo dejo anotado para que "
                    "Capital Humano le indique opciones al contactarle."
                )
        if is_local:
            return "¿Cuenta con cartas laborales o semanas cotizadas del IMSS?"
        else:
            return "¿Cuenta con 2 cartas laborales membretadas de sus empleos anteriores?"
    return _profile_complete_closing()


def next_prehandoff_question(branch: str, facts: dict[str, Any]) -> str | None:
    """Retorna la pregunta de verificación previa al handoff, o None si el dato mínimo ya está.

    branch: 'escuelita' | 'cecati' | 'b1' | 'reingreso'
    facts: dict canónico de facts del lead (group.key → value)
    """
    lic = str(facts.get("license.category") or "").upper()
    has_be = lic in {"B", "E"}
    has_tramite = (
        facts.get("license.tramite_comprobante") == "true"
        or facts.get("medical.tramite_comprobante") == "true"
    )

    if branch in {"escuelita", "cecati"}:
        if has_be or has_tramite:
            return None  # dato mínimo confirmado → handoff puede proceder
        return (
            "Para considerar su candidatura, necesitamos saber si cuenta con "
            "licencia federal tipo B o E vigente (o comprobante de renovación). "
            "¿Tiene licencia federal B o E?"
        )

    if branch == "b1":
        if not facts.get("experience.vehicle_type"):
            return "Para las vacantes con ruta B1/EUA, ¿su experiencia es en tracto full o sencillo?"
        if not has_be or not facts.get("license.expiration_text"):
            return (
                "Para las vacantes B1/EUA necesitamos confirmar que su licencia federal esté vigente. "
                "¿Qué tipo de licencia federal tiene y cuándo vence?"
            )
        if not facts.get("medical.apto_expiration_text"):
            return "¿Cuándo vence su apto médico?"
        return None  # todos los datos confirmados

    if branch == "reingreso":
        if not facts.get("reingreso.tipo_vacante"):
            return (
                "Gracias por contactarnos de nuevo. ¿Busca regresar como operador de tracto, "
                "o tiene en mente otro tipo de vacante?"
            )
        return None

    return None


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
        return age_disqualification_reply(_to_int(facts.get("candidate.age")))

    # Frases de confirmación naturales por tipo de dato (P2-5)
    confirms = []
    if current.get("candidate.city"):
        confirms.append(f"Anotado, {current['candidate.city']}.")
    if current.get("candidate.age"):
        confirms.append(f"Edad anotada, continuamos con el proceso.")
    vt = current.get("experience.vehicle_type")
    if vt == "sencillo":
        confirms.append("Entendido, experiencia en camión sencillo.")
    elif vt == "full":
        # Solo full confirma tracto full; jerga (quinta rueda/tráiler) nunca
        # llega aquí como vehicle_type y no debe afirmarse como full.
        confirms.append("Entendido, operador de tracto full.")
    if current.get("license.category"):
        confirms.append(f"Queda anotado: licencia federal tipo {current['license.category']}.")
    _lic_exp = current.get("license.expiration_text")
    if _lic_exp and _lic_exp != "vencido":
        confirms.append(f"Tomamos nota, licencia vigente ({_lic_exp}).")
    _apto_exp = current.get("medical.apto_expiration_text")
    if _apto_exp and _apto_exp != "vencido":
        confirms.append(f"Bien, apto médico vigente ({_apto_exp}).")
    if current.get("medical.apto_status") == "vigente":
        if not _apto_exp:
            confirms.append("Bien, apto médico vigente.")
    if current.get("experience.years"):
        confirms.append(f"Esa experiencia es valiosa. Con ese perfil nos interesa conocerle.")
    if current.get("documents.labor_letters") == "sí" or current.get("documents.proof") in {"cartas", "semanas_imss"}:
        confirms.append("Listo, documentos anotados.")
    if current.get("documents.general_status") == "vigente":
        confirms.append("Documentación vigente, anotado.")

    if confirms:
        prefix = " ".join(confirms)
    else:
        prefix = "Gracias, lo dejo registrado."

    return _join_ack_and_question(prefix, next_question_from_missing_facts(facts))
