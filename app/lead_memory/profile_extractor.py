"""Extractor de facts del candidato por regex (licencia, apto, experiencia,
documentos, edad, ciudad).

**Único** extractor regex del proyecto: Neo4j cubre geo/vehículo; aquí NO se
dispersa lógica equivalente (constraint 2 en ``openspec/project.md``). El RAG
nunca extrae facts.

Opera sobre texto ya **normalizado** (jerga/typos canonicalizados aguas
arriba), por lo que los marcadores de residencia y los nombres capturados
llegan en forma canónica. Puro: no persiste; devuelve dicts de fact.
"""
from __future__ import annotations

import re
from typing import Any

from app.knowledge.text_normalizer import normalize_text
from app.knowledge.normalize_domain_values import normalize_vehicle


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

_MONTHS = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "setiembre", "octubre",
    "noviembre", "diciembre",
)


def _number_word_to_text(value: str) -> str:
    value = normalize_text(value)
    mapped = _NUMBER_WORDS.get(value)
    return str(mapped) if mapped is not None else value


def _find_expiration_text(text: str) -> str | None:
    rel = re.search(
        r"\b(?:vence|vencen|se\s+(?:me\s+)?vence|vencimiento)\b"
        r"(?:\s+(?:como|aprox(?:imadamente)?))?"
        r"\s+en\s+(\d{1,2}|un|una|uno|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez)"
        r"\s+(dias?|semanas?|mes(?:es)?|ano|anos|anio|anios)\b",
        text,
    )
    if rel:
        n = _number_word_to_text(rel.group(1))
        unit = rel.group(2)
        unit_label = "años" if unit in {"ano", "anos", "anio", "anios"} else unit
        return f"vence en {n} {unit_label}"

    numeric_date = re.search(
        r"\b(?:vence|vencen|se\s+(?:me\s+)?vence|vencimiento)\b"
        r"\s+(?:el\s+)?(\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?)\b",
        text,
    )
    if numeric_date:
        return numeric_date.group(1)

    month_pattern = "|".join(_MONTHS)
    long_date = re.search(
        r"\b(?:vence|vencen|se\s+(?:me\s+)?vence|vencimiento)\b"
        rf"\s+(?:el\s+)?(\d{{1,2}}\s+de\s+(?:{month_pattern})(?:\s+de\s+\d{{4}})?)\b",
        text,
    )
    if long_date:
        return long_date.group(1)

    month_year = re.search(
        r"\b(?:vence|vencen|se\s+(?:me\s+)?vence|vencimiento)\b"
        rf"\s+(?:en\s+|para\s+)?((?:{month_pattern})(?:\s+de)?\s+\d{{4}})\b",
        text,
    )
    if month_year:
        return month_year.group(1)
    return None


def _has_renewal_proof(text: str) -> str | None:
    if not any(term in text for term in ("papel", "comprobante", "pago", "cita", "tramite", "tramit")):
        return None
    if re.search(r"\b(?:no|todavia no|aun no|sin)\b", text):
        return "no"
    if re.search(r"\b(?:si|sí|ya|tengo|cuento)\b", text):
        return "sí"
    return None


def _expiry_text_is_short_unknown(expiration_text: str) -> bool:
    t = normalize_text(expiration_text)
    m = re.search(r"\b(\d{1,2})\s+(dias?|semanas?|mes(?:es)?)\b", t)
    if not m:
        return False
    amount = int(m.group(1))
    unit = m.group(2)
    return unit.startswith("dia") or unit.startswith("semana") or (unit.startswith("mes") and amount <= 3)


