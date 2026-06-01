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
    ("torreón", "Torreón"),
    ("monterrey", "Monterrey"),
    ("mty", "Monterrey"),
    ("durango", "Durango"),
    ("queretaro", "Querétaro"),
    ("querétaro", "Querétaro"),
    ("cd juarez", "Ciudad Juárez"),
    ("cd. juarez", "Ciudad Juárez"),
    ("ciudad juarez", "Ciudad Juárez"),
    ("juarez", "Ciudad Juárez"),
    ("juárez", "Ciudad Juárez"),
    ("manzanillo", "Manzanillo"),
    ("rio bravo", "Río Bravo"),
    ("río bravo", "Río Bravo"),
    ("saltillo", "Saltillo"),
    ("leon", "León"),
    ("león", "León"),
]


def _fact(fact_group: str, fact_key: str, fact_value: str, confidence: float = 0.8) -> dict[str, Any]:
    return {
        "fact_group": fact_group,
        "fact_key": fact_key,
        "fact_value": fact_value,
        "confidence": confidence,
    }


def _extract_city(message: str, text: str) -> dict[str, Any] | None:
    # Prefer explicit known aliases. This is intentionally conservative.
    for alias, canonical in KNOWN_CITY_ALIASES:
        if alias in text:
            return _fact("candidate", "city", canonical, 0.9)

    # Fallback for "resido en X" / "vivo en X" with short city fragment.
    match = re.search(
        r"\b(?:resido|radico|vivo|soy)\s+(?:en|de)\s+([a-záéíóúñ .]{3,40})",
        message.lower(),
        flags=re.IGNORECASE,
    )
    if match:
        raw_city = re.split(r"\b(?:y|con|tengo|licencia|apto|cartas)\b", match.group(1))[0].strip(" .,")
        if raw_city:
            return _fact("candidate", "city", raw_city.title(), 0.65)
    return None


