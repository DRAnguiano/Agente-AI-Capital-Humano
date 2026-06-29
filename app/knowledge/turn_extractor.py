"""Extractor unificado de turno (unified-turn-extractor).

Una sola pasada LLM T=0 por turno que devuelve TODOS los datos del candidato:
facts crudos (con evidencia observable), pregunta embebida y señales de turno.

Arquitectura por capas (design.md D1):
  Capa 1 (este módulo, LLM):  lenguaje → concepto crudo + evidencia
  Capa 2 (validate_extraction): concepto → válido (catálogo determinista)
  Capa 3 (en código de negocio): concepto → política (B→sencillo, escuelita, ...)

El LLM NUNCA devuelve confianza (D2) ni toma decisiones de negocio (D1).
Reporta hechos observables: explicit_marker, answered_direct_question.
La confianza se computa en código (Capa 2) a partir de esa evidencia.

Fail-safe (D-degradación): si Groq falla o el JSON no parsea, retorna un
TurnExtraction vacío — el funnel re-pregunta. NUNCA cae a regex-adivinanza.

Estado: SHADOW. Este módulo no está wireado al path vivo todavía (sección 6 de
tasks). Se valida en log-only contra el path actual antes de cortar.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any

from app.knowledge.turn_intent_classifier import TurnIntentSignals
from app.knowledge.geo_utils import normalize_zm_laguna_city
from app.knowledge.llm_errors import LLMUnavailableError

# El extractor unificado usa su propio modelo: por defecto el de generación (70b),
# más capaz para distinguir reclamo/negación de dato afirmado que el 8b clasificador.
# Configurable vía UNIFIED_EXTRACTOR_MODEL sin afectar TIPC ni otros clasificadores.
_EXTRACTOR_MODEL = os.getenv(
    "UNIFIED_EXTRACTOR_MODEL",
    os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
)

# Campos de perfil que el extractor puede reportar (clave canónica).
# Texto libre (sin Capa 2 que valide): name, license_expiration, apto_expiration.
# Con catálogo (Capa 2 valida): city, vehicle_type, age, license_category.
_PROFILE_FIELDS = (
    "candidate.name",
    "candidate.city",
    "candidate.age",
    "experience.vehicle_type",
    "experience.years",
    "license.category",
    "license.expiration_text",
    "medical.apto_expiration_text",
    "documents.proof",
)


@dataclass
class FieldValue:
    """Un campo extraído con su evidencia observable (NO confianza — D2)."""
    value: str | None = None
    explicit_marker: bool = False          # hubo "me llamo"/"soy de"/"vence en"...
    answered_direct_question: bool = False  # last_bot pidió este campo y esto lo responde


@dataclass
class TurnExtraction:
    """Resultado único de la extracción de un turno (D5)."""
    fields: dict[str, FieldValue] = field(default_factory=dict)
    embedded_question: str | None = None
    signals: TurnIntentSignals = field(default_factory=TurnIntentSignals)

    def value(self, key: str) -> str | None:
        fv = self.fields.get(key)
        return fv.value if fv else None


_TURN_EXTRACTOR_SYSTEM = """Eres un extractor de datos de reclutamiento para operadores de camión (tracto full / sencillo).
El candidato escribió un mensaje. El bot le había hecho una pregunta (te la doy como contexto).
También te doy los datos que YA conocemos del candidato.

Extrae TODO lo que el candidato dijo en ESTE mensaje, en una sola pasada. Devuelve EXACTAMENTE este JSON:

