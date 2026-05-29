from __future__ import annotations

import re
from typing import Any

from app.knowledge.text_normalizer import normalize_text

KNOWN_CITY_ALIASES: list[tuple[str, str]] = [
    ("san luis potosi", "San Luis Potosí"),
    ("slp", "San Luis Potosí"),
    ("nuevo laredo", "Nuevo Laredo"),
    ("nvo laredo", "Nuevo Laredo"),
    ("torreon", "Torreón"),
    ("gomez palacio", "Gómez Palacio"),
    ("lerdo", "Lerdo"),
    ("monterrey", "Monterrey"),
    ("mty", "Monterrey"),
    ("durango", "Durango"),
    ("queretaro", "Querétaro"),
    ("cd juarez", "Ciudad Juárez"),
    ("ciudad juarez", "Ciudad Juárez"),
    ("juarez", "Ciudad Juárez"),
    ("manzanillo", "Manzanillo"),
    ("saltillo", "Saltillo"),
]


def _fact(fact_group: str, fact_key: str, fact_value: str, confidence: float = 0.8) -> dict[str, Any]:
    return {"fact_group": fact_group, "fact_key": fact_key, "fact_value": fact_value, "confidence": confidence}


def _extract_city(message: str, text: str) -> dict[str, Any] | None:
    for alias, canonical in KNOWN_CITY_ALIASES:
        if alias in text:
            return _fact("candidate", "city", canonical, 0.9)

    match = re.search(r"\b(?:resido|radico|vivo|soy|estoy)\s+(?:en|de)\s+([a-záéíóúñ .]{3,40})", message.lower(), flags=re.IGNORECASE)
    if match:
        raw_city = re.split(r"\b(?:y|con|tengo|licencia|apto|cartas)\b", match.group(1))[0].strip(" .,")
        if raw_city:
            return _fact("candidate", "city", raw_city.title(), 0.65)
    return None


def extract_profile_facts(message: str, intent: str | None = None) -> list[dict[str, Any]]:
    text = normalize_text(message)
    facts: list[dict[str, Any]] = []

    city = _extract_city(message, text)
    if city:
        facts.append(city)

    if "licencia" in text or "lic" in text or "tipo" in text:
        cats = re.findall(r"\btipo\s*([a-e])\b|\blic(?:encia)?\s*(?:tipo)?\s*([a-e])\b", text)
        flat = [item for tup in cats for item in tup if item]
        if flat:
            facts.append(_fact("license", "category", ",".join(sorted(set(c.upper() for c in flat))), 0.85))
        elif re.search(r"\b[by]\s*(?:y|e|/)\s*e\b", text):
            facts.append(_fact("license", "category", "B,E", 0.75))

    if any(term in text for term in ("vigente", "vigentes", "en regla", "todo vigente", "toda mi informacion")):
        facts.append(_fact("documents", "general_status", "vigente", 0.8))
        if any(term in text for term in ("licencia", "lic", "tipo e", "tipo b", "todo vigente")):
            facts.append(_fact("license", "status", "vigente", 0.8))
        if "apto" in text or "todo vigente" in text or "toda mi informacion" in text:
            facts.append(_fact("medical", "apto_status", "vigente", 0.8))

    if "carta" in text or "cartas" in text:
        if any(term in text for term in ("tengo", "cuento", "si", "sí")):
            facts.append(_fact("documents", "labor_letters", "sí", 0.82))
        elif "no" in text:
            facts.append(_fact("documents", "labor_letters", "no", 0.75))

    age = re.search(r"\b(1[8-9]|[2-6][0-9]|7[0-5])\s*(?:anos|anios|años)?\b", text)
    if age:
        facts.append(_fact("candidate", "age", age.group(1), 0.8))

    years = re.search(r"\b(\d{1,2})\s*(?:anos|anios|años|año)\b", text)
    if years and any(term in text for term in ("experiencia", "manej", "quinta", "full", "tracto")):
        facts.append(_fact("experience", "years", years.group(1), 0.8))

    if any(term in text for term in ("quinta", "quinta rueda", "full", "tracto")):
        if any(term in text for term in ("si", "sí", "tengo", "manejo", "manejando", "experiencia")):
            facts.append(_fact("experience", "fifth_wheel", "sí", 0.8))

    if any(term in text for term in ("me interesa", "si me interesa", "sí me interesa", "me agrada", "jalo")):
        facts.append(_fact("candidate", "vacancy_accepted", "sí", 0.8))

    if any(term in text for term in ("voy manejando", "vengo manejando", "ando manejando", "al rato", "mas tarde", "más tarde")):
        facts.append(_fact("candidate", "availability_status", "en_ruta_o_no_disponible_ahora", 0.75))

    if any(term in text for term in ("cuanto pagan", "cuánto pagan", "pago", "sueldo", "kilometro", "kilómetro", "km")):
        facts.append(_fact("interest", "payment", "asked", 0.8))

    return facts