# Geo fallback — used when Neo4j is unavailable.
# Multi-word aliases must precede any shorter alias they contain.
# Catálogo de ciudades inline para anclar candidate.city por regex. Convive con
# rh_city_catalog (Postgres), que resuelve normalización/geo estructurada; ver
# deuda D-5 (docs/deuda_tecnica.md) sobre cuál fuente manda al crecer.
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

    # Si hay marcador de residencia, los aliases se buscan SOLO después del
    # marcador y gana el MÁS CERCANO — "soy de gomez palacio ... para ir a
    # torreon" debe dar Gómez Palacio, no el destino mencionado después.
    marker = re.search(r"\b(?:resido|radico|vivo|soy)\s+(?:en|de)\s+", text)
    search_zone = text[marker.end():] if marker else text
    best: tuple[int, str] | None = None
    for alias, canonical in KNOWN_CITY_ALIASES:
        idx = search_zone.find(alias)
        if idx >= 0 and (best is None or idx < best[0]):
            best = (idx, canonical)
    if best:
        return _fact("candidate", "city", best[1], 0.9)

    # Sobre texto NORMALIZADO: ahí ya aplicó la canonicalización de jerga/typos
    # ("soy d gomez palasio" → "soy de gomez palacio"), así que el marcador de
    # residencia y el nombre capturado llegan en forma canónica.
    match = re.search(
        r"\b(?:resido|radico|vivo|soy)\s+(?:en|de)\s+([a-z0-9áéíóúñ .]{3,40})",
        text,
        flags=re.IGNORECASE,
    )
    if match:
        # Corta en conectores/interrogativos para no tragarse la frase
        # ("soy de Laredo ahí de donde a donde me toca ir" → "laredo").
        raw_city = re.split(
            r"\b(?:y|con|tengo|licencia|apto|cartas|ahi|ahí|a|donde|dónde|que|qué|para|pero|cual|cuál|como|cómo|cuando|cuándo)\b",
            match.group(1),
        )[0].strip(" .,")
        # Tope defensivo: ninguna ciudad objetivo supera 4 tokens.
        raw_city = " ".join(raw_city.split()[:4])
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

    expiration_text = _find_expiration_text(text)
    if expiration_text and any(t in text for t in ("licencia", "lic", "tipo e", "tipo b")):
        upsert("license", "expiration_text", expiration_text, 0.90)
        if not _expiry_text_is_short_unknown(expiration_text):
            upsert("license", "status", "vigente", 0.80)

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
        ):
            upsert("medical", "apto_status", "vigente", 0.95)
            upsert("document", "apto_status", "vigente", 0.95)

    if expiration_text and any(t in text for t in ("apto", "medico")):
        upsert("medical", "apto_expiration_text", expiration_text, 0.90)
        if not _expiry_text_is_short_unknown(expiration_text):
            upsert("medical", "apto_status", "vigente", 0.80)
            upsert("document", "apto_status", "vigente", 0.80)

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

    proof = _has_renewal_proof(text)
    if proof:
        upsert("documents", "renewal_proof", proof, 0.80)

    # ── Experience ───────────────────────────────────────────────────────────
    DRIVING_TERMS = ("manejando", "manejo", "experiencia", "operador", "full", "quinta", "fulero", "fulera", "tracto")

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

    # ── Tipo de unidad / experiencia (catálogo de dominio, sin regex de negocio) ──
    # Fase 1B / F8: full|sencillo se confirman como vehicle_type. quinta rueda / tráiler /
    # traila / tractocamión son experiencia COMPATIBLE pero NO vehicle_type final (el funnel
    # pedirá full o sencillo). camión es ambiguo; torton/rabón/reparto/local/camioneta no son
    # objetivo → no se infiere vehicle_type. La resolución vive en domain_catalog (datos).
    veh = normalize_vehicle(message)
    if veh and veh.value:                  # full | sencillo confirmados
        upsert("experience", "vehicle_type", veh.value, 0.88)
        if _dur_label:
            upsert("experience", "years", _dur_label, 0.90)
    elif veh and veh.target_experience:    # quinta rueda / tráiler / traila / tractocamión
        # señal ambigua de oficio: no se persiste vehicle_type;
        # el funnel preguntará: ¿tracto full o sencillo?
        if _dur_label:
            upsert("experience", "years", _dur_label, 0.90)
    # camión (ambiguo) y torton/rabón/reparto/carga local/camioneta (no objetivo):
    # NO se infiere vehicle_type.

    if any(t in text for t in ("carretera mexicana", "republica", "república", "foraneo", "foráneo")):
        upsert("experience", "carretera_mexicana", "sí", 0.75)

    # ── Documents ────────────────────────────────────────────────────────────
    if "cartas" in text and any(t in text for t in ("si", "sí", "cuento", "tengo")):
        upsert("documents", "labor_letters_status", "available", 0.80)

    if any(t in text for t in ("carta", "cartas", "laboral", "laborales")) and "no tengo" not in text:
        upsert("documents", "labor_letters", "sí", 0.90)

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
    # Edad SOLO con señal explícita; nunca desde "N años" de experiencia.
    #   (a) con la palabra "edad" → siempre edad
    #   (b) "tengo / cuento con N años" → solo si NO hay contexto de experiencia
    has_exp_context = any(t in text for t in DRIVING_TERMS)
    age_m = (
        re.search(r"\b(\d{1,2})\s*(?:ano|anos|anio|anios)\s+de\s+edad\b", text)
        or re.search(r"\bedad\s+(?:es\s+)?(?:de\s+)?(\d{1,2})\b", text)
    )
    if age_m is None and not has_exp_context:
        age_m = re.search(r"\b(?:tengo|cuento con)\s+(\d{1,2})\s*(?:ano|anos|anio|anios)\b", text)
    if age_m and 18 <= int(age_m.group(1)) <= 75:
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
        ("candidate.age", "edad"),
        ("experience.vehicle_type", "tipo de unidad (tracto full o sencillo)"),
        ("license.category", "tipo de licencia"),
        ("license.expiration_text", "vencimiento de licencia"),
        ("medical.apto_expiration_text", "vencimiento de apto médico"),
        ("experience.years", "años de experiencia"),
        ("documents.labor_letters_status", "cartas laborales"),
    ]
    return [label for key, label in required if key not in facts]