{
  "fields": {
    "candidate.name":             {"value": <str|null>, "explicit_marker": <bool>, "answered_direct_question": <bool>},
    "candidate.city":             {"value": <str|null>, "explicit_marker": <bool>, "answered_direct_question": <bool>},
    "candidate.age":              {"value": <str|null>, "explicit_marker": <bool>, "answered_direct_question": <bool>},
    "experience.vehicle_type":    {"value": <str|null>, "explicit_marker": <bool>, "answered_direct_question": <bool>},
    "experience.years":           {"value": <str|null>, "explicit_marker": <bool>, "answered_direct_question": <bool>},
    "license.category":           {"value": <str|null>, "explicit_marker": <bool>, "answered_direct_question": <bool>},
    "license.expiration_text":    {"value": <str|null>, "explicit_marker": <bool>, "answered_direct_question": <bool>},
    "medical.apto_expiration_text":{"value": <str|null>, "explicit_marker": <bool>, "answered_direct_question": <bool>},
    "documents.proof":            {"value": <str|null>, "explicit_marker": <bool>, "answered_direct_question": <bool>}
  },
  "embedded_question": <str|null>,
  "signals": {
    "is_ya_reclamo": <bool>, "is_memory_claim": <bool>, "has_embedded_question": <bool>,
    "call_requested": <bool>, "renewal_proof": <"si"|"no"|null>, "no_road_experience": <bool>,
    "has_expiry_context": <bool>, "experience_context": <bool>
  }
}

REGLAS DE VALOR (qué dijo el candidato — NO interpretes política de negocio):
- candidate.name: nombre propio. Ignora saludos ("hola"), afirmaciones ("si","no") y términos de unidad. Si no hay nombre, null.
- candidate.city: ciudad de RESIDENCIA (no destinos ni rutas). Texto crudo, corrige typos evidentes. Sin marcador de residencia → null.
- candidate.age: edad en años, entero como string. Convierte palabras ("cincuenta y uno"→"51"). NO de "N años de experiencia". Rango plausible 18-70, fuera de eso → null.
- experience.vehicle_type: reporta el término CRUDO tal como lo dijo ("full","sencillo","torton","quinta rueda","trailer"). NO clasifiques si es objetivo o no — eso lo decide el sistema.
- experience.years: años manejando como número o aproximación numérica ("10 años","más de 5","como 3 años"). Expresiones vagas sin número ("toda la vida","de siempre","muchos años","bastante","siempre") → null. Distínguelo del vencimiento de licencia.
- license.category: tipo de licencia federal (A/B/E) tal como lo dijo.
- license.expiration_text: cuánto falta para que venza la licencia ("2 años","6 meses","vencido"). Solo si habla de vigencia de LICENCIA.
- medical.apto_expiration_text: vigencia del apto médico. Si dice "igual/lo mismo que mi licencia" y conoces license.expiration_text, usa ESE valor.
- documents.proof: "cartas" si tiene cartas laborales, "semanas_imss" si tiene semanas del IMSS, "ninguno" si dice que NO tiene. Si no menciona, null.

REGLAS DE EVIDENCIA:
- explicit_marker = true cuando el candidato usó un marcador explícito ("me llamo","soy de","vivo en","mi licencia vence en","tengo X años").
- answered_direct_question = true cuando la pregunta del bot pedía ESE campo y el mensaje lo responde.

embedded_question: si el candidato pregunta por pago/rutas/prestaciones/requisitos, pon el texto de la duda; si no, null.

