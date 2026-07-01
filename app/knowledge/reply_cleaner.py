"""Limpieza unificada de respuestas del LLM (rag-corpus #13).

Punto ÚNICO de limpieza para todas las rutas que devuelven texto del LLM al candidato
(orquestador vivo `_clean_reply` y endpoint `/orchestrate` `_clean_llm_answer`). Antes
existían dos implementaciones divergentes; esta consolida la unión de ambas:

1. sanitiza el carácter de reemplazo Unicode (U+FFFD) que algunos modelos emiten;
2. elimina `<think>...</think>` (cerrado) y el razonamiento tras un `<think>` sin
   cerrar (modelos reasoning como qwen que truncan el pensamiento);
3. quita marcadores de blockquote markdown (`> `) al inicio de línea;
4. recorta cierres genéricos exactos (frases completas) en bucle;
5. recorta cierres genéricos por patrón (regex);
6. quita un nivel de comillas que envuelvan toda la respuesta.

Idempotente y sin dependencias de red.
"""
from __future__ import annotations

import re

# Cierres genéricos exactos que algunos modelos agregan aunque el prompt lo prohíba.
_GENERIC_ENDINGS: tuple[str, ...] = (
    "Si tienes alguna otra duda sobre el proceso, puedo ayudarte a resolverla.",
    "Si tienes alguna otra duda sobre el proceso, puedo ayudarte a resolverlas.",
    "Si tienes alguna otra duda, puedo ayudarte a resolverla.",
    "Si tienes alguna otra duda, puedo ayudarte a resolverlas.",
    "Si tienes otra duda, puedo ayudarte.",
    "Puedo ayudarte si tienes alguna otra duda.",
    "Estoy aquí para ayudarte.",
    "¿Tienes alguna otra duda?",
    "¿Puedo ayudarte con algo más?",
    "¿Quieres que te aclare algo más?",
)

# Cierres genéricos por patrón (unión de app.py y knowledge_orchestrator).
_GENERIC_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\n*Si tienes más dudas sobre .*?, puedo ayudarte a resolverlas\.?\s*$", re.IGNORECASE | re.DOTALL),
    re.compile(r"\n*Si tienes más dudas.*, puedo ayudarte.*$", re.IGNORECASE | re.DOTALL),
    re.compile(r"\n*Si hay algo más que quieras saber.*, puedo buscar.*$", re.IGNORECASE | re.DOTALL),
    re.compile(r"\n*No olvides que Capital Humano puede validar cualquier duda.*$", re.IGNORECASE | re.DOTALL),
    re.compile(r"\n*Capital Humano puede confirmar los detalles exactos.*$", re.IGNORECASE | re.DOTALL),
    re.compile(r"\n*Estoy aquí para ayudarte.*$", re.IGNORECASE | re.DOTALL),
    re.compile(r"\n*Puedo ayudarte a resolver.*$", re.IGNORECASE | re.DOTALL),
    re.compile(r"\n*¿Tienes alguna otra duda\?\s*$", re.IGNORECASE | re.DOTALL),
    re.compile(r"\n*¿Quieres que te aclare algo más\?\s*$", re.IGNORECASE | re.DOTALL),
    re.compile(r"\s*Si tienes (m[aá]s |alguna )?(otra )?duda[s]?,? puedo ayudarte\.?\s*$", re.IGNORECASE),
    re.compile(r"\s*Si necesitas m[aá]s informaci[oó]n,? puedo ayudarte[^.?!]*(\.|!|\?)?\s*$", re.IGNORECASE),
    re.compile(r"\s*¿?Tienes alguna otra duda\??\s*$", re.IGNORECASE),
)

# Pares de comillas que el LLM a veces pone alrededor de TODA la respuesta
# (ej. devuelve '"Laredo, anotado."'). Se quita un solo nivel; no toca las internas.
_WRAP_QUOTE_PAIRS = (('"', '"'), ("“", "”"), ("«", "»"), ("'", "'"))


def _sanitize(text: str) -> str:
    if not text:
        return text
    return text.replace("�", "").encode("utf-8", "ignore").decode("utf-8").strip()


def _strip_wrapping_quotes(text: str) -> str:
    for open_q, close_q in _WRAP_QUOTE_PAIRS:
        if len(text) >= 2 and text[0] == open_q and text[-1] == close_q:
            return text[1:-1].strip()
    return text


def clean_reply(text: str) -> str:
    clean = _sanitize(text or "")
    if not clean:
        return clean
    clean = re.sub(r"<think>.*?</think>", "", clean, flags=re.IGNORECASE | re.DOTALL)
    # Razonamiento truncado: un <think> sin cierre (el modelo reasoning agotó tokens
    # dentro del bloque de pensamiento) → todo lo que sigue es razonamiento, no la
    # respuesta. Se descarta hasta el final (evita filtrar el "pensamiento" al candidato).
    clean = re.sub(r"<think>.*$", "", clean, flags=re.IGNORECASE | re.DOTALL)
    clean = re.sub(r"</?think>", "", clean, flags=re.IGNORECASE).strip()
    # Marcadores de blockquote markdown ("> ") que algunos modelos (p. ej. qwen)
    # anteponen; se ven mal en WhatsApp/Chatwoot. Se quitan al inicio de cada línea.
    clean = re.sub(r"(?m)^[ \t]*>[ \t]?", "", clean).strip()

    changed = True
    while changed:
        changed = False
        for ending in _GENERIC_ENDINGS:
            if clean.endswith(ending):
                clean = clean[: -len(ending)].rstrip()
                changed = True

    for pattern in _GENERIC_PATTERNS:
        clean = pattern.sub("", clean).strip()

    clean = _strip_wrapping_quotes(clean)
    return clean.strip()
