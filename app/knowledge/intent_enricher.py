"""Enriquecimiento y validación de la clasificación multi-intent (Fase 2).

Toma la salida de intent_classifier.classify_message y:
  1. Resuelve conflictos cuando un field recibe valores contradictorios.
  2. Filtra answers persistibles (evidence_ok AND confidence >= umbral).
  3. Enriquece cada question con políticas (requires_rag, requires_human,
     risk_level, preferred_sources).

Las POLÍTICAS son deterministas (no las decide el LLM). Hoy viven en el mapa
INTENT_POLICIES de este módulo; en la fase de reposicionamiento de Neo4j se
migran al grafo sin cambiar la interfaz de enrich_classification.

Aislado: no toca el flujo de orquestación.
"""
from __future__ import annotations

import os
from typing import Any

# Umbral de confianza para persistir un answer (además del check de evidence).
CONFIDENCE_THRESHOLD = float(os.getenv("INTENT_CONFIDENCE_THRESHOLD", "0.85"))

# Mapa de políticas por question-intent.
# TEMPORAL: migra a Neo4j (nodos Intent/Policy/InternalSource) en la fase de
# reposicionamiento del grafo. La interfaz de enrich_classification no cambia.
# preferred_sources = nombre de archivo tal cual el metadata 'source' en Chroma.
INTENT_POLICIES: dict[str, dict[str, Any]] = {
    "pay_question": {
        "requires_rag": True, "requires_human": False, "risk_level": "low",
        "preferred_sources": ["01_pago_prestaciones.md"],
    },
    "logistics_question": {
        "requires_rag": True, "requires_human": False, "risk_level": "low",
        "preferred_sources": ["04_bases_rutas.md"],
    },
    "documents_question": {
        "requires_rag": True, "requires_human": False, "risk_level": "low",
        "preferred_sources": ["02_documentos_requisitos.md"],
    },
    "vacancy_question": {
        "requires_rag": True, "requires_human": False, "risk_level": "low",
        "preferred_sources": ["00_politicas_generales.md"],
    },
    # safety_intent se resuelve por is_admission (ver _enrich_question).
}

# Fields donde un valor positivo descarta el valor "ninguno".
# Ej: "no traigo cartas pero tengo semanas imss" → semanas_imss gana, "ninguno" se descarta.
_POSITIVE_OVERRIDES_NONE = {"documents.proof"}

_RISK_RANK = {"low": 1, "medium": 2, "high": 3}


def _resolve_answer_conflicts(answers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Cuando un field aparece varias veces, deja un solo answer por field.

    Reglas:
    - Para fields en _POSITIVE_OVERRIDES_NONE: un valor != 'ninguno' descarta 'ninguno'.
    - Entre los restantes: gana el de mayor confidence; en empate, el primero.
    """
    by_field: dict[str, list[dict[str, Any]]] = {}
    for ans in answers:
        by_field.setdefault(ans["field"], []).append(ans)

    resolved: list[dict[str, Any]] = []
    for field, group in by_field.items():
        if len(group) == 1:
            resolved.append(group[0])
            continue

        candidates = group
        if field in _POSITIVE_OVERRIDES_NONE:
            positives = [a for a in group if str(a.get("value")).lower() != "ninguno"]
            if positives:
                candidates = positives

        winner = max(candidates, key=lambda a: a.get("confidence") or 0.0)
        winner = dict(winner)
        if len(group) > 1:
            winner["conflict_resolved_from"] = [
                {"value": a.get("value"), "confidence": a.get("confidence")} for a in group
            ]
        resolved.append(winner)

    return resolved


def _enrich_question(q: dict[str, Any]) -> dict[str, Any]:
    """Añade políticas a una question según su intent (y is_admission para safety)."""
    intent = q.get("intent")
    enriched = dict(q)

    if intent == "safety_intent":
        if q.get("is_admission"):
            policy = {"requires_rag": False, "requires_human": True, "risk_level": "high",
                      "preferred_sources": []}
        else:
            policy = {"requires_rag": True, "requires_human": False, "risk_level": "medium",
                      "preferred_sources": ["03_seguridad_antidoping.md"]}
    else:
        policy = INTENT_POLICIES.get(intent, {
            "requires_rag": False, "requires_human": False, "risk_level": "low",
            "preferred_sources": [],
        })

    enriched.update(policy)
    return enriched


def enrich_classification(classification: dict[str, Any]) -> dict[str, Any]:
    """Valida, resuelve y enriquece una clasificación multi-intent.

    Devuelve:
      - answers_to_persist: pasaron evidence_ok AND confidence >= umbral (sin conflictos)
      - answers_rejected: con razón (no_evidence / low_confidence)
      - questions: enriquecidas con políticas
      - requires_human / max_risk_level: agregados de las questions
    """
    answers = classification.get("answers") or []

    # 1. Resolver conflictos de field
    resolved = _resolve_answer_conflicts(answers)

    # 2. Filtrar persistibles
    to_persist: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for ans in resolved:
        if not ans.get("evidence_ok"):
            rejected.append({**ans, "reject_reason": "no_evidence"})
        elif (ans.get("confidence") or 0.0) < CONFIDENCE_THRESHOLD:
            rejected.append({**ans, "reject_reason": "low_confidence"})
        else:
            to_persist.append(ans)

    # 3. Enriquecer questions
    questions = [_enrich_question(q) for q in (classification.get("questions") or [])]

    requires_human = any(q.get("requires_human") for q in questions)
    max_risk = "low"
    for q in questions:
        if _RISK_RANK.get(q.get("risk_level", "low"), 1) > _RISK_RANK.get(max_risk, 1):
            max_risk = q.get("risk_level", "low")

    return {
        "message_type": classification.get("message_type"),
        "primary_intent": classification.get("primary_intent"),
        "secondary_intents": classification.get("secondary_intents") or [],
        "answers_to_persist": to_persist,
        "answers_rejected": rejected,
        "questions": questions,
        "requires_human": requires_human,
        "max_risk_level": max_risk,
    }