IMPORTANTE: Responde SOLO el JSON. value siempre es lo que el candidato DIJO, nunca una inferencia de negocio."""


def _parse_field(raw: Any) -> FieldValue:
    if not isinstance(raw, dict):
        return FieldValue()
    val = raw.get("value")
    val = str(val).strip() if val not in (None, "", "null") else None
    return FieldValue(
        value=val,
        explicit_marker=bool(raw.get("explicit_marker", False)),
        answered_direct_question=bool(raw.get("answered_direct_question", False)),
    )


def _parse_signals(raw: Any) -> TurnIntentSignals:
    if not isinstance(raw, dict):
        return TurnIntentSignals()
    return TurnIntentSignals(
        is_ya_reclamo=bool(raw.get("is_ya_reclamo", False)),
        is_memory_claim=bool(raw.get("is_memory_claim", False)),
        has_embedded_question=bool(raw.get("has_embedded_question", False)),
        call_requested=bool(raw.get("call_requested", False)),
        renewal_proof=raw.get("renewal_proof") or None,
        no_road_experience=bool(raw.get("no_road_experience", False)),
        has_expiry_context=bool(raw.get("has_expiry_context", False)),
        experience_context=bool(raw.get("experience_context", False)),
    )


def extract_turn(
    message: str,
    last_bot_question: str | None = None,
    known_facts: dict[str, Any] | None = None,
) -> TurnExtraction:
    """Extrae todo el turno en una sola pasada LLM. Fail-safe a TurnExtraction vacío."""
    if not (message or "").strip():
        return TurnExtraction()

    known = known_facts or {}
    known_lines = "\n".join(f"- {k}: {v}" for k, v in known.items() if v) or "(ninguno)"
    user_content = (
        f"PREGUNTA DEL BOT: {last_bot_question or '(ninguna)'}\n"
        f"DATOS YA CONOCIDOS:\n{known_lines}\n"
        f"MENSAJE DEL CANDIDATO: {message}"
    )

    try:
        from app.indexer import call_groq_json
        from groq import RateLimitError as GroqRateLimitError
        raw = call_groq_json(user_content, _TURN_EXTRACTOR_SYSTEM, temperature=0.0, model=_EXTRACTOR_MODEL)
        data = json.loads(raw)
    except GroqRateLimitError as exc:
        # Cuota agotada en primaria y backup: abort silencioso del turno.
        # El worker captura LLMUnavailableError antes de enviar nada a Chatwoot.
        raise LLMUnavailableError(
            f"Groq quota agotada en ambas claves (TPD): {exc}"
        ) from exc
    except Exception:
        return TurnExtraction()

    fields_raw = data.get("fields") or {}
    fields = {
        key: _parse_field(fields_raw.get(key))
        for key in _PROFILE_FIELDS
        if fields_raw.get(key) and _parse_field(fields_raw.get(key)).value is not None
    }
    if "candidate.city" in fields and fields["candidate.city"].value:
        fields["candidate.city"].value = normalize_zm_laguna_city(fields["candidate.city"].value)
    if "documents.proof" in fields and fields["documents.proof"].value:
        from app.knowledge.current_turn import canonicalize_proof
        _proof_canon = canonicalize_proof(fields["documents.proof"].value)
        if _proof_canon is None:
            del fields["documents.proof"]  # no mapeable → no persistir texto crudo
        else:
            fields["documents.proof"].value = _proof_canon
    embedded = data.get("embedded_question") or None
    return TurnExtraction(
        fields=fields,
        embedded_question=str(embedded).strip() if embedded else None,
        signals=_parse_signals(data.get("signals")),
    )


# ── Capa 2: validación determinista + confianza derivada ──────────────────────

# Campos de texto libre SIN catálogo que valide (D3): requieren anclaje para persistir.
_FREE_TEXT_FIELDS = {
    "candidate.name",
    "license.expiration_text",
    "medical.apto_expiration_text",
}
# Hints de igualdad para resolver "igual que mi licencia" (determinista, no LLM).
_EQUALITY_HINTS = (
    "igual", "mismo", "lo mismo", "al mismo tiempo", "igual que", "mismo que",
    "los dos", "ambos", "misma vigencia", "igualmente",
)
_NAME_SKIP = {
    "si", "no", "nel", "nop", "ok", "va", "dale", "sale", "claro", "exacto",
    "hola", "ola", "buenas", "buenos", "buen", "hey", "gracias", "perfecto",
    "listo", "entendido", "correcto", "anotado", "registrado",
    "full", "sencillo", "tracto", "torton", "rabon",
}


def _derived_confidence(fv: FieldValue, catalog_validated: bool, base: float = 0.5) -> float:
    conf = base
    if catalog_validated:
        conf += 0.3
    if fv.explicit_marker:
        conf += 0.2
    if fv.answered_direct_question:
        conf += 0.2
    return round(min(conf, 1.0), 2)


def validate_extraction(
    extraction: TurnExtraction,
    known_facts: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Capa 2: valida los campos crudos contra catálogos y deriva confianza.

    Devuelve facts canónicos listos para persistir: cada uno con
    {fact_group, fact_key, fact_value, confidence, is_explicit_correction}.
    Aplica D3 (texto libre sin anclaje no se promueve) y la resolución
    determinista de referencias de igualdad. NO aplica política de negocio (Capa 3).
    """
    from app.knowledge.normalize_domain_values import normalize_vehicle
    from app.knowledge.domain_catalog import NON_TARGET, NEEDS_CLARIFICATION
    from app.knowledge.text_normalizer import normalize_text
    from app.settings import AGE_DISQUALIFICATION_LIMIT  # noqa: F401  (política, no usado aquí)

    known = known_facts or {}
    is_correction = extraction.signals.is_ya_reclamo
    out: list[dict[str, Any]] = []

    def _emit(key: str, value: str, fv: FieldValue, catalog_validated: bool):
        group, fkey = key.split(".", 1)
        out.append({
            "fact_group": group,
            "fact_key": fkey,
            "fact_value": value,
            "confidence": _derived_confidence(fv, catalog_validated),
            "is_explicit_correction": is_correction,
        })

    for key, fv in extraction.fields.items():
        if fv.value is None:
            continue

        # D3: texto libre sin anclaje (ni marcador ni respuesta a pregunta) → no promover
        if key in _FREE_TEXT_FIELDS and not (fv.explicit_marker or fv.answered_direct_question):
            continue

        # candidate.name — texto libre, descartar saludos/ruido
        if key == "candidate.name":
            if fv.value.lower().strip() in _NAME_SKIP or len(fv.value.strip()) < 3:
                continue
            _emit(key, fv.value.strip().title(), fv, catalog_validated=False)
            continue

        # candidate.age — Capa 2: rango plausible 18-70
        if key == "candidate.age":
            digits = "".join(c for c in fv.value if c.isdigit())
            if digits and 18 <= int(digits) <= 70:
                _emit(key, str(int(digits)), fv, catalog_validated=True)
            continue

        # experience.vehicle_type — catálogo decide; solo full/sencillo confirmado se promueve.
        # NON_TARGET/NEEDS_CLARIFICATION NO fija vehicle_type (eso es política, Capa 3).
        if key == "experience.vehicle_type":
            res = normalize_vehicle(fv.value)
            if res and res.value:  # full | sencillo confirmado
                _emit(key, res.value, fv, catalog_validated=True)
            # término crudo (torton, quinta rueda) se preserva para Capa 3
            elif res and res.status in {NON_TARGET, NEEDS_CLARIFICATION}:
                out.append({
                    "fact_group": "experience", "fact_key": "vehicle_type_raw",
                    "fact_value": fv.value, "confidence": _derived_confidence(fv, True),
                    "is_explicit_correction": is_correction,
                })
            continue

        # license.category — catálogo A/B/E
        if key == "license.category":
            cat = fv.value.strip().upper().replace("TIPO ", "").strip()
            if cat in {"A", "B", "E"}:
                _emit(key, cat, fv, catalog_validated=True)
            continue

        # medical.apto_expiration_text — resolver igualdad con la licencia (determinista)
        if key == "medical.apto_expiration_text":
            val = fv.value
            if any(h in val.lower() for h in _EQUALITY_HINTS):
                lic = known.get("license.expiration_text") or extraction.value("license.expiration_text")
                if lic:
                    val = lic
                else:
                    continue  # referencia sin ancla → no inventar
            _emit(key, val, fv, catalog_validated=False)
            continue

        # license.expiration_text, experience.years, documents.proof — pasan con su evidencia
        _emit(key, fv.value, fv, catalog_validated=False)

    return out
