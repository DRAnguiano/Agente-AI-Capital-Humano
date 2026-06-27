"""Capa de respuesta contextual controlada (Opción B).

Después de que el flujo determinista resolvió extracción, validación, decisión y
persistencia (escritor único `_store_lead_memory_updates`, que corre antes del guard),
esta capa decora SOLO el prefijo conversacional del ack del funnel con tono humano,
mientras Python conserva la pregunta canónica (`next_question_from_missing_facts`).

Invariantes (ver openspec/changes/controlled-response-composition):
- El LLM NO decide estado, etiquetas, persistencia ni la siguiente pregunta.
- El mensaje crudo del candidato NO entra al prompt → resistente a prompt injection;
  solo viaja una `tone_signal` derivada de forma determinista y el prefijo canónico.
- Validación estricta de la salida; ante cualquier fallo, fallback al ack determinista.
- El contenido de tono lo genera el LLM (variado); no hay banco fijo de frases.
"""
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from typing import Any

from app.indexer import call_llm
from app.knowledge.current_turn import _join_ack_and_question, current_turn_ack_parts
from app.knowledge.reply_cleaner import clean_reply
from app.knowledge.text_normalizer import normalize_text

_COMPOSER_ENABLED = "KNOWLEDGE_RESPONSE_COMPOSER_ENABLED"
_COMPOSER_SHADOW = "KNOWLEDGE_RESPONSE_COMPOSER_SHADOW"
_ACK_MAX_CHARS = 160

_NUMBER_WORDS = frozenset({
    "un", "uno", "una", "dos", "tres", "cuatro", "cinco", "seis", "siete",
    "ocho", "nueve", "diez", "once", "doce", "trece", "catorce", "quince",
    "dieciseis", "diecisiete", "dieciocho", "diecinueve", "veinte", "treinta",
    "cuarenta", "cincuenta", "sesenta", "setenta", "ochenta", "noventa", "cien",
})

# Frases que NO se permiten cuando el dato del turno NO fue persistido (anti falsa
# confirmación). Solo se aplican como filtro de seguridad, nunca como contenido.
_PERSISTENCE_CLAIM = re.compile(
    r"(registrad|aprobad|qued[oó]\s+(?:registrad|anotad|guardad|listo)|"
    r"ya\s+(?:avanz|qued|est[aá]\s+listo)|cumple|su\s+perfil\s+est[aá]\s+list)",
    re.IGNORECASE,
)

_HUMOR_HINTS = ("jaja", "jeje", "jiji", "jaj", "lol", "🤣", "😂", "🤠")
_FRUST_HINTS = (
    "me pele", "ni modo", "ya ni", "harto", "molest", "enojad", "fastidi",
    "no me han", "no me ha", "que mal", "una lastima",
)
_EVASION_HINTS = (
    "ahorita le", "luego le", "despues le", "al rato", "espereme", "esperame",
    "mas tarde", "luego te", "ahorita te",
)

_TONE_GUIDE = {
    "humor": "El candidato bromeó; reconoce el buen humor con calidez, sin exagerar.",
    "frustration": "El candidato suena molesto o desanimado; responde con empatía y respeto.",
    "evasion": "El candidato evade o pospone; mantén un tono comprensivo y paciente.",
    "doubt": "El candidato muestra duda; responde con claridad y cercanía.",
    "neutral": "Responde corto y cordial.",
}


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _has_number(text: str | None) -> bool:
    norm = normalize_text(text or "")
    if any(ch.isdigit() for ch in norm):
        return True
    return any(tok in _NUMBER_WORDS for tok in norm.split())


def _derive_tone(message: str | None) -> str:
    raw = (message or "").lower()
    norm = normalize_text(message or "")
    if any(h in raw for h in _HUMOR_HINTS):
        return "humor"
    if any(f in norm for f in _FRUST_HINTS):
        return "frustration"
    if any(e in norm for e in _EVASION_HINTS):
        return "evasion"
    if "?" in raw or "¿" in raw:
        return "doubt"
    return "neutral"


def _first_name(facts: dict[str, Any] | None) -> str | None:
    name = str((facts or {}).get("candidate.name") or "").strip()
    if not name:
        return None
    token = name.split()[0]
    return (token[:1].upper() + token[1:].lower()) if token else None


@dataclass(frozen=True)
class ResponseComposition:
    """Contrato interno entre la decisión operacional y el envío.

    Es la ÚNICA entrada de la capa lingüística. No transporta el historial completo
    ni el mensaje crudo del candidato.
    """

    pending_question: str
    deterministic_prefix: str
    deterministic_ack: str
    override: str | None = None
    tone_signal: str = "neutral"
    persisted: bool = False
    candidate_first_name: str | None = None
    extraction_state: str = "valid"


