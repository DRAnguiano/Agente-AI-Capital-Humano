import re
from typing import Any

from app.knowledge.text_normalizer import normalize_text


LOCAL_LAGUNA = ["torreon", "torreon coahuila", "gomez palacio", "lerdo", "matamoros"]


def is_question(text: str | None) -> bool:
    raw = text or ""
    norm = normalize_text(raw)
    if "?" in raw or "¿" in raw:
        return True
    return bool(re.match(r"^(cuanto|cuanta|cuantos|cuantas|cuando|donde|que|como|cual|pagan|tienen|hay|manejan)\b", norm))


def extract_current_turn_facts(message: str | None) -> dict[str, Any]:
    """Dict view of profile facts for the debounce guard in tasks_chatwoot.

    Delegates extraction to profile_extractor (single source of truth) and adds
    the debounce-specific fields: interest.payment, interest.routes,
    location.is_local_laguna.
    """
    from app.lead_memory.profile_extractor import extract_profile_facts_as_dict

    raw = (message or "").strip()
    if not raw:
        return {}

    facts = extract_profile_facts_as_dict(raw)
    text = normalize_text(raw)

    # Fields only needed by the debounce guard, not persisted to lead_memory.
    if any(t in text for t in ("cuanto pagan", "pago", "sueldo", "compensacion", "kilometro", "km")):
        facts["interest.payment"] = "asked"
    if any(t in text for t in ("que rutas", "rutas tienen", "bases", "cedis")):
        facts["interest.routes"] = "asked"

    city_norm = normalize_text(facts.get("candidate.city") or "")
    facts["location.is_local_laguna"] = city_norm in LOCAL_LAGUNA

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
