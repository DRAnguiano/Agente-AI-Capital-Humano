from __future__ import annotations

import re
from typing import Any

from app.knowledge.text_normalizer import normalize_text


# Geo fallback — used when Neo4j is unavailable.
# Multi-word aliases must precede any shorter alias they contain.
KNOWN_CITY_ALIASES: list[tuple[str, str]] = [
    ("nuevo laredo", "Nuevo Laredo"),
    ("nvo laredo", "Nuevo Laredo"),
    ("san luis potosi", "San Luis Potosí"),
    ("ciudad juarez", "Ciudad Juárez"),
    ("cd juarez", "Ciudad Juárez"),
    ("cd. juarez", "Ciudad Juárez"),
    ("gomez palacio", "Gómez Palacio"),
    ("gómez palacio", "Gómez Palacio"),
    ("rio bravo", "Río Bravo"),
    ("río bravo", "Río Bravo"),
    ("monterrey", "Monterrey"),
    ("monterey", "Monterrey"),
    ("mty", "Monterrey"),
    ("slp", "San Luis Potosí"),
    ("torreon", "Torreón"),
    ("torreón", "Torreón"),
    ("matehuala", "Matehuala"),
    ("durango", "Durango"),
    ("queretaro", "Querétaro"),
    ("querétaro", "Querétaro"),
    ("juarez", "Ciudad Juárez"),
    ("juárez", "Ciudad Juárez"),
    ("manzanillo", "Manzanillo"),
    ("saltillo", "Saltillo"),
    ("chihuahua", "Chihuahua"),
    ("culiacan", "Culiacán"),
    ("culiacán", "Culiacán"),
    ("leon gto", "León"),
    ("leon guanajuato", "León"),
]


def _fact(fact_group: str, fact_key: str, fact_value: str, confidence: float = 0.8) -> dict[str, Any]:
    return {
        "fact_group": fact_group,
        "fact_key": fact_key,
        "fact_value": fact_value,
        "confidence": confidence,
    }


