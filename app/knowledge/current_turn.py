import re
import unicodedata
from typing import Any


LOCAL_LAGUNA = ["torreon", "torreon coahuila", "gomez palacio", "lerdo", "matamoros"]


def normalize_text(text: str | None) -> str:
    value = (text or "").strip().lower()
    value = unicodedata.normalize("NFD", value)
    value = "".join(ch for ch in value if unicodedata.category(ch) != "Mn")
    value = re.sub(r"[^a-z0-9\s,+.-]", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def is_question(text: str | None) -> bool:
    raw = text or ""
    norm = normalize_text(raw)
    if "?" in raw or "¿" in raw:
        return True
    return bool(re.match(r"^(cuanto|cuanta|cuantos|cuantas|cuando|donde|que|como|cual|pagan|tienen|hay|manejan)\b", norm))


def extract_current_turn_facts(message: str | None) -> dict[str, Any]:
    """
    Extrae hechos determinísticos del mensaje actual.

    Regla de arquitectura: los hechos del turno actual tienen prioridad sobre memoria/RAG.
    Esta capa cubre faltas comunes y lenguaje natural corto de candidatos traileros.
    """
    raw = (message or "").strip()
    text = normalize_text(raw)
    facts: dict[str, Any] = {}

    if not text:
        return facts

    age_match = re.search(r"\b(1[8-9]|[2-6][0-9]|7[0-5])\s*(anos|anios|años)?\b", text)
    if age_match:
        facts["candidate.age"] = int(age_match.group(1))

    # Ciudad con patrones frecuentes.
    city_patterns = [
        r"\b(?:soy de|soi de|vivo en|vivo por|estoy en|ando en|radico en|resido en|me ubico en)\s+([a-z\s]+?)(?:\s+y\b|,|\.|$)",
        r"\ben\s+(torreon|gomez palacio|lerdo|matamoros|san luis potosi|slp|monterrey|saltillo|durango)\b",
    ]
    for pattern in city_patterns:
        match = re.search(pattern, text)
        if match:
            city = match.group(1).strip()
            city = {"slp": "San Luis Potosí", "torreon": "Torreón", "gomez palacio": "Gómez Palacio"}.get(city, city.title())
            facts["candidate.city"] = city
            facts["location.is_local_laguna"] = normalize_text(city) in LOCAL_LAGUNA
            break

    license_match = re.search(r"\b(?:licencia\s*)?(?:tipo\s*)?([abe])\b", text)
    if license_match and ("licencia" in text or "tipo" in text):
        facts["license.category"] = license_match.group(1).upper()
        facts["license.status"] = "vigente" if any(word in text for word in ["vigente", "todo vigente", "vigentes"]) else "mencionada"

    if any(phrase in text for phrase in ["todo vigente", "todos vigentes", "documentacion vigente", "documentos vigentes", "papeles vigentes"]):
        facts["documents.general_status"] = "vigente"
        facts["license.status"] = "vigente"
        facts["medical.apto_status"] = "vigente"

    if "apto" in text or "medico" in text:
        if any(word in text for word in ["vigente", "si", "sí", "tengo", "cuento"]):
            facts["medical.apto_status"] = "vigente"
        elif any(word in text for word in ["vencido", "no tengo", "no cuento"]):
            facts["medical.apto_status"] = "no_vigente"

    if "carta" in text or "cartas" in text or "laboral" in text or "laborales" in text:
        if any(word in text for word in ["tengo", "cuento", "si", "sí"]):
            facts["documents.labor_letters"] = "sí"
        elif "no" in text:
            facts["documents.labor_letters"] = "no"

    if any(term in text for term in ["quinta", "quinta rueda", "full", "tracto", "trailer", "trailer"]):
        if any(word in text for word in ["si", "sí", "tengo", "manejo", "manejando", "experiencia"]):
            facts["experience.fifth_wheel"] = "sí"

    years_match = re.search(r"\b(\d{1,2})\s*(anos|anios|años|año)\b", text)
    if years_match and any(term in text for term in ["experiencia", "manej", "quinta", "full", "tracto"]):
        facts["experience.years"] = years_match.group(1)

    if any(phrase in text for phrase in ["me interesa", "si me interesa", "sí me interesa", "me agrada", "si jalo", "jalo"]):
        facts["candidate.vacancy_accepted"] = "sí"

    if any(phrase in text for phrase in ["voy manejando", "vengo manejando", "ando manejando", "al rato", "mas tarde", "más tarde"]):
        facts["candidate.availability_status"] = "en_ruta_o_no_disponible_ahora"

    if any(phrase in text for phrase in ["cuanto pagan", "cuanto pagan", "pago", "sueldo", "compensacion", "kilometro", "km"]):
        facts["interest.payment"] = "asked"

    if any(phrase in text for phrase in ["que rutas", "rutas tienen", "bases", "cedis", "monterrey"]):
        facts["interest.routes"] = "asked"

    return facts


def has_current_turn_profile_signal(message: str | None) -> bool:
    facts = extract_current_turn_facts(message)
    return any(
        key.startswith(("candidate.", "license.", "medical.", "documents.", "experience.", "location."))
        for key in facts
    )


def should_prioritize_current_turn(message: str | None) -> bool:
    """Evita que RAG/memoria pisen una respuesta clara del candidato."""
    if is_question(message):
        return False
    return has_current_turn_profile_signal(message)


def next_question_from_missing_facts(facts: dict[str, Any]) -> str:
    if not facts.get("candidate.city"):
        return "Para continuar, ¿en qué ciudad te encuentras actualmente?"
    if not facts.get("license.category") and not facts.get("license.status"):
        return "Gracias. ¿Qué tipo de licencia federal tienes y está vigente?"
    if not facts.get("experience.fifth_wheel") and not facts.get("experience.years"):
        return "Perfecto. ¿Cuántos años de experiencia tienes manejando quinta rueda o full?"
    if not facts.get("medical.apto_status"):
        return "Gracias. ¿Tu apto médico está vigente?"
    if not facts.get("documents.labor_letters"):
        return "¿Cuentas con cartas laborales?"
    return "Perfecto, con esto tu perfil queda listo para revisión de Capital Humano."


def build_current_turn_ack(message: str | None, merged_facts: dict[str, Any] | None = None) -> str:
    facts = {**(merged_facts or {}), **extract_current_turn_facts(message)}
    detected = []
    if facts.get("candidate.city"):
        detected.append(f"ciudad {facts['candidate.city']}")
    if facts.get("license.category"):
        detected.append(f"licencia tipo {facts['license.category']}")
    if facts.get("medical.apto_status") == "vigente":
        detected.append("apto médico vigente")
    if facts.get("documents.general_status") == "vigente":
        detected.append("documentación vigente")
    if facts.get("documents.labor_letters") == "sí":
        detected.append("cartas laborales")
    if facts.get("candidate.age"):
        detected.append(f"{facts['candidate.age']} años")
    if facts.get("experience.years"):
        detected.append(f"{facts['experience.years']} años de experiencia")
    if facts.get("experience.fifth_wheel") == "sí":
        detected.append("experiencia en quinta rueda/full")

    if detected:
        prefix = "Perfecto, registro " + ", ".join(detected) + "."
    else:
        prefix = "Perfecto, lo dejo registrado."

    return f"{prefix} {next_question_from_missing_facts(facts)}"
