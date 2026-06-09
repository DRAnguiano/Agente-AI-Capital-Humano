"""QA harness read-only para la matriz de preguntas reales.

Lee tests/fixtures/response_qa/matriz_qa.csv y produce un reporte CSV con el
resultado de cada caso contra el sistema actual.

Modos:
  --mode dry       (default) Solo verifica frases_prohibidas contra
                   agent_answer_historica. Sin LLM, sin DB.
  --mode classify  Llama classify_message() por cada pregunta y compara
                   primary_intent contra route_esperada_sugerida.
                   Requiere GROQ_API_KEY en entorno.
  --mode full      classify + plan_and_respond. Requiere GROQ_API_KEY.

Uso:
  python scripts/qa_response_matrix.py
  python scripts/qa_response_matrix.py --output reports/qa_dry.csv --limit 25
  python scripts/qa_response_matrix.py --mode classify --limit 50
  python scripts/qa_response_matrix.py --mode classify --route-filter vacante_info_general
  python scripts/qa_response_matrix.py --mode classify --priority Alta

READ-ONLY: no escribe en Chatwoot, no muta DB, no envía mensajes reales.
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
import time
import traceback
from pathlib import Path
from typing import Any

# ── Paths ─────────────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT = REPO_ROOT / "tests/fixtures/response_qa/matriz_qa.csv"
DEFAULT_OUTPUT = REPO_ROOT / "reports/qa_response_matrix.csv"

# ── Frases prohibidas globales ─────────────────────────────────────────────────
# Verificación literal; no regex. Cualquier respuesta que contenga una de estas
# frases falla independientemente del modo.

GLOBAL_FORBIDDEN: list[str] = [
    "quinta rueda/full",
    "sencillo (escuelita)",
    "Capital Humano valida viabilidad",
    "disponible_acudir",
    "caduca",
    "caducidad",
    "tenemos convenio con CECATI",
]

# ── Mapeo route → intents del clasificador ────────────────────────────────────
# Fuente: openspec/changes/response-qa-intent-classification/proposal.md
# None = wildcard (cualquier intent es aceptable para esta ruta).

ROUTE_TO_INTENTS: dict[str, set[str] | None] = {
    "vacante_info_general":             {"vacancy_question", "greeting", "candidate_interest", "acknowledgement"},
    "ubicacion_base_traslado":          {"logistics_question", "candidate_answer"},
    "documentos_requisitos":            {"documents_question", "candidate_answer"},
    "pago_condiciones":                 {"pay_question"},
    "objetivo_full_sencillo":           {"candidate_answer"},
    "seguimiento_llamada":              {"candidate_interest", "acknowledgement", "candidate_answer"},
    "jerga_ambigua_falta_unidad":       {"candidate_answer"},
    "considerar_operador_b1":           {"logistics_question", "vacancy_question", "candidate_answer"},
    "cecati_sugerido":                  {"vacancy_question", "candidate_answer"},
    "considerar_escuelita_transmontes": {"vacancy_question", "candidate_answer"},
    "reingreso_verificar":              {"reingreso"},
    "otros_rag":                        None,
}

# Columnas de salida del reporte
OUTPUT_COLUMNS = [
    "qa_id", "candidate_question", "route_esperada_sugerida",
    "labels_esperadas_sugeridas", "prioridad",
    "actual_intent", "actual_labels", "actual_reply",
    "pass_forbidden_phrases", "pass_route",
    "status", "comment",
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_forbidden(cell: str | None) -> list[str]:
    if not cell:
        return []
    return [f.strip() for f in cell.split(";") if f.strip()]


def _check_forbidden(text: str | None, forbidden: list[str]) -> tuple[bool, list[str]]:
    """Retorna (all_clear, lista_de_frases_encontradas). Verificación literal, sin regex."""
    if not text:
        return True, []
    found = [f for f in forbidden if f.lower() in text.lower()]
    return len(found) == 0, found


def _route_pass(actual_intent: str | None, route: str) -> bool:
    expected = ROUTE_TO_INTENTS.get(route)
    if expected is None:
        return True
    return actual_intent in expected


def _status(pass_forbidden: bool, pass_route: bool, mode: str, had_error: bool) -> str:
    if had_error:
        return "ERROR"
    if not pass_forbidden:
        return "FAIL"
    if mode == "dry":
        return "PASS" if pass_forbidden else "FAIL"
    if pass_forbidden and pass_route:
        return "PASS"
    if pass_forbidden and not pass_route:
        return "REVIEW"
    return "FAIL"


# ── Modo dry: solo frases prohibidas contra answer histórica ──────────────────

def run_dry(row: dict[str, str]) -> dict[str, Any]:
    historic = row.get("agent_answer_historica") or ""
    per_row_forbidden = _parse_forbidden(row.get("frases_prohibidas"))
    all_forbidden = GLOBAL_FORBIDDEN + [f for f in per_row_forbidden if f not in GLOBAL_FORBIDDEN]

    pass_forb, found = _check_forbidden(historic, all_forbidden)

    comment = ""
    if found:
        comment = f"Frases prohibidas en respuesta histórica: {found}"

    return {
        "actual_intent": "",
        "actual_labels": "",
        "actual_reply": (historic or "")[:300],
        "pass_forbidden_phrases": pass_forb,
        "pass_route": True,
        "status": "PASS" if pass_forb else "FAIL",
        "comment": comment,
    }


# ── Modo classify: classify_message + comparación de ruta ────────────────────

def run_classify(row: dict[str, str]) -> dict[str, Any]:
    from app.knowledge.intent_classifier import classify_message  # noqa: PLC0415

    question = row.get("candidate_question") or ""
    route = row.get("route_esperada_sugerida") or ""

    try:
        result = classify_message(question)
    except Exception as exc:
        return {
            "actual_intent": "ERROR",
            "actual_labels": "",
            "actual_reply": "",
            "pass_forbidden_phrases": True,
            "pass_route": False,
            "status": "ERROR",
            "comment": f"classify_message error: {type(exc).__name__}: {exc}",
        }

    actual_intent = result.get("primary_intent") or ""
    pass_route = _route_pass(actual_intent, route)

    per_row_forbidden = _parse_forbidden(row.get("frases_prohibidas"))
    all_forbidden = GLOBAL_FORBIDDEN + [f for f in per_row_forbidden if f not in GLOBAL_FORBIDDEN]
    pass_forb, found = _check_forbidden(row.get("agent_answer_historica") or "", all_forbidden)

    comment_parts = []
    if found:
        comment_parts.append(f"Frases prohibidas: {found}")
    if not pass_route:
        comment_parts.append(
            f"Intent '{actual_intent}' no esperado para ruta '{route}' "
            f"(esperados: {ROUTE_TO_INTENTS.get(route)})"
        )

    return {
        "actual_intent": actual_intent,
        "actual_labels": "",
        "actual_reply": "",
        "pass_forbidden_phrases": pass_forb,
        "pass_route": pass_route,
        "status": _status(pass_forb, pass_route, "classify", False),
        "comment": "; ".join(comment_parts),
    }


# ── Modo full: classify + plan_and_respond ────────────────────────────────────

def run_full(row: dict[str, str]) -> dict[str, Any]:
    from app.knowledge.intent_classifier import classify_message  # noqa: PLC0415
    from app.knowledge.intent_enricher import enrich_classification  # noqa: PLC0415
    from app.knowledge.intent_orchestrator import plan_and_respond  # noqa: PLC0415

    question = row.get("candidate_question") or ""
    route = row.get("route_esperada_sugerida") or ""

    try:
        classification = classify_message(question)
        enriched = enrich_classification(classification)
        plan = plan_and_respond(enriched, question, {})
    except Exception as exc:
        return {
            "actual_intent": "ERROR",
            "actual_labels": "",
            "actual_reply": "",
            "pass_forbidden_phrases": True,
            "pass_route": False,
            "status": "ERROR",
            "comment": f"full pipeline error: {type(exc).__name__}: {exc}",
        }

    actual_intent = classification.get("primary_intent") or ""
    actual_reply = (plan.get("response_text") or "")[:400]

    per_row_forbidden = _parse_forbidden(row.get("frases_prohibidas"))
    all_forbidden = GLOBAL_FORBIDDEN + [f for f in per_row_forbidden if f not in GLOBAL_FORBIDDEN]

    pass_forb_hist, found_hist = _check_forbidden(row.get("agent_answer_historica") or "", all_forbidden)
    pass_forb_new, found_new = _check_forbidden(actual_reply, all_forbidden)
    pass_forb = pass_forb_hist and pass_forb_new

    pass_route = _route_pass(actual_intent, route)

    comment_parts = []
    if found_hist:
        comment_parts.append(f"Frases prohibidas en histórico: {found_hist}")
    if found_new:
        comment_parts.append(f"Frases prohibidas en respuesta nueva: {found_new}")
    if not pass_route:
        comment_parts.append(
            f"Intent '{actual_intent}' ≠ ruta '{route}' "
            f"(esperados: {ROUTE_TO_INTENTS.get(route)})"
        )

    return {
        "actual_intent": actual_intent,
        "actual_labels": "",
        "actual_reply": actual_reply,
        "pass_forbidden_phrases": pass_forb,
        "pass_route": pass_route,
        "status": _status(pass_forb, pass_route, "full", False),
        "comment": "; ".join(comment_parts),
    }


# ── Runner principal ──────────────────────────────────────────────────────────

RUN_FN = {
    "dry": run_dry,
    "classify": run_classify,
    "full": run_full,
}


def run(
    input_path: Path,
    output_path: Path,
    mode: str,
    limit: int,
    route_filter: str | None,
    priority_filter: str | None,
    dry_run: bool,
) -> None:
    with open(input_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    if route_filter:
        rows = [r for r in rows if r.get("route_esperada_sugerida") == route_filter]
    if priority_filter:
        rows = [r for r in rows if (r.get("prioridad") or "").lower() == priority_filter.lower()]
    if limit > 0:
        rows = rows[:limit]

    fn = RUN_FN[mode]
    results: list[dict[str, Any]] = []
    counters: dict[str, int] = {}

    for i, row in enumerate(rows):
        if not dry_run:
            if mode in ("classify", "full"):
                time.sleep(0.2)  # rate-limit suave para Groq

        try:
            result = fn(row)
        except Exception:
            result = {
                "actual_intent": "ERROR",
                "actual_labels": "",
                "actual_reply": "",
                "pass_forbidden_phrases": False,
                "pass_route": False,
                "status": "ERROR",
                "comment": traceback.format_exc(limit=3),
            }

        status = result["status"]
        counters[status] = counters.get(status, 0) + 1

        out_row = {
            "qa_id": row.get("qa_id", ""),
            "candidate_question": (row.get("candidate_question") or "")[:200],
            "route_esperada_sugerida": row.get("route_esperada_sugerida", ""),
            "labels_esperadas_sugeridas": row.get("labels_esperadas_sugeridas", ""),
            "prioridad": row.get("prioridad", ""),
            **{k: result.get(k, "") for k in OUTPUT_COLUMNS if k not in row},
        }
        # Asegurar que todas las columnas de salida estén presentes
        for col in OUTPUT_COLUMNS:
            if col not in out_row:
                out_row[col] = result.get(col, row.get(col, ""))

        results.append(out_row)

        if (i + 1) % 25 == 0:
            print(f"  {i+1}/{len(rows)} procesados ...", file=sys.stderr)

    # Escribir reporte
    if not dry_run:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=OUTPUT_COLUMNS)
            writer.writeheader()
            writer.writerows(results)
        print(f"\nReporte guardado: {output_path}")

    # Resumen
    total = len(results)
    print(f"\n=== Resumen (modo={mode}, total={total}) ===")
    for status in ("PASS", "FAIL", "REVIEW", "GAP_FUTURO", "ERROR"):
        n = counters.get(status, 0)
        if n:
            pct = round(100 * n / total, 1) if total else 0
            print(f"  {status:15s} {n:4d}  ({pct}%)")

    # Top 10 fallos
    fails = [r for r in results if r.get("status") in ("FAIL", "ERROR", "REVIEW")]
    if fails:
        print(f"\n=== Top fallos ({len(fails)} total) ===")
        for r in fails[:10]:
            print(f"  [{r['status']}] {r['qa_id']} | route={r['route_esperada_sugerida']} | intent={r['actual_intent']}")
            if r.get("comment"):
                print(f"         {r['comment'][:120]}")

    # Fallos por ruta
    from collections import Counter
    fail_by_route: Counter[str] = Counter(
        r["route_esperada_sugerida"] for r in fails
    )
    if fail_by_route:
        print("\n=== Fallos por ruta ===")
        for route, n in fail_by_route.most_common():
            print(f"  {n:3d}  {route}")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--mode", choices=["dry", "classify", "full"], default="dry")
    parser.add_argument("--limit", type=int, default=0, help="0 = todos los casos")
    parser.add_argument("--route-filter", help="Filtrar por route_esperada_sugerida exacta")
    parser.add_argument("--priority", help="Filtrar por prioridad (Alta, Media)")
    parser.add_argument("--dry-run", action="store_true", help="No escribe archivos de salida")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"ERROR: No se encontró input: {input_path}", file=sys.stderr)
        sys.exit(1)

    if args.mode in ("classify", "full") and not os.getenv("GROQ_API_KEY"):
        print("ERROR: GROQ_API_KEY no definida. Usar --mode dry para correr sin LLM.", file=sys.stderr)
        sys.exit(1)

    if args.mode in ("classify", "full"):
        sys.path.insert(0, str(REPO_ROOT))

    run(
        input_path=input_path,
        output_path=Path(args.output),
        mode=args.mode,
        limit=args.limit,
        route_filter=args.route_filter,
        priority_filter=args.priority,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