def _extract_city(message: str, text: str) -> dict[str, Any] | None:
    # Skip complaint/question patterns that echo a city name without meaning it.
    if re.search(r"\bpor\s*qu[eé]\s+me\b|\bque\s+es\s+\w+\b|\bpara\s+qu[eé]\b", text):
        return None
    if re.search(r"\bme\s+dic[ei]\s+\w+", text):
        return None

    for alias, canonical in KNOWN_CITY_ALIASES:
        if alias in text:
            return _fact("candidate", "city", canonical, 0.9)

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

    Neo4j handles geo (city/state) and vehicle type at higher confidence.
    This extractor covers license, medical, experience, documents, age, and
    geo as a fallback when Neo4j is unavailable.
    """
    text_raw = normalize_text(message)
    # Normalize common "aos" typo so year patterns match consistently.
    text = text_raw.replace(" aos", " anos").replace(" ao ", " ano ")
    facts: list[dict[str, Any]] = []

    def upsert(fact_group: str, fact_key: str, fact_value: str, confidence: float = 0.9) -> None:
        for i, f in enumerate(facts):
            if f["fact_group"] == fact_group and f["fact_key"] == fact_key:
                if confidence >= f["confidence"]:
                    facts[i] = _fact(fact_group, fact_key, fact_value, confidence)
                return
        facts.append(_fact(fact_group, fact_key, fact_value, confidence))

    # ── City (geo fallback) ──────────────────────────────────────────────────
    city = _extract_city(message, text)
    if city:
        upsert(city["fact_group"], city["fact_key"], city["fact_value"], city["confidence"])

    # ── License category ─────────────────────────────────────────────────────
    if "licencia" in text or "lic" in text or "tipo" in text:
        cats = sorted(set(re.findall(r"\btipo\s*([a-e])\b|\blic(?:encia)?\s*(?:tipo)?\s*([a-e])\b", text)))
        flat = [c for tup in cats for c in tup if c]
        if flat:
            upsert("license", "category", ",".join(sorted(set(c.upper() for c in flat))), 0.85)
        elif re.search(r"\b[by]\s*(?:y|e|/)\s*e\b", text):
            upsert("license", "category", "B,E", 0.75)

    # "es/tengo tipo E" — explicit confirmation, higher confidence
    m = re.search(r"\b(?:es|tengo|traigo)\s+(?:licencia\s+)?tipo\s*([a-e])\b", text)
    if m:
        upsert("license", "category", m.group(1).upper(), 0.92)

    # General type letter when preceded by license keyword
    m = re.search(r"\b(?:licencia\s*)?(?:tipo\s*)?([abe])\b", text)
    if m and ("licencia" in text or "tipo" in text):
        upsert("license", "category", m.group(1).upper(), 0.92)

    # ── License validity ─────────────────────────────────────────────────────
    if any(t in text for t in ("vigente", "vigentes", "en regla", "todo vigente", "toda mi informacion")):
        if any(t in text for t in ("licencia", "lic", "tipo e", "tipo b")):
            upsert("license", "status", "vigente", 0.80)
        if any(t in text for t in ("apto", "toda mi informacion", "todo vigente")):
            upsert("medical", "apto_status", "vigente", 0.80)
        if "cartas" in text:
            upsert("documents", "labor_letters_status", "available", 0.80)

    # Future expiry = still valid
    if "licencia" in text and re.search(r"\b(?:vence|vencen|se vence)\b", text):
        if re.search(r"\bvence\s+en\s+\d+\s+(?:ano|anos|anio|anios)\b", text):
            upsert("license", "status", "vigente", 0.92)

    if any(t in text for t in ("vence", "vencen", "vencimiento")):
        if any(t in text for t in ("1 ano", "un ano", "1 año", "un año")):
            upsert("license", "expires_in", "1 año", 0.75)
            upsert("medical", "apto_expires_in", "1 año", 0.65)
        elif any(t in text for t in ("2 meses", "dos meses")):
            upsert("license", "expires_in", "2 meses", 0.65)
            upsert("medical", "apto_expires_in", "2 meses", 0.65)

    if any(t in text for t in ("vencido", "vencida")):
        if any(t in text for t in ("lic", "licencia")):
            upsert("license", "status", "vencida", 0.85)
        if "apto" in text:
            upsert("medical", "apto_status", "vencido", 0.85)

    # ── Apto médico ──────────────────────────────────────────────────────────
    if "apto" in text or "medico" in text:
        if (
            "vigente" in text
            or re.search(r"\bvence\s+en\s+\d+\s+(?:ano|anos|anio|anios)\b", text)
            or "no le veo el problema" in text
        ):
            upsert("medical", "apto_status", "vigente", 0.95)
            upsert("document", "apto_status", "vigente", 0.95)

    m = re.search(
        r"\bapto(?:\s+medico)?\s+(?:vence|se vence)\s+en\s+(\d+)\s+(?:ano|anos|anio|anios)\b", text
    )
    if m:
        upsert("medical", "apto_expiration_text", f"vence en {m.group(1)} años", 0.90)

    # ── "ambas / los dos" + expiry → apply to license AND apto ───────────────
    ambas = re.search(
        r"\b(?:ambas?|los dos|las dos|ambos)\b.*?\bvencen?\s+en\s+(\d+)\s+(mes|meses|ano|anos|anio|anios)\b",
        text,
    ) or re.search(
        r"\bvencen?\s+en\s+(\d+)\s+(mes|meses|ano|anos|anio|anios)\b.*?\b(?:ambas?|los dos|las dos|ambos)\b",
        text,
    )
    if ambas:
        n, raw_unit = ambas.group(1), ambas.group(2)
        unit_label = "meses" if "mes" in raw_unit else "años"
        exp_text = f"vence en {n} {unit_label}"
        upsert("license", "status", "vigente", 0.88)
        upsert("license", "expiration_text", exp_text, 0.88)
        upsert("medical", "apto_status", "vigente", 0.88)
        upsert("medical", "apto_expiration_text", exp_text, 0.88)
        upsert("document", "apto_status", "vigente", 0.88)

    # ── Experience ───────────────────────────────────────────────────────────
    DRIVING_TERMS = ("manejando", "manejo", "experiencia", "full", "quinta", "fulero", "fulera", "tracto")

    years_m = re.search(r"\b(\d{1,2})\s*(?:ano|anos|anio|anios)\s+(?:de\s+)?experiencia\b", text)
    if not years_m:
        years_m = re.search(r"\b(\d{1,2})\s*(?:ano|anos|anio|anios)\b", text)
    if not years_m:
        years_m = re.search(r"\bcon\s+(\d{1,2})\s*(?:ano|anos|anio|anios)\b", text)

    months_m = (
        re.search(r"\b(\d{1,2})\s*meses?\b", text)
        if not years_m else None
    )

    # Build duration label with unit so Chatwoot note shows "10 años" not just "10"
    if years_m:
        _dur_label = f"{years_m.group(1)} años"
        _dur_match = years_m
    elif months_m:
        _dur_label = f"{months_m.group(1)} meses"
        _dur_match = months_m
    else:
        _dur_label = None
        _dur_match = None

    if _dur_label and any(t in text for t in DRIVING_TERMS):
        upsert("experience", "years", _dur_label, 0.85)

    # Quinta rueda
    if any(t in text for t in ("quinta rueda", "5ta rueda", "kinta rueda")):
        upsert("experience", "vehicle_type", "quinta_rueda", 0.85)
        upsert("experience", "fifth_wheel", "sí", 0.85)
        if _dur_label:
            upsert("experience", "years", _dur_label, 0.90)

    # Camión sencillo — NOT quinta rueda/full
    if "sencillo" in text:
        upsert("experience", "vehicle_type", "sencillo", 0.85)
        upsert("experience", "fifth_wheel", "no", 0.85)
        if _dur_label:
            upsert("experience", "years", _dur_label, 0.90)

    # Full / fulero (double-articulated — distinct from quinta rueda)
    if any(t in text for t in ("fulero", "fulera", "fuleros")):
        upsert("experience", "vehicle_type", "full", 0.88)
        upsert("experience", "fifth_wheel", "sí", 0.85)
        if years_m:
            upsert("experience", "years", years_m.group(1), 0.88)

    # General fifth_wheel signal (lower confidence — no explicit type)
    if any(t in text for t in ("quinta", "full", "tracto", "trailer")):
        if any(t in text for t in ("si", "sí", "tengo", "manejo", "manejando", "experiencia")):
            upsert("experience", "fifth_wheel", "sí", 0.75)

    if any(t in text for t in ("carretera mexicana", "republica", "república", "foraneo", "foráneo")):
        upsert("experience", "carretera_mexicana", "sí", 0.75)

    # ── Documents ────────────────────────────────────────────────────────────
    if "cartas" in text and any(t in text for t in ("si", "sí", "cuento", "tengo")):
        upsert("documents", "labor_letters_status", "available", 0.80)

    if any(t in text for t in ("carta", "cartas", "laboral", "laborales")) and "no tengo" not in text:
        upsert("documents", "labor_letters", "sí", 0.90)

    if any(t in text for t in ("lo tengo", "tengo todo", "si tengo", "sí tengo", "cuento con todo", "toda mi informacion")):
        upsert("documents", "availability_claim", "candidate_says_available", 0.70)

    if any(t in text for t in ("en unas horas", "yo le aviso", "luego se los mando", "luego los mando",
                               "dame oportunidad", "deme oportunidad", "conseguirlos", "vengo manejando")):
        upsert("documents", "submission_status", "pending_candidate_will_send", 0.85)
        upsert("candidate", "availability_status", "en_ruta_o_no_disponible_ahora", 0.75)

    # ── Candidate intent / availability ──────────────────────────────────────
    if any(t in text for t in ("me agrada", "si me interesa", "sí me interesa", "me interesa",
                               "seguimos", "adelante", "si jalo", "jalo")):
        upsert("candidate", "vacancy_accepted", "sí", 0.75)

    if any(t in text for t in ("voy manejando", "vengo manejando", "ando manejando",
                               "al rato", "mas tarde", "más tarde")):
        upsert("candidate", "availability_status", "en_ruta_o_no_disponible_ahora", 0.80)

    # ── Age ──────────────────────────────────────────────────────────────────
    age_m = re.search(
        r"\b(?:tengo|edad(?:\s+es\s+de)?)?\s*(1[8-9]|[2-6][0-9]|7[0-5])\s*(?:ano|anos|anio|anios)?\b", text
    )
    if age_m:
        upsert("candidate", "age", age_m.group(1), 0.88)

    return facts


def extract_profile_facts_as_dict(message: str) -> dict[str, Any]:
    """Flat dict view of extract_profile_facts — used by the debounce guard."""
    return {
        f"{f['fact_group']}.{f['fact_key']}": f["fact_value"]
        for f in extract_profile_facts(message)
    }


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
