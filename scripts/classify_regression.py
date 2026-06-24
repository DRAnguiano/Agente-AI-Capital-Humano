"""Tarea 9.3 — suite de regresión `/classify` con clasificación LLM real.

Corre los casos reales de `tests/fixtures/multi_intent/regression_9_3.jsonl` por el
pipeline multi-intent completo (classify → enrich → plan_and_respond + plan_turn) y
verifica las expectativas de cada caso. REQUIERE GROQ_API_KEY (el clasificador es LLM).

Pensado para correr vía api-test (código actual + .env con Groq + red a Postgres):

    docker compose --profile test run --rm api-test python scripts/classify_regression.py
    docker compose --profile test run --rm api-test python scripts/classify_regression.py --json
    docker compose --profile test run --rm api-test python scripts/classify_regression.py --only 9.3.3a 9.3.11

Es read-only: no persiste en Postgres ni envía a Chatwoot. El LLM es no determinista,
así que esto MIDE y reporta; cuando un caso falla, imprime lo que devolvió para afinar
prompt/few-shot o la expectativa.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

# Raíz del repo en sys.path para que `import app...` funcione sin depender de
# PYTHONPATH (el script vive en /app/scripts; la raíz es su parents[1]).
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

FIXTURES = _REPO_ROOT / "tests" / "fixtures" / "multi_intent" / "regression_9_3.jsonl"


def _load_cases(path: Path) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            cases.append(json.loads(line))
    return cases


def run_case(case: dict[str, Any]) -> dict[str, Any]:
    """Corre un caso por el pipeline y devuelve {ok, failures, observed}."""
    # Imports diferidos: solo al ejecutar (necesitan Groq/entorno).
    from app.knowledge.intent_classifier import classify_message
    from app.knowledge.intent_enricher import enrich_classification
    from app.knowledge.turn_planner import plan_turn

    msg = case["message"]
    known = dict(case.get("known_facts") or {})
    last_q = case.get("last_bot_question")
    exp = case.get("expect") or {}

    classification = classify_message(msg, last_bot_question=last_q)
    enriched = enrich_classification(classification)
    turn = plan_turn(known, enriched.get("answers_to_persist") or [], msg)

    # plan_and_respond solo si el caso evalúa handoff/no_profiling: para preguntas RAG
    # dispara el camino Groq-70B+Chroma (lento, api-test no monta Chroma). greeting/señales
    # no entran a ese camino, así que aquí es barato.
    plan: dict[str, Any] = {}
    if "handoff" in exp or "no_profiling" in exp:
        from app.knowledge.intent_orchestrator import plan_and_respond
        plan = plan_and_respond(enriched, msg, known)

    answers = enriched.get("answers_to_persist") or []
    answer_pairs = {(a.get("field"), str(a.get("value")).lower()) for a in answers}
    intents_present = (
        {classification.get("primary_intent")}
        | set(classification.get("secondary_intents") or [])
        | {q.get("intent") for q in (classification.get("questions") or [])}
    )

    failures: list[str] = []

    if "primary_intent_in" in exp and classification.get("primary_intent") not in exp["primary_intent_in"]:
        failures.append(f"primary_intent={classification.get('primary_intent')!r} no en {exp['primary_intent_in']}")

    if "intent_present" in exp and exp["intent_present"] not in intents_present:
        failures.append(f"intent {exp['intent_present']!r} ausente (presentes: {sorted(i for i in intents_present if i)})")

    for field, value in exp.get("answers_include", []):
        if (field, str(value).lower()) not in answer_pairs:
            failures.append(f"answer faltante {field}={value!r} (answers: {sorted(answer_pairs)})")

    for field, value in (exp.get("facts_after_includes") or {}).items():
        if str(turn["facts_after"].get(field)).lower() != str(value).lower():
            failures.append(f"facts_after[{field}]={turn['facts_after'].get(field)!r} != {value!r}")

    for field, value in (exp.get("facts_after_unchanged") or {}).items():
        if str(turn["facts_after"].get(field)) != str(value):
            failures.append(f"facts_after[{field}]={turn['facts_after'].get(field)!r} cambió (esperado intacto {value!r})")

    for field in exp.get("not_reask", []):
        if turn["next_question_field"] == field:
            failures.append(f"repregunta el campo {field!r} (next_question_field)")

    if "handoff" in exp and bool(plan.get("handoff")) != bool(exp["handoff"]):
        failures.append(f"handoff={plan.get('handoff')!r} != {exp['handoff']!r}")

    if exp.get("no_profiling"):
        actions = plan.get("recommended_action_order") or []
        if "emit_funnel_question" in actions:
            failures.append(f"arrancó perfilamiento en mensaje fuera de tema (acciones: {actions})")

    if "memory_resolution" in exp:
        claim = turn.get("memory_claim")
        got = claim.get("resolution") if claim else None
        if got != exp["memory_resolution"]:
            failures.append(f"memory_resolution={got!r} != {exp['memory_resolution']!r}")

    return {
        "id": case.get("id"),
        "desc": case.get("desc"),
        "ok": not failures,
        "failures": failures,
        "observed": {
            "primary_intent": classification.get("primary_intent"),
            "secondary_intents": classification.get("secondary_intents"),
            "answers_to_persist": [{"field": a.get("field"), "value": a.get("value")} for a in answers],
            "next_question_field": turn.get("next_question_field"),
            "memory_claim": turn.get("memory_claim"),
            "handoff": plan.get("handoff"),
            "action_order": plan.get("recommended_action_order"),
            "shadow_reply": (plan.get("response_text") or "")[:200],
        },
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Regresión /classify multi-intent (9.3). Requiere GROQ_API_KEY.")
    ap.add_argument("--json", action="store_true", help="Salida JSON.")
    ap.add_argument("--only", nargs="*", default=None, metavar="ID", help="Correr solo estos ids de caso.")
    ap.add_argument("--fixtures", default=str(FIXTURES), help="Ruta al jsonl de casos.")
    args = ap.parse_args(argv)

    if not os.getenv("GROQ_API_KEY"):
        print("ERROR: falta GROQ_API_KEY en el entorno (el clasificador es LLM).")
        return 2

    cases = _load_cases(Path(args.fixtures))
    if args.only:
        cases = [c for c in cases if c.get("id") in set(args.only)]

    results = [run_case(c) for c in cases]
    passed = sum(1 for r in results if r["ok"])

    if args.json:
        print(json.dumps({"passed": passed, "total": len(results), "results": results},
                         ensure_ascii=False, indent=2))
    else:
        for r in results:
            mark = "PASS" if r["ok"] else "FAIL"
            print(f"[{mark}] {r['id']}  {r['desc']}")
            if not r["ok"]:
                for f in r["failures"]:
                    print(f"        - {f}")
                obs = r["observed"]
                print(f"        observed: intent={obs['primary_intent']} "
                      f"answers={obs['answers_to_persist']} next={obs['next_question_field']} "
                      f"memory={obs['memory_claim']}")
        print(f"\n{passed}/{len(results)} casos PASS")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