def extract_profile_facts(message: str, intent: str | None = None) -> list[dict[str, Any]]:
    """Extract conservative profile facts from short recruiting messages.

    This extractor is not a document validator. It only records what the candidate
    says, so Capital Humano can validate later.
    """
    text = normalize_text(message)
    facts: list[dict[str, Any]] = []

    city = _extract_city(message, text)
    if city:
        facts.append(city)

    # License category: "licencia tipo E", "tipo E", "B y E".
    if "licencia" in text or "lic" in text or "tipo" in text:
        cats = sorted(set(re.findall(r"\btipo\s*([a-e])\b|\blic(?:encia)?\s*(?:tipo)?\s*([a-e])\b", text)))
        flat = [item for tup in cats for item in tup if item]
        if flat:
            facts.append(_fact("license", "category", ",".join(sorted(set(c.upper() for c in flat))), 0.85))
        elif re.search(r"\b[by]\s*(?:y|e|/)\s*e\b", text):
            facts.append(_fact("license", "category", "B,E", 0.75))

    # Compact "es tipo E" after a license question.
    match_tipo = re.search(r"\b(?:es|tengo|traigo)\s+(?:licencia\s+)?tipo\s*([a-e])\b", text)
    if match_tipo:
        facts.append(_fact("license", "category", match_tipo.group(1).upper(), 0.9))

    # Expiration/vigency.
    if any(term in text for term in ("vigente", "vigentes", "en regla", "todo vigente", "toda mi informacion")):
        if any(term in text for term in ("licencia", "lic", "tipo e", "tipo b")):
            facts.append(_fact("license", "status", "vigente", 0.8))
        if "apto" in text or "toda mi informacion" in text or "todo vigente" in text:
            facts.append(_fact("medical", "apto_status", "vigente", 0.8))
        if "cartas" in text:
            facts.append(_fact("documents", "labor_letters_status", "available", 0.8))

    if "vence" in text or "vencen" in text or "vencimiento" in text:
        if "1 año" in text or "un año" in text:
            facts.append(_fact("license", "expires_in", "1 año", 0.75))
            facts.append(_fact("medical", "apto_expires_in", "1 año", 0.65))
        elif "2 meses" in text or "dos meses" in text:
            facts.append(_fact("license", "expires_in", "2 meses", 0.65))
            facts.append(_fact("medical", "apto_expires_in", "2 meses", 0.65))

    if any(term in text for term in ("vencido", "vencida")):
        if "lic" in text or "licencia" in text:
            facts.append(_fact("license", "status", "vencida", 0.85))
        if "apto" in text:
            facts.append(_fact("medical", "apto_status", "vencido", 0.85))

    # Experience.
    years_match = re.search(r"\b(\d{1,2})\s*(?:anos|años)\b", text)
    if years_match and any(term in text for term in ("manejando", "manejo", "experiencia", "full", "quinta", "5ta")):
        facts.append(_fact("experience", "years", years_match.group(1), 0.8))

    if any(term in text for term in ("full", "quinta rueda", "5ta rueda", "quinta", "kinta")):
        facts.append(_fact("experience", "fifth_wheel", "sí", 0.8))

    if any(term in text for term in ("carretera mexicana", "republica", "república", "foraneo", "foráneo")):
        facts.append(_fact("experience", "carretera_mexicana", "sí", 0.75))

    if "cartas" in text and any(term in text for term in ("si", "sí", "cuento", "tengo")):
        facts.append(_fact("documents", "labor_letters_status", "available", 0.8))

    # Document availability / delayed send.
    if any(term in text for term in ("lo tengo", "tengo todo", "si tengo", "sí tengo", "cuento con todo", "toda mi informacion")):
        facts.append(_fact("documents", "availability_claim", "candidate_says_available", 0.7))

    if any(term in text for term in ("en unas horas", "yo le aviso", "luego se los mando", "luego los mando", "dame oportunidad", "deme oportunidad", "conseguirlos", "vengo manejando")):
        facts.append(_fact("documents", "submission_status", "pending_candidate_will_send", 0.85))
        facts.append(_fact("candidate", "availability_status", "en_ruta_o_no_disponible_ahora", 0.75))

    # Candidate likes/accepts moving forward.
    if any(term in text for term in ("me agrada", "si me interesa", "sí me interesa", "me interesa", "seguimos", "adelante")):
        facts.append(_fact("candidate", "vacancy_accepted", "sí", 0.75))

    # Deduplicate by group/key, last wins.
    dedup: dict[tuple[str, str], dict[str, Any]] = {}
    for fact in facts:
        dedup[(fact["fact_group"], fact["fact_key"])] = fact
    return list(dedup.values())


def missing_profile_fields(active_facts: dict[str, Any] | None) -> list[str]:
    facts = active_facts or {}
    required = [
        ("candidate.city", "ciudad"),
        ("license.category", "tipo de licencia"),
        ("license.status", "vigencia de licencia"),
        ("medical.apto_status", "apto médico"),
        ("experience.fifth_wheel", "experiencia quinta rueda/full"),
        ("documents.labor_letters_status", "cartas laborales"),
    ]
    return [label for key, label in required if key not in facts]

# ---------------------------------------------------------------------------
# Current-turn extraction hotfix.
# Rule: explicit candidate facts in the current message override stale memory/RAG.
# Examples:
# - "apto medico vence en 2 años" => apto vigente, not pending_update.
# - "tengo 33 aos" => age 33.
# - "7 años de experiencia en full" => experience.years = 7, fifth_wheel = sí.
# ---------------------------------------------------------------------------