def build_response_composition(
    message: str | None,
    merged_facts: dict[str, Any] | None,
    current_facts: dict[str, Any] | None,
    pre_validated: list | None,
    last_bot_message: str | None,
) -> ResponseComposition:
    """Ensambla el contrato a partir de fuentes que el worker ya tiene en el guard.

    No re-extrae ni persiste: lee el resultado del flujo determinista.
    """
    override, prefix, question = current_turn_ack_parts(
        message, merged_facts, last_bot_message, current_facts
    )
    deterministic_ack = (
        override if override is not None else _join_ack_and_question(prefix, question)
    )
    persisted = bool(pre_validated)
    first_name = _first_name(merged_facts) if persisted else None
    return ResponseComposition(
        pending_question=question,
        deterministic_prefix=prefix,
        deterministic_ack=deterministic_ack,
        override=override,
        tone_signal=_derive_tone(message),
        persisted=persisted,
        candidate_first_name=first_name,
        extraction_state="valid" if persisted else "incomplete",
    )


def _build_ack_prompt(rc: ResponseComposition) -> str:
    name_line = (
        f"Puedes dirigirte a la persona como «{rc.candidate_first_name}» UNA sola vez."
        if rc.candidate_first_name
        else "No uses ningún nombre propio."
    )
    persist_line = (
        ""
        if rc.persisted
        else " NO afirmes que algo 'quedó registrado', 'ya avanzó', 'cumple' ni 'fue aprobado'."
    )
    return (
        "Eres Mundo, del equipo de reclutamiento de Transmontes. Reclutador mexicano: "
        "directo, cálido, breve.\n"
        "TU ÚNICO TRABAJO: reescribir esta confirmación con tono humano y natural, SIN "
        "cambiar su significado y SIN añadir datos.\n"
        f"Confirmación a reformular: {rc.deterministic_prefix!r}\n"
        f"{_TONE_GUIDE.get(rc.tone_signal, _TONE_GUIDE['neutral'])}\n"
        f"{name_line}{persist_line}\n"
        "Reglas: una sola oración, máximo 18 palabras; NUNCA termines con '?'; no hagas "
        "preguntas; no inventes cifras, años, documentos, ciudades ni condiciones; no "
        "prometas sueldo ni contratación; nada de '¡Genial!' ni '¡Excelente!'. "
        "Devuelve SOLO la frase, sin comillas."
    )


def _validate_ack_block(block: str, rc: ResponseComposition) -> tuple[str, str | None]:
    b = (block or "").strip()
    if not b:
        return "", "empty"
    if len(b) > _ACK_MAX_CHARS:
        return "", "too_long"
    if "?" in b or "¿" in b:
        return "", "has_question"
    if _has_number(b) and not _has_number(rc.deterministic_prefix):
        return "", "fabricated_number"
    if not rc.persisted and _PERSISTENCE_CLAIM.search(b):
        return "", "persistence_claim"
    return b, None


def _generate_ack_block(rc: ResponseComposition) -> str:
    return clean_reply(call_llm(_build_ack_prompt(rc)) or "")


def _log(used: bool, reason: str | None, ms: float, rc: ResponseComposition) -> None:
    try:
        print(
            "[COMPOSER]",
            json.dumps(
                {
                    "used": used,
                    "fallback": not used,
                    "reason": reason,
                    "tone": rc.tone_signal,
                    "persisted": rc.persisted,
                    "canonical_question_preserved": True,
                    "compose_added_ms": ms,
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
    except Exception:
        pass


def compose_reply(rc: ResponseComposition) -> str:
    """Devuelve el ack final. Opción B: el LLM solo redacta el prefijo de tono;
    Python une la pregunta canónica. Fallback total al ack determinista."""
    # Respuestas de política (p. ej. descarte por edad) nunca se decoran.
    if rc.override is not None:
        return rc.override

    if not _env_bool(_COMPOSER_ENABLED):
        if _env_bool(_COMPOSER_SHADOW):
            _shadow(rc)
        return rc.deterministic_ack

    started = time.perf_counter()
    block, reason = "", None
    try:
        block = _generate_ack_block(rc)
    except Exception as exc:  # noqa: BLE001 — cualquier fallo cae al determinista
        reason = f"llm_error:{type(exc).__name__}"
    if block:
        block, reason = _validate_ack_block(block, rc)
    else:
        reason = reason or "empty"

    ms = round((time.perf_counter() - started) * 1000, 2)
    if not block:
        _log(used=False, reason=reason, ms=ms, rc=rc)
        return rc.deterministic_ack
    _log(used=True, reason=None, ms=ms, rc=rc)
    return _join_ack_and_question(block, rc.pending_question)


def _shadow(rc: ResponseComposition) -> None:
    """Modo shadow: genera y loguea la versión compuesta sin enviarla (QA de
    naturalidad), conservando el determinista de cara al candidato."""
    started = time.perf_counter()
    try:
        block, reason = _validate_ack_block(_generate_ack_block(rc), rc)
    except Exception as exc:  # noqa: BLE001
        block, reason = "", f"llm_error:{type(exc).__name__}"
    ms = round((time.perf_counter() - started) * 1000, 2)
    composed = _join_ack_and_question(block, rc.pending_question) if block else None
    try:
        print(
            "[COMPOSER_SHADOW]",
            json.dumps(
                {
                    "reason": reason,
                    "tone": rc.tone_signal,
                    "deterministic": rc.deterministic_ack,
                    "composed": composed,
                    "compose_added_ms": ms,
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
    except Exception:
        pass
