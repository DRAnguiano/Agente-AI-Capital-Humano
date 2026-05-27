# app/graphs/hr_nodes_fast_semantic_router.py

from __future__ import annotations

import re
import unicodedata
from typing import Any

from app.graphs.hr_state import HRState


def _norm(text: str) -> str:
    text = (text or "").lower().strip()
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = re.sub(r"[^a-z0-9ñ\s$.-]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


FAST_INTENTS: list[dict[str, Any]] = [
    {
        "intent": "payment_compensation",
        "route": "rag",
        "preferred_sources": ["01_pago_prestaciones.md"],
        "rewrite": "¿Cuánto pagan por vuelta, tramo o kilómetro, y qué prestaciones manejan?",
        "aliases": [
            "pagan",
            "pago",
            "pagos",
            "sueldo",
            "salario",
            "kilometro",
            "kilómetro",
            "km",
            "x kilometro",
            "por kilometro",
            "prestaciones",
            "beneficios",
            "bono",
            "bonos",
            "gastos muertos",
            "viaticos",
            "viáticos",
            "fondo de ahorro",
        ],
    },
    {
        "intent": "requirements_documents",
        "route": "rag",
        "preferred_sources": ["02_documentos_requisitos.md"],
        "rewrite": "¿Qué requisitos y documentos piden para entrar como operador?",
        "aliases": [
            "requisitos",
            "rekisitos",
            "reqisitos",
            "documentos",
            "que piden",
            "qué piden",
            "ocupan",
            "okupan",
            "licencia",
            "lic",
            "apto",
            "medico",
            "médico",
            "cartas laborales",
            "cartas",
            "sello",
            "logotipo",
            "hoja membretada",
            "vencida",
            "vencido",
            "renovarla",
            "vigente",
        ],
    },
    {
        "intent": "drug_testing_urine",
        "route": "rag",
        "preferred_sources": ["03_seguridad_antidoping.md"],
        "rewrite": "¿Realizan pruebas de orina o pruebas toxicológicas?",
        "aliases": [
            "antidoping",
            "anti doping",
            "antidopin",
            "doping",
            "dooping",
            "toxicol",
            "toxicologica",
            "toxicológica",
            "toxicológicas",
            "toxicologicas",
            "prueba de drogas",
            "pruebas de drogas",
            "prueba de orina",
            "pruebas de orina",
            "orina",
            "miados",
            "meados",
            "pipi",
            "pipí",
            "drogas",
        ],
    },
    {
        "intent": "bases_routes_rest",
        "route": "rag",
        "preferred_sources": ["04_bases_rutas.md"],
        "rewrite": "¿En qué ciudades tienen bases o patios, cómo manejan rutas, descansos y paradas autorizadas?",
        "aliases": [
            "base",
            "bases",
            "vase",
            "patio",
            "patios",
            "siudad",
            "ciudad",
            "monterrey",
            "torreon",
            "torreón",
            "nuevo laredo",
            "queretaro",
            "querétaro",
            "cd juarez",
            "cd. juárez",
            "manzanillo",
            "descanso",
            "descansos",
            "paradas",
            "parada",
            "cafe",
            "café",
            "baño",
            "bano",
            "ruta",
            "rutas",
        ],
    },
    {
        "intent": "driving_school",
        "route": "rag",
        "preferred_sources": ["02_documentos_requisitos.md"],
        "rewrite": "¿Cuentan con escuela de manejo o curso para operador de quinta rueda?",
        "aliases": [
            "escuelita",
            "escuela",
            "curso",
            "op 5ta",
            "5ta rueda",
            "quinta rueda",
            "me falta experiencia",
            "sin experiencia",
            "aprender",
            "ensenan",
            "enseñan",
        ],
    },
]


UNKNOWN_AMBIGUOUS_TERMS = [
    "kchmbr",
    "kchimb",
    "kchimba",
    "kachmbr",
]


def _contains_any(text: str, aliases: list[str]) -> bool:
    return any(alias in text for alias in aliases)


def fast_semantic_router_node(state: HRState) -> dict[str, Any]:
    """
    Fast deterministic router for frequent, low-ambiguity recruiting FAQs.

    Important:
    - This node must not decide conversational churn, urgency, complaints or
      candidate-loss situations. Those messages can contain multiple intentions
      and must be handled by the intent understanding gate.
    - Keep this node limited to stable FAQ-style routes where a partial keyword
      match is acceptable because the downstream answer is grounded in RAG.
    """
    message = state.get("message") or ""
    text = _norm(message)

    if not text:
        return {
            "fast_route_found": False,
            "events": [
                {
                    "type": "fast_semantic_router_checked",
                    "matched": False,
                    "reason": "empty_message",
                }
            ],
        }

    # Ambiguous slang should not be rewritten into a sensitive fact or sent to RAG.
    if _contains_any(text, UNKNOWN_AMBIGUOUS_TERMS):
        reply = (
            "Me perdí tantito con esa palabra. ¿Me confirmas a qué te refieres? "
            "Así te respondo bien y sin inventarte información."
        )
        return {
            "fast_route_found": True,
            "fast_intent": "unknown_ambiguous_term",
            "route": "clarification",
            "intent": "ambiguous_slang_clarification",
            "risk_level": "medium",
            "requires_human": False,
            "requires_rag": False,
            "requires_clarification": True,
            "reason": "fast_unknown_ambiguous_term",
            "reply": reply,
            "text": reply,
            "events": [
                {
                    "type": "fast_semantic_router_matched",
                    "intent": "unknown_ambiguous_term",
                    "route": "clarification",
                    "reason": "unknown_term_should_not_be_rewritten",
                }
            ],
        }

    # FAQ RAG routes only.
    matches: list[dict[str, Any]] = []
    for item in FAST_INTENTS:
        hit_count = sum(1 for alias in item["aliases"] if alias in text)
        if hit_count:
            matches.append({**item, "hit_count": hit_count})

    if not matches:
        return {
            "fast_route_found": False,
            "events": [
                {
                    "type": "fast_semantic_router_checked",
                    "matched": False,
                    "reason": "no_fast_intent_match",
                }
            ],
        }

    best = sorted(matches, key=lambda item: item["hit_count"], reverse=True)[0]

    return {
        "fast_route_found": True,
        "fast_intent": best["intent"],
        "route": best["route"],
        "intent": best["intent"],
        "risk_level": "low" if best["intent"] != "drug_testing_urine" else "medium",
        "requires_human": False,
        "requires_rag": True,
        "requires_clarification": False,
        "reason": f"fast_semantic_{best['intent']}",
        "question": best["rewrite"],
        "question_rewrite": {
            "rewritten_question": best["rewrite"],
            "normalized_terms": best["aliases"][:8],
            "reason": f"fast_semantic_{best['intent']}",
            "confidence": 1.0,
            "preferred_sources": best["preferred_sources"],
        },
        "classifier": {
            "datasource": "vectorstore",
            "recommended_route": "rag",
            "classifier_intent": best["intent"],
            "risk_level": "low" if best["intent"] != "drug_testing_urine" else "medium",
            "requires_rag": True,
            "requires_web_lookup": False,
            "requires_human": False,
            "requires_clarification": False,
            "reason": f"fast_semantic_{best['intent']}",
            "confidence": 1.0,
            "preferred_sources": best["preferred_sources"],
        },
        "events": [
            {
                "type": "fast_semantic_router_matched",
                "intent": best["intent"],
                "route": best["route"],
                "question": best["rewrite"],
                "preferred_sources": best["preferred_sources"],
                "hit_count": best["hit_count"],
            }
        ],
    }
