from __future__ import annotations

import re
from typing import Any


# Centralized regex rules for the production hybrid graph.
# Keep this file small and boring on purpose: regex is only for obvious guards,
# not for full intent classification.
REGEX_RULES: dict[str, re.Pattern[str]] = {
    "high_risk": re.compile(
        r"\b(boletinado|r\.control|huachicol|combustible robado|robo|rob[eé]|"
        r"abandon[eé] unidad|documento falso|licencia falsa|arma|armas|"
        r"violencia|golpe[aé]|pelea|demanda|acoso|me drogo|uso drogas|"
        r"marihuana|cristal|perico|coca[ií]na|metanfetamina|"
        r"pastillas para aguantar|para no dormir)\b",
        re.IGNORECASE,
    ),
    "pure_greeting": re.compile(
        r"^(hola|buenas|buenos d[ií]as|buen d[ií]a|buenas tardes|"
        r"buenas noches|qu[eé] tal|que tal|q tal|hey|k tal|k ase|ke ase)\W*$",
        re.IGNORECASE,
    ),
    "on_route": re.compile(
        r"\b(voy manejando|ando en ruta|voy en ruta|10-4|al rato|"
        r"ahorita manejo|luego te escribo|luego te mando)\b",
        re.IGNORECASE,
    ),
    "callback_request": re.compile(
        r"\b(ll[aá]menme|ll[aá]me[nm]e|me llaman|me pueden llamar|"
        r"quiero que me llamen|a qu[eé] hora me llaman)\b",
        re.IGNORECASE,
    ),
}

RULE_TO_ROUTE = {
    "high_risk": "human_handoff",
    "pure_greeting": "static_greeting",
    "on_route": "static_on_route",
    "callback_request": "static_callback",
}

STATIC_REPLIES = {
    "static_greeting": "Hola, soy Mundo de Capital Humano. ¿Te interesa la vacante de operador de quinta rueda?",
    "static_on_route": "Claro, escribe cuando estés detenido y con seguridad; aquí seguimos con tu proceso.",
    "static_callback": "Claro, lo dejo anotado para que Capital Humano pueda darte seguimiento por llamada.",
    "human_handoff": "Ese punto debe revisarlo Capital Humano antes de continuar. Lo dejo anotado para seguimiento.",
}

OUTPUT_GUARD_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\n*Si tienes (m[aá]s |otra )?duda[s]?.{0,80}$", re.IGNORECASE),
    re.compile(r"\n*Estoy aqu[ií] para ayudarte.{0,60}$", re.IGNORECASE),
    re.compile(r"\n*¿(Hay|Tienes) algo m[aá]s.{0,70}\?$", re.IGNORECASE),
    re.compile(r"\n*Puedo ayudarte.{0,60}$", re.IGNORECASE),
    re.compile(r"\n*.{0,40}(nombre completo|cu[aá]l es tu nombre|me confirmas tu nombre).{0,80}$", re.IGNORECASE),
    re.compile(r"\b(ya est[aá]s contratado|quedaste seleccionado|eres el candidato)\b", re.IGNORECASE),
)

MAX_REPLY_CHARS = 600


def _rule_to_route(rule: str | None) -> str | None:
    if not rule:
        return None
    return RULE_TO_ROUTE.get(rule, "continue")


def regex_guard(text: str) -> dict[str, Any]:
    """Single entry guard before LLM work.

    Returns a route only for obvious cases. Everything else should continue to
    rewrite + graph/vector context + generation.
    """
    value = text or ""
    for rule_name, pattern in REGEX_RULES.items():
        if pattern.search(value):
            route = _rule_to_route(rule_name)
            return {
                "matched_rule": rule_name,
                "route": route,
                "reply": STATIC_REPLIES.get(route or ""),
            }
    return {"matched_rule": None, "route": None, "reply": None}


def output_guard(reply: str, max_chars: int = MAX_REPLY_CHARS) -> str:
    """Final deterministic cleanup with no LLM call."""
    clean = (reply or "").strip()
    clean = re.sub(r"<think>.*?</think>", "", clean, flags=re.IGNORECASE | re.DOTALL)
    clean = re.sub(r"</?think>", "", clean, flags=re.IGNORECASE).strip()
    clean = re.sub(
        r"^\s*(¡?Hola!?[,\s]*)?soy Mundo,?\s*asistente de Capital Humano\.?\s*",
        "",
        clean,
        flags=re.IGNORECASE,
    ).strip()

    for pattern in OUTPUT_GUARD_PATTERNS:
        clean = pattern.sub("", clean).strip()

    if len(clean) > max_chars:
        cut = clean.rfind(".", 0, max_chars)
        clean = clean[: cut + 1] if cut > 0 else clean[:max_chars]

    return clean.strip()
