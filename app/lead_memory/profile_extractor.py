"""Extractor de facts del candidato (licencia, apto, experiencia,
documentos, edad, ciudad).

Los extractores de texto natural usan LLM T=0 (llm-first-extraction).
Las capas deterministas (catalog lookups, fact comparison) se mantienen con regex.
Puro: no persiste; devuelve dicts de fact.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any

from app.knowledge.text_normalizer import normalize_text
from app.knowledge.normalize_domain_values import normalize_vehicle
from app.knowledge.domain_catalog import NEEDS_CLARIFICATION, NON_TARGET
from app.knowledge.business_hours import classify_call_window

_EXTRACTOR_MODEL = os.getenv("GROQ_CLASSIFIER_MODEL", "llama-3.1-8b-instant")

_PROFILE_EXPIRATION_SYSTEM = """Eres un extractor de datos de reclutamiento.
Del mensaje, extrae la expresión de vencimiento de un documento (licencia o apto médico).
Formato de salida:
- Tiempo relativo → "vence en N años/meses/días" (convierte palabras a números)
- Fecha exacta → copia exacto: "31 de diciembre de 2027", "12/2025"
- Mes+año → "diciembre 2026", "enero de 2027"
- Vencido → "vencido"
- Sin dato de tiempo: null
Responde SOLO JSON: {"expiration_text": "<expresión>" | null}
Ejemplos:
- "mi licencia vence el 31 de diciembre de 2027" → {"expiration_text": "31 de diciembre de 2027"}
- "el apto se me vence como en dos meses" → {"expiration_text": "vence en 2 meses"}
- "se me vence en 3 años" → {"expiration_text": "vence en 3 años"}
- "vence para diciembre" → {"expiration_text": "diciembre"}
- "ambas vencen en un año" → {"expiration_text": "vence en 1 año"}
- "ya están vencidas" → {"expiration_text": "vencido"}
- "está vigente" → {"expiration_text": null}
- "hola buenas" → {"expiration_text": null}"""

_PROFILE_EXPERIENCE_YEARS_SYSTEM = """Eres un extractor de datos de reclutamiento.
Del mensaje, extrae la duración de experiencia conduciendo vehículos de carga.
- Solo si el candidato habla de SU PROPIA experiencia conduciendo
- NO confundas con la edad del candidato ("tengo 35 años" sin contexto de manejo → null)
- Para años: devuelve entero (ej. 10)
- Para meses: devuelve string con unidad (ej. "8 meses")
- Convierte palabras: "diez" → 10, "una década" → 10
- Frases vagas → null
Responde SOLO JSON: {"years": <entero> | "<N meses>" | null}
Ejemplos:
- "llevo 10 años manejando full" → {"years": 10}
- "tengo como 8 meses de experiencia en carretera" → {"years": "8 meses"}
- "soy operador desde hace 5 años" → {"years": 5}
- "tengo 35 años" → {"years": null}
- "muy poca experiencia" → {"years": null}
- "soy nuevo en esto" → {"years": null}"""

_EXPERIENCE_CONTEXT_SYSTEM = """Eres un clasificador de datos de reclutamiento.
Determina si el candidato habla de SU PROPIA experiencia conduciendo vehículos de carga.
- true: "manejo tracto", "soy operador de quinta rueda", "he manejado tráiler", "trabajo manejando"
- false: "¿manejan ruta B1?", "la empresa usa tractos", preguntas sobre la compañía
Responde SOLO JSON: {"experience_context": true | false}
Ejemplos:
- "soy operador de quinta rueda" → {"experience_context": true}
- "manejo trailer desde hace años" → {"experience_context": true}
- "¿manejan ruta B1?" → {"experience_context": false}
- "la empresa maneja tractos full" → {"experience_context": false}"""

_NO_ROAD_EXP_SYSTEM = """Eres un clasificador de datos de reclutamiento.
Determina si el candidato declara EXPLÍCITAMENTE no tener experiencia manejando carretera.
- true: "no tengo experiencia", "nunca he manejado camión", "quiero aprender a manejar", "sin experiencia"
- false: cualquier otro caso (incluye mensajes sin mención de experiencia, o que sí tienen experiencia)
Responde SOLO JSON: {"no_road_experience": true | false}
Ejemplos:
- "no tengo experiencia en tracto" → {"no_road_experience": true}
- "nunca he manejado carretera" → {"no_road_experience": true}
- "quiero aprender a manejar" → {"no_road_experience": true}
- "tengo 10 años de experiencia" → {"no_road_experience": false}
- "hola, estoy interesado" → {"no_road_experience": false}"""

_CITY_FALLBACK_SYSTEM = """Eres un extractor de datos de reclutamiento.
Del mensaje, extrae la ciudad donde RESIDE el candidato.
- Solo si hay marcador de residencia: "soy de", "vivo en", "radico en", "resido en", "estoy en"
- Extrae solo el nombre de la ciudad (sin estado ni país), máximo 4 palabras
- Si hay ambigüedad o no hay marcador explícito de residencia: null
Responde SOLO JSON: {"city": "<nombre>" | null}
Ejemplos:
- "soy de Hermosillo" → {"city": "Hermosillo"}
- "radico en Ciudad Obregón" → {"city": "Ciudad Obregón"}
- "vivo en el norte" → {"city": null}
- "¿cuánto pagan?" → {"city": null}
- "de por acá" → {"city": null}"""

_CALL_WINDOW_SYSTEM = """Eres un extractor de datos de reclutamiento.
Del mensaje, extrae CUÁNDO el candidato quiere que le llamen.
- Expresiones válidas: días (hoy, mañana, lunes...), horas (a las 10, por la mañana...), combinaciones
- Normaliza a texto corto en español
- Si no menciona una ventana específica de tiempo: null
Responde SOLO JSON: {"call_window": "<expresión>" | null}
Ejemplos:
- "llámenme mañana por la mañana" → {"call_window": "mañana por la mañana"}
- "a las 10 am" → {"call_window": "a las 10 am"}
- "el próximo lunes en la tarde" → {"call_window": "lunes por la tarde"}
- "cuando puedan" → {"call_window": null}
- "me pueden llamar por favor" → {"call_window": null}"""


def _find_expiration_text(text: str, message: str = "") -> str | None:
    _expiry_hints = ("vence", "vencen", "vencimiento", "caduca", "caducidad", "caduco")
    if not any(h in text for h in _expiry_hints):
        return None
    try:
        from app.indexer import call_groq_json
        raw = call_groq_json(message or text, _PROFILE_EXPIRATION_SYSTEM, temperature=0.0, model=_EXTRACTOR_MODEL)
        val = json.loads(raw).get("expiration_text")
        return str(val).strip() if val else None
    except Exception:
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

    # Alias lookup exhausted — LLM fallback for free-form residence declarations.
    # Check both normalized text and original (lowercased) to catch typos like
    # "soy d ciudad" that survive without _PHRASE_CANON in normalize_text.
    _residence_markers = ("soy de", "soy d ", "soi de", "soi d ", "vivo en", "vivo n ",
                          "radico en", "resido en", "estoy en")
    _msg_lower = (message or "").lower()
    if any(m in text for m in _residence_markers) or any(m in _msg_lower for m in _residence_markers):
        try:
            from app.indexer import call_groq_json
            raw = call_groq_json(message, _CITY_FALLBACK_SYSTEM, temperature=0.0, model=_EXTRACTOR_MODEL)
            city_val = json.loads(raw).get("city")
            if city_val:
                return _fact("candidate", "city", str(city_val).strip().title(), 0.65)
        except Exception:
            pass
    return None


# "Laredo" es ambiguo: Nuevo Laredo (Tamaulipas, MX) vs Laredo (Texas, EUA). Solo se
# desambigua cuando el candidato lo declara como RESIDENCIA; dentro de una pregunta de
# ruta sin marcador no aplica (ya lo cubre el guard de geo del orquestador). Si trae
# "nuevo laredo"/"tamaulipas" (MX explícito) o "texas"/"tx" (EUA explícito), NO es ambiguo.
_LAREDO_RESIDENCE_MARKERS = ("soy de", "vivo en", "radico en", "resido en", "estoy en", "me encuentro en")


def detect_laredo_ambiguity(message: str) -> bool:
    """True si el candidato declara residencia en "Laredo" sin especificar cuál."""
    text = normalize_text(message or "")
    if "laredo" not in text:
        return False
    # Explícito (no ambiguo): lado mexicano o lado americano ya resuelto.
    if any(t in text for t in ("nuevo laredo", "tamaulipas", "texas", "laredo tx")):
        return False
    # Solo dispara como residencia declarada en primera persona.
    return any(marker in text for marker in _LAREDO_RESIDENCE_MARKERS)


# ── Call scheduling (B7.4) ────────────────────────────────────────────────────
# Detección determinista de que el candidato pide/acepta una llamada. Patrones sobre
# texto ya normalizado (minúsculas, sin acentos, sin puntuación). La emisión del label
# `llamada_pendiente` la decide `calculate_candidate_labels` (gate perfil_listo / agente);
# aquí solo se registran los facts `scheduling.*`. NO se promete agenda real.
_CALL_REQUEST_RE = re.compile(
    r"\b(?:"
    r"me\s+llam\w+|llamen\w*|llamem\w*|"            # me llamen, llámenme
    r"me\s+pueden\s+llamar|pueden\s+llamarme|puede\s+llamarme|"
    r"me\s+marc\w+|marquen\w*|marquem\w*|"          # me marcan, márquenme
    r"(?:prefiero|mejor|quiero|quisiera|me\s+gustaria|me\s+gusta|agend\w+)\s+(?:que\s+me\s+llamen|(?:una\s+)?llamada)|"
    r"una\s+llamada|por\s+(?:telefono|llamada)|hablamos\s+por\s+telefono"
    r")\b"
)
# Negación: si el candidato rechaza la llamada, NO se registra solicitud.
_CALL_NEG_RE = re.compile(r"\bno\s+(?:quiero\s+(?:la\s+|una\s+)?llamada|me\s+llamen|llamada)\b")


def _extract_call_window(message: str) -> str | None:
    try:
        from app.indexer import call_groq_json
        raw = call_groq_json(message, _CALL_WINDOW_SYSTEM, temperature=0.0, model=_EXTRACTOR_MODEL)
        val = json.loads(raw).get("call_window")
        return str(val).strip() if val else None
    except Exception:
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

    # General type letter — requiere "tipo" o "licencia" inmediatamente adyacentes
    # (sin palabras intermedias) para evitar capturar "a" de "aprender a manejar".
    m = re.search(r"\b(?:licencia\s+(?:tipo\s*)?|tipo\s*)([abe])\b", text)
    if m:
        upsert("license", "category", m.group(1).upper(), 0.90)

    # ── License validity ─────────────────────────────────────────────────────
    if any(t in text for t in ("vigente", "vigentes", "en regla", "todo vigente", "toda mi informacion")):
        if any(t in text for t in ("licencia", "lic", "tipo e", "tipo b")):
            upsert("license", "status", "vigente", 0.80)
        if any(t in text for t in ("apto", "toda mi informacion", "todo vigente")):
            upsert("medical", "apto_status", "vigente", 0.80)
        if "cartas" in text:
            upsert("documents", "labor_letters_status", "available", 0.80)

    expiration_text = _find_expiration_text(text, message)
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

    _dur_label: str | None = None
    if any(t in text for t in DRIVING_TERMS):
        try:
            from app.indexer import call_groq_json
            raw = call_groq_json(message, _PROFILE_EXPERIENCE_YEARS_SYSTEM, temperature=0.0, model=_EXTRACTOR_MODEL)
            val = json.loads(raw).get("years")
            if val is not None:
                _dur_label = f"{val} años" if isinstance(val, int) else str(val)
        except Exception:
            pass

    if _dur_label:
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

    # ── Solicitud de llamada (B7.4) + validación de ventana (B7.5) ────────────
    if _CALL_REQUEST_RE.search(text) and not _CALL_NEG_RE.search(text):
        upsert("scheduling", "call_requested", "true", 0.85)
        upsert("scheduling", "call_status", "pending", 0.85)
        window = _extract_call_window(message)
        if window:
            upsert("scheduling", "call_window_text", window, 0.80)
        # Validez vs horario de oficina (8:00–17:30 L–V): true | false | unknown.
        upsert("scheduling", "call_window_valid", classify_call_window(text), 0.80)

    # Solo escribir vehicle_type_pending/non_target cuando hay evidencia de
    # experiencia personal — no por mera mención del vehículo como tipo de vacante.
    veh = normalize_vehicle(message)
    _experience_context = False
    if veh and veh.status == NEEDS_CLARIFICATION and veh.domain:
        try:
            from app.indexer import call_groq_json
            raw = call_groq_json(message, _EXPERIENCE_CONTEXT_SYSTEM, temperature=0.0, model=_EXTRACTOR_MODEL)
            _experience_context = bool(json.loads(raw).get("experience_context"))
        except Exception:
            pass
    if veh and veh.status == NEEDS_CLARIFICATION and veh.domain and _experience_context:
        upsert("experience", "vehicle_type_pending", veh.domain, 0.86)
    if veh and veh.status == NON_TARGET and veh.domain:
        upsert("experience", "non_target_vehicle_type", veh.domain, 0.88)

    has_confirmed_or_non_target_unit = bool(veh and (veh.value or veh.status == NON_TARGET))
    no_road_experience = False
    _no_road_hints = ("no tengo", "sin experiencia", "nunca he", "nunca mane", "aprender a manejar", "quiero aprender")
    if any(h in text for h in _no_road_hints):
        try:
            from app.indexer import call_groq_json
            raw = call_groq_json(message, _NO_ROAD_EXP_SYSTEM, temperature=0.0, model=_EXTRACTOR_MODEL)
            no_road_experience = bool(json.loads(raw).get("no_road_experience"))
        except Exception:
            pass
    if no_road_experience and not has_confirmed_or_non_target_unit and not _dur_label:
        upsert("experience", "road_experience", "none", 0.88)

    if re.search(r"\b(b1|b-1|estados unidos|eeuu|ee uu|eua|usa|ruta americana|lado americano|laredo texas|laredo tx|cruce|cruzar)\b", text):
        upsert("experience", "b1_us_intent", "sí", 0.88)

    if re.search(
        r"\breingres\w*\b"
        r"|volver a trabajar"
        r"|\bya\b.*\btrabaj\w*\b.*\b(ustedes|la empresa|transmontes|aqui|aca)\b"
        r"|\btrabaj\w*\b.*\b(antes|anteriormente)\b.*\b(ustedes|la empresa|transmontes|aqui|aca)\b",
        text,
    ):
        upsert("candidate", "reingreso", "sí", 0.88)

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