if "_CURRENT_TURN_PROFILE_HOTFIX_APPLIED" not in globals():
    _CURRENT_TURN_PROFILE_HOTFIX_APPLIED = True
    _base_extract_profile_facts = extract_profile_facts

    def _hotfix_fact(fact_group: str, fact_key: str, fact_value: str, confidence: float = 0.9) -> dict[str, Any]:
        return {
            "fact_group": fact_group,
            "fact_key": fact_key,
            "fact_value": fact_value,
            "confidence": confidence,
        }

    def _upsert_fact_local(facts: list[dict[str, Any]], fact: dict[str, Any]) -> None:
        for idx, item in enumerate(facts):
            if item.get("fact_group") == fact.get("fact_group") and item.get("fact_key") == fact.get("fact_key"):
                if float(fact.get("confidence") or 0) >= float(item.get("confidence") or 0):
                    facts[idx] = fact
                return
        facts.append(fact)

    def extract_profile_facts(message: str, intent: str | None = None) -> list[dict[str, Any]]:
        facts = list(_base_extract_profile_facts(message, intent))
        text = normalize_text(message)

        # Normalize common typo: "aos" -> "años/anios" equivalent.
        text_for_numbers = text.replace(" aos", " anos").replace(" ao ", " ano ")

        # License category.
        license_match = re.search(r"\b(?:licencia\s*)?(?:tipo\s*)?([abe])\b", text_for_numbers)
        if license_match and ("licencia" in text_for_numbers or "tipo" in text_for_numbers):
            _upsert_fact_local(facts, _hotfix_fact("license", "category", license_match.group(1).upper(), 0.92))

        # License validity: "se vence en 3 años" means valid.
        if "licencia" in text_for_numbers and re.search(r"\b(?:vence|vencen|se vence|vigente)\b", text_for_numbers):
            if re.search(r"\bvence\s+en\s+\d+\s+(?:ano|anos|anio|anios)\b", text_for_numbers) or "vigente" in text_for_numbers:
                _upsert_fact_local(facts, _hotfix_fact("license", "status", "vigente", 0.92))

        # Apto medico validity. Any future expiration in years is valid.
        if "apto" in text_for_numbers or "medico" in text_for_numbers:
            if (
                "vigente" in text_for_numbers
                or re.search(r"\bvence\s+en\s+\d+\s+(?:ano|anos|anio|anios)\b", text_for_numbers)
                or "no le veo el problema" in text_for_numbers
            ):
                _upsert_fact_local(facts, _hotfix_fact("medical", "apto_status", "vigente", 0.95))
                # Compatibility with older code that accidentally uses singular "document".
                _upsert_fact_local(facts, _hotfix_fact("document", "apto_status", "vigente", 0.95))

        apto_exp = re.search(r"\bapto(?:\s+medico)?\s+(?:vence|se vence)\s+en\s+(\d+)\s+(?:ano|anos|anio|anios)\b", text_for_numbers)
        if apto_exp:
            _upsert_fact_local(facts, _hotfix_fact("medical", "apto_expiration_text", f"vence en {apto_exp.group(1)} años", 0.9))

        # Documents / labor letters.
        if ("carta" in text_for_numbers or "cartas" in text_for_numbers or "laboral" in text_for_numbers) and not "no tengo" in text_for_numbers:
            _upsert_fact_local(facts, _hotfix_fact("documents", "labor_letters", "sí", 0.9))

        # City.
        if "san luis potosi" in text_for_numbers or "slp" in text_for_numbers:
            _upsert_fact_local(facts, _hotfix_fact("candidate", "city", "San Luis Potosí", 0.95))

        # Age.
        age_match = re.search(r"\b(?:tengo|edad(?:\s+es\s+de)?|soy de .*? tengo)?\s*(1[8-9]|[2-6][0-9]|7[0-5])\s*(?:ano|anos|anio|anios)?\b", text_for_numbers)
        if age_match:
            _upsert_fact_local(facts, _hotfix_fact("candidate", "age", age_match.group(1), 0.88))

        # Full / fifth wheel experience.
        years_match = re.search(r"\b(\d{1,2})\s*(?:ano|anos|anio|anios)\s+(?:de\s+)?experiencia\b", text_for_numbers)
        if not years_match:
            years_match = re.search(r"\bcon\s+(\d{1,2})\s*(?:ano|anos|anio|anios)\b", text_for_numbers)

        if years_match and any(term in text_for_numbers for term in ("full", "quinta", "quinta rueda", "tracto")):
            _upsert_fact_local(facts, _hotfix_fact("experience", "years", years_match.group(1), 0.92))
            _upsert_fact_local(facts, _hotfix_fact("experience", "fifth_wheel", "sí", 0.92))

        if any(term in text_for_numbers for term in ("full", "quinta", "quinta rueda", "tracto")):
            _upsert_fact_local(facts, _hotfix_fact("experience", "fifth_wheel", "sí", 0.85))

        return facts
