"""Shadow mode del pipeline multi-intent (Fase 4).

Corre el pipeline (classify → enrich → plan) EN PARALELO al flujo real, con los
facts reales del lead, y registra en logs qué habría respondido — SIN afectar lo
que recibe el candidato. Permite comparar el multi-intent contra el sistema actual
con tráfico real antes de activarlo.

Controlado por el flag MULTI_INTENT_SHADOW (default off). Nunca lanza excepción:
si algo falla, loggea el error y el flujo real sigue intacto.
"""
from __future__ import annotations

import json
import time
from typing import Any


def _facts_to_known(lead_memory: dict[str, Any] | None) -> dict[str, str]:
    """Convierte lead_memory.facts (lista) al dict {group.key: value} que usa el pipeline."""
    known: dict[str, str] = {}
    for row in (lead_memory or {}).get("facts") or []:
        if isinstance(row, dict) and row.get("fact_group") and row.get("fact_key"):
            known[f"{row['fact_group']}.{row['fact_key']}"] = str(row.get("fact_value"))
    return known


def run_shadow(message: str, lead_memory: dict[str, Any] | None, actual_reply: str) -> None:
    """Ejecuta el pipeline en shadow y loggea la comparación. Nunca propaga errores."""
    try:
        from app.knowledge.intent_classifier import classify_message
        from app.knowledge.intent_enricher import enrich_classification
        from app.knowledge.intent_orchestrator import plan_and_respond

        started = time.perf_counter()
        known = _facts_to_known(lead_memory)

        classification = classify_message(message)
        enriched = enrich_classification(classification)
        plan = plan_and_respond(enriched, message, known)
        elapsed_ms = round((time.perf_counter() - started) * 1000, 1)

        print(
            "[MULTI_INTENT_SHADOW] " + json.dumps(
                {
                    "message": message[:200],
                    "message_type": classification.get("message_type"),
                    "primary_intent": classification.get("primary_intent"),
                    "secondary_intents": classification.get("secondary_intents"),
                    "facts_to_persist": [
                        {"field": a["field"], "value": a["value"]}
                        for a in plan.get("facts_to_persist") or []
                    ],
                    "action_order": plan.get("recommended_action_order"),
                    "core_completeness": plan.get("core_completeness"),
                    "handoff": plan.get("handoff"),
                    "shadow_reply": (plan.get("response_text") or "")[:400],
                    "actual_reply": (actual_reply or "")[:400],
                    "shadow_ms": elapsed_ms,
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
    except Exception as exc:
        print(f"[MULTI_INTENT_SHADOW_ERROR] {type(exc).__name__}: {exc}", flush=True)
