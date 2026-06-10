"""QA harness read-only para la matriz de preguntas reales.

Lee tests/fixtures/response_qa/matriz_qa.csv y produce un reporte CSV con el
resultado de cada caso contra el sistema actual.

Modos:
  --mode dry       (default) Solo verifica frases_prohibidas contra
                   agent_answer_historica. Sin LLM, sin DB.
  --mode classify  Llama classify_message() por cada pregunta y compara
                   primary/secondary intents contra route_esperada_sugerida.
                   Requiere GROQ_API_KEY en entorno.
  --mode full      classify + plan_and_respond. Requiere GROQ_API_KEY.

mapping_status:
  PASS_STRONG    primary o secondary coincide con intent fuerte de la ruta.
  PASS_WEAK      coincide solo por intent amplio; falta business_route para confirmar.
  REVIEW_MAPPING ningún match; conversacionalmente razonable pero no confirmado.
  CONTRACT_GAP   ruta sin mapping definido.
  ERROR          excepción técnica.

Límites Groq (llama-3.1-8b-instant, tier free):
  RPM: 30 | TPM: 6000 | Daily: 500K tokens
  Default --requests-per-minute 1.5 → sleep_by_rpm=40s → effective 40s

Corrida por bloques:
  --start-index 0  --limit 25 --append --output reports/qa_all.csv
  --start-index 25 --limit 25 --append --output reports/qa_all.csv

READ-ONLY: no escribe en Chatwoot, no muta DB, no envía mensajes reales.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
import traceback
from collections import Counter
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

# ── Mapping de intents por ruta (evaluación QA — no lógica productiva) ────────
#
# ROUTE_STRONG: intents que solos (primary o secondary) confirman la ruta → PASS_STRONG
# ROUTE_WEAK:   intents que coinciden ampliamente pero necesitan business_route → PASS_WEAK
# None en ROUTE_STRONG = wildcard (otros_rag) → siempre PASS_STRONG
#
# Regla de evaluación:
#  1. any(intent in ROUTE_STRONG[route])  → PASS_STRONG (source=primary|secondary)
#  2. any(intent in ROUTE_WEAK[route])    → PASS_WEAK   (source=primary|secondary)
#  3. ninguno                             → REVIEW_MAPPING
#  4. route no en ninguna tabla           → CONTRACT_GAP

ROUTE_STRONG: dict[str, set[str] | None] = {
    "vacante_info_general": {
        "greeting", "candidate_interest", "vacancy_question", "acknowledgement",
    },
    "ubicacion_base_traslado": {
        "logistics_question", "candidate_answer",
    },
    "documentos_requisitos": {
        "documents_question", "document_submission", "candidate_answer",
    },
    "pago_condiciones": {
        "pay_question",
    },
    "objetivo_full_sencillo": {
        "candidate_answer",
    },
    "considerar_escuelita_transmontes": {
        "candidate_answer", "vacancy_question",
    },
    "jerga_ambigua_falta_unidad": {
        "candidate_answer",
    },
    "cecati_sugerido": {
        "candidate_answer", "vacancy_question", "greeting",
    },
    "considerar_operador_b1": {
        "candidate_answer", "candidate_interest",
    },
    "seguimiento_llamada": {
        "candidate_answer", "acknowledgement", "candidate_interest",
    },
    "reingreso_verificar": {
        "reingreso", "candidate_answer", "candidate_interest", "vacancy_question",
    },
    "otros_rag": None,  # wildcard
}

# ROUTE_WEAK: match amplio → PASS_WEAK (no CONTRACT_GAP, pero necesita confirmación)
ROUTE_WEAK: dict[str, set[str]] = {
    "vacante_info_general":             {"documents_question"},
    "ubicacion_base_traslado":          {"vacancy_question"},
    "documentos_requisitos":            {"vacancy_question"},
    "pago_condiciones":                 {"vacancy_question", "candidate_interest"},
    "objetivo_full_sencillo":           {"candidate_interest", "vacancy_question", "logistics_question"},
    "considerar_escuelita_transmontes": set(),   # document_submission solo → REVIEW_MAPPING
    "jerga_ambigua_falta_unidad":       {"vacancy_question", "logistics_question"},
    "cecati_sugerido":                  set(),
    "considerar_operador_b1":           {"vacancy_question"},
    "seguimiento_llamada":              set(),   # out_of_scope removido
    "reingreso_verificar":              set(),
}

OUTPUT_COLUMNS = [
    "qa_id", "candidate_question", "route_esperada_sugerida",
    "labels_esperadas_sugeridas", "prioridad",
    # Compat
    "actual_intent",
    # Extendidas
    "actual_primary_intent",
    "actual_secondary_intents",
    "actual_answers",
    "actual_business_route",
    "actual_labels",
    "actual_reply",
    "pass_forbidden_phrases",
    # Evaluación de ruta
    "mapping_status",
    "mapping_strength",
    "match_source",
    "matched_intents",
    # Hechos de negocio extraídos del texto
    "profile_vehicle_type",
    "business_fact_match",
    # Compat
    "pass_route",
    "status",
    "comment",
]


# ── Helpers — forbidden phrases ───────────────────────────────────────────────

def _parse_forbidden(cell: str | None) -> list[str]:
    if not cell:
        return []
    return [f.strip() for f in cell.split(";") if f.strip()]


def _check_forbidden(text: str | None, forbidden: list[str]) -> tuple[bool, list[str]]:
    """Verificación literal, sin regex."""
    if not text:
        return True, []
    found = [f for f in forbidden if f.lower() in text.lower()]
    return len(found) == 0, found


# ── Evaluación de ruta ────────────────────────────────────────────────────────

def _evaluate_route(
    primary: str | None,
    secondary: list[str],
    route: str,
) -> tuple[str, str, list[str]]:
    """Retorna (mapping_status, match_source, matched_intents).

    Prioridad:
      1. any intent in ROUTE_STRONG[route] → PASS_STRONG
      2. any intent in ROUTE_WEAK[route]   → PASS_WEAK
      3. sin match                         → REVIEW_MAPPING
      4. route no en ninguna tabla         → CONTRACT_GAP
    """
    if route not in ROUTE_STRONG and route not in ROUTE_WEAK:
        return "CONTRACT_GAP", "none", []

    strong = ROUTE_STRONG.get(route)

    # wildcard
    if strong is None:
        return "PASS_STRONG", "wildcard", []

    all_intents = [(primary, "primary")] + [(s, "secondary") for s in secondary]

    # 1. STRONG
    strong_hits = [(intent, src) for intent, src in all_intents if intent in strong]
    if strong_hits:
        matched = [i for i, _ in strong_hits]
        source = "primary" if any(s == "primary" for _, s in strong_hits) else "secondary"
        return "PASS_STRONG", source, matched

    # 2. WEAK
    weak = ROUTE_WEAK.get(route, set())
    weak_hits = [(intent, src) for intent, src in all_intents if intent in weak]
    if weak_hits:
        matched = [i for i, _ in weak_hits]
        source = "primary" if any(s == "primary" for _, s in weak_hits) else "secondary"
        return "PASS_WEAK", source, matched

    return "REVIEW_MAPPING", "none", []


def _compat_status(mapping_status: str, pass_f: bool) -> tuple[bool, str]:
    """Retorna (pass_route_bool, status_compat) para columnas de compatibilidad."""
    if not pass_f:
        return False, "FAIL"
    if mapping_status in ("PASS_STRONG", "PASS_WEAK"):
        return True, "PASS"
    if mapping_status in ("REVIEW_MAPPING", "CONTRACT_GAP"):
        return False, "REVIEW"
    return False, "ERROR"


# ── Extracción de hechos de negocio (read-only, sin regex de intents) ─────────

def _extract_vehicle_fact(question: str) -> tuple[str, str]:
    """Extrae vehicle_type del texto usando el catálogo de dominio del proyecto.

    Retorna (profile_vehicle_type, business_fact_match):
      - profile_vehicle_type: 'full' | 'sencillo' | 'quinta_rueda' | etc, o ''
      - business_fact_match:  'vehicle_type_confirmed' si aplica objetivo, si no ''

    Reutiliza normalize_vehicle + applies_objetivo_full_sencillo del catálogo.
    Importación lazy: no falla si app/ no está en sys.path (modo dry sin app).
    """
    try:
        from app.knowledge.normalize_domain_values import (  # noqa: PLC0415
            applies_objetivo_full_sencillo,
            normalize_vehicle,
        )
    except ImportError:
        return "", ""

    resolution = normalize_vehicle(question)
    if resolution is None:
        return "", ""

    vt = resolution.value or resolution.domain or ""
    bfm = "vehicle_type_confirmed" if applies_objetivo_full_sencillo(resolution) else ""
    return vt, bfm


# ── Rate limit / retry ────────────────────────────────────────────────────────

def _is_rate_limit(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "429" in msg or "rate limit" in msg or "ratelimit" in msg or "too many" in msg


def _effective_sleep(rpm: float, tpm: int, tokens_per_call: int, sleep_override: float) -> float:
    sleep_by_rpm = 60.0 / rpm if rpm > 0 else 60.0
    sleep_by_tpm = (60.0 * tokens_per_call / tpm) if tpm > 0 else 60.0
    return max(sleep_override, sleep_by_rpm, sleep_by_tpm)


_ERROR_FIELDS: dict[str, Any] = {
    "actual_intent": "ERROR",
    "actual_primary_intent": "ERROR",
    "actual_secondary_intents": "[]",
    "actual_answers": "[]",
    "actual_business_route": "",
    "actual_labels": "",
    "actual_reply": "",
    "pass_forbidden_phrases": True,
    "mapping_status": "ERROR",
    "mapping_strength": "error",
    "match_source": "none",
    "matched_intents": "[]",
    "profile_vehicle_type": "",
    "business_fact_match": "",
    "pass_route": False,
    "status": "ERROR",
}


def _with_retry(
    fn: Any,
    row: dict[str, str],
    max_retries: int,
    retry_base_seconds: float,
) -> dict[str, Any]:
    last_exc: Exception | None = None
    for attempt in range(1, max_retries + 2):
        try:
            return fn(row)
        except Exception as exc:
            last_exc = exc
            if attempt > max_retries:
                break
            wait = retry_base_seconds * attempt
            tag = "rate-limit" if _is_rate_limit(exc) else type(exc).__name__
            print(f"  [retry {attempt}/{max_retries}] {tag} — espera {wait:.0f}s ...",
                  file=sys.stderr, flush=True)
            time.sleep(wait)

    return {
        **_ERROR_FIELDS,
        "comment": f"agotó {max_retries} reintentos: {type(last_exc).__name__}: {last_exc}",
    }


# ── Builders compartidos ──────────────────────────────────────────────────────

def _build_route_fields(
    primary: str,
    secondary: list[str],
    answers: list[Any],
    route: str,
    historic: str,
    row_forbidden: list[str],
    question: str = "",
) -> dict[str, Any]:
    """Evalúa ruta, verifica frases, construye campos de salida.

    Para rutas donde un hecho de negocio (vehicle_type) confirma la ruta, aplica
    upgrade PASS_WEAK/REVIEW_MAPPING → PASS_STRONG via match_source='business_fact'.
    """
    ms, src, matched = _evaluate_route(primary, secondary, route)

    # ── Business-fact upgrade para objetivo_full_sencillo ──
    profile_vt = ""
    bfm = ""
    if route == "objetivo_full_sencillo" and question:
        profile_vt, bfm = _extract_vehicle_fact(question)
        if bfm == "vehicle_type_confirmed" and ms != "PASS_STRONG":
            ms = "PASS_STRONG"
            src = "business_fact"
            matched = [f"vehicle_type={profile_vt}"]

    all_f = GLOBAL_FORBIDDEN + [f for f in row_forbidden if f not in GLOBAL_FORBIDDEN]
    pass_f, found = _check_forbidden(historic, all_f)
    _, final_status = _compat_status(ms, pass_f)

    comments: list[str] = []
    if found:
        comments.append(f"Frases prohibidas: {found}")
    if ms == "REVIEW_MAPPING":
        comments.append(
            f"Primary intent '{primary}' is conversational for route '{route}'. "
            "Business route requires future business_route classifier or expanded mapping."
        )
    elif ms == "CONTRACT_GAP":
        comments.append(f"Route '{route}' has no mapping defined.")
    elif ms == "PASS_WEAK":
        comments.append(
            f"Weak match via {src} ({matched}). "
            "Business route needs confirmation."
        )

    return {
        "actual_intent": primary,
        "actual_primary_intent": primary,
        "actual_secondary_intents": json.dumps(secondary, ensure_ascii=False),
        "actual_answers": json.dumps(
            [{"field": a.get("field"), "value": a.get("value")} for a in answers],
            ensure_ascii=False,
        ),
        "actual_business_route": "",
        "actual_labels": "",
        "pass_forbidden_phrases": pass_f,
        "mapping_status": ms,
        "mapping_strength": {
            "PASS_STRONG": "strong",
            "PASS_WEAK": "weak",
            "REVIEW_MAPPING": "review",
            "CONTRACT_GAP": "gap",
            "ERROR": "error",
        }.get(ms, ms.lower()),
        "match_source": src,
        "matched_intents": json.dumps(matched, ensure_ascii=False),
        "profile_vehicle_type": profile_vt,
        "business_fact_match": bfm,
        "pass_route": ms in ("PASS_STRONG", "PASS_WEAK"),
        "status": final_status,
        "comment": "; ".join(comments),
    }


# ── Modo dry ──────────────────────────────────────────────────────────────────

def run_dry(row: dict[str, str]) -> dict[str, Any]:
    historic = row.get("agent_answer_historica") or ""
    per_row = _parse_forbidden(row.get("frases_prohibidas"))
    all_f = GLOBAL_FORBIDDEN + [f for f in per_row if f not in GLOBAL_FORBIDDEN]
    pass_f, found = _check_forbidden(historic, all_f)
    return {
        "actual_intent": "",
        "actual_primary_intent": "",
        "actual_secondary_intents": "[]",
        "actual_answers": "[]",
        "actual_business_route": "",
        "actual_labels": "",
        "actual_reply": historic[:300],
        "pass_forbidden_phrases": pass_f,
        "mapping_status": "PASS" if pass_f else "FAIL",
        "mapping_strength": "strong" if pass_f else "fail",
        "match_source": "none",
        "matched_intents": "[]",
        "profile_vehicle_type": "",
        "business_fact_match": "",
        "pass_route": True,
        "status": "PASS" if pass_f else "FAIL",
        "comment": f"Frases prohibidas en histórico: {found}" if found else "",
    }


# ── Modo classify ─────────────────────────────────────────────────────────────

def run_classify(row: dict[str, str]) -> dict[str, Any]:
    from app.knowledge.intent_classifier import classify_message  # noqa: PLC0415

    question = row.get("candidate_question") or ""
    route = row.get("route_esperada_sugerida") or ""

    result = classify_message(question)

    primary: str = result.get("primary_intent") or ""
    secondary: list[str] = result.get("secondary_intents") or []
    answers: list[Any] = result.get("answers") or []
    per_row = _parse_forbidden(row.get("frases_prohibidas"))
    historic = row.get("agent_answer_historica") or ""

    fields = _build_route_fields(primary, secondary, answers, route, historic, per_row, question)
    return {**fields, "actual_reply": ""}


# ── Modo full ─────────────────────────────────────────────────────────────────

def run_full(row: dict[str, str]) -> dict[str, Any]:
    from app.knowledge.intent_classifier import classify_message  # noqa: PLC0415
    from app.knowledge.intent_enricher import enrich_classification  # noqa: PLC0415
    from app.knowledge.intent_orchestrator import plan_and_respond  # noqa: PLC0415

    question = row.get("candidate_question") or ""
    route = row.get("route_esperada_sugerida") or ""

    classification = classify_message(question)
    enriched = enrich_classification(classification)
    plan = plan_and_respond(enriched, question, {})

    primary: str = classification.get("primary_intent") or ""
    secondary: list[str] = classification.get("secondary_intents") or []
    answers: list[Any] = classification.get("answers") or []
    actual_reply = (plan.get("response_text") or "")[:400]
    per_row = _parse_forbidden(row.get("frases_prohibidas"))
    historic = row.get("agent_answer_historica") or ""

    fields = _build_route_fields(primary, secondary, answers, route, historic, per_row, question)

    # También chequear frases prohibidas en la respuesta nueva
    all_f = GLOBAL_FORBIDDEN + [f for f in per_row if f not in GLOBAL_FORBIDDEN]
    pass_f_new, found_new = _check_forbidden(actual_reply, all_f)
    if not pass_f_new:
        fields["pass_forbidden_phrases"] = False
        fields["status"] = "FAIL"
        existing = fields.get("comment", "")
        extra = f"Frases prohibidas en respuesta nueva: {found_new}"
        fields["comment"] = f"{existing}; {extra}".lstrip("; ") if existing else extra

    return {**fields, "actual_reply": actual_reply}


RUN_FN = {"dry": run_dry, "classify": run_classify, "full": run_full}


# ── Runner principal ──────────────────────────────────────────────────────────

def run(
    input_path: Path,
    output_path: Path,
    mode: str,
    limit: int,
    start_index: int,
    route_filter: str | None,
    priority_filter: str | None,
    rpm: float,
    tpm: int,
    tokens_per_call: int,
    sleep_override: float,
    max_retries: int,
    retry_base_seconds: float,
    daily_budget: int,
    stop_before_budget: bool,
    append: bool,
    dry_run: bool,
) -> None:
    with open(input_path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    if route_filter:
        rows = [r for r in rows if r.get("route_esperada_sugerida") == route_filter]
    if priority_filter:
        rows = [r for r in rows if (r.get("prioridad") or "").lower() == priority_filter.lower()]
    if start_index > 0:
        rows = rows[start_index:]
    if limit > 0:
        rows = rows[:limit]

    needs_llm = mode in ("classify", "full")
    eff_sleep = _effective_sleep(rpm, tpm, tokens_per_call, sleep_override) if needs_llm else 0.0

    if needs_llm and stop_before_budget and daily_budget > 0:
        max_by_budget = daily_budget // tokens_per_call
        if len(rows) > max_by_budget:
            print(
                f"[budget] {len(rows)} × {tokens_per_call} = {len(rows)*tokens_per_call:,} "
                f"> budget {daily_budget:,}. Recortando a {max_by_budget} casos.",
                file=sys.stderr, flush=True,
            )
            rows = rows[:max_by_budget]

    est_tokens = len(rows) * tokens_per_call
    est_min = ((len(rows) - 1) * eff_sleep / 60.0) if len(rows) > 1 else 0.0
    print(f"\nCases selected:              {len(rows)}", file=sys.stderr)
    if needs_llm:
        print(f"Estimated tokens/call:       {tokens_per_call}", file=sys.stderr)
        print(f"Estimated total tokens:      {est_tokens:,}", file=sys.stderr)
        print(f"Daily token budget:          {daily_budget:,}", file=sys.stderr)
        print(
            f"Estimated sleep between:     {eff_sleep:.1f}s  "
            f"(rpm={rpm}, tpm={tpm}, override={sleep_override})",
            file=sys.stderr,
        )
        print(f"Estimated runtime:           ~{est_min:.1f} minutes", file=sys.stderr)
        print(f"Max retries / backoff base:  {max_retries} / {retry_base_seconds}s", file=sys.stderr)
    print("", file=sys.stderr, flush=True)

    fn = RUN_FN[mode]
    write_header = True
    file_mode = "w"
    if not dry_run:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if append and output_path.exists():
            file_mode = "a"
            write_header = False

    out_file = None
    writer = None
    if not dry_run:
        out_file = open(output_path, file_mode, newline="", encoding="utf-8")
        writer = csv.DictWriter(out_file, fieldnames=OUTPUT_COLUMNS)
        if write_header:
            writer.writeheader()

    ms_counters: dict[str, int] = {}
    status_counters: dict[str, int] = {}
    results_summary: list[dict[str, Any]] = []

    try:
        for i, row in enumerate(rows):
            if needs_llm and i > 0:
                time.sleep(eff_sleep)

            try:
                result = _with_retry(fn, row, max_retries, retry_base_seconds) if needs_llm else fn(row)
            except Exception:
                result = {
                    **_ERROR_FIELDS,
                    "comment": traceback.format_exc(limit=3),
                }

            status = result.get("status", "ERROR")
            ms = result.get("mapping_status", "ERROR")
            status_counters[status] = status_counters.get(status, 0) + 1
            ms_counters[ms] = ms_counters.get(ms, 0) + 1

            out_row: dict[str, Any] = {
                "qa_id":                      row.get("qa_id", ""),
                "candidate_question":         (row.get("candidate_question") or "")[:200],
                "route_esperada_sugerida":    row.get("route_esperada_sugerida", ""),
                "labels_esperadas_sugeridas": row.get("labels_esperadas_sugeridas", ""),
                "prioridad":                  row.get("prioridad", ""),
                "actual_intent":              result.get("actual_intent", ""),
                "actual_primary_intent":      result.get("actual_primary_intent", ""),
                "actual_secondary_intents":   result.get("actual_secondary_intents", "[]"),
                "actual_answers":             result.get("actual_answers", "[]"),
                "actual_business_route":      result.get("actual_business_route", ""),
                "actual_labels":              result.get("actual_labels", ""),
                "actual_reply":               result.get("actual_reply", ""),
                "pass_forbidden_phrases":     result.get("pass_forbidden_phrases", ""),
                "mapping_status":             ms,
                "mapping_strength":           result.get("mapping_strength", ""),
                "match_source":               result.get("match_source", ""),
                "matched_intents":            result.get("matched_intents", "[]"),
                "profile_vehicle_type":       result.get("profile_vehicle_type", ""),
                "business_fact_match":        result.get("business_fact_match", ""),
                "pass_route":                 result.get("pass_route", ""),
                "status":                     status,
                "comment":                    result.get("comment", ""),
            }

            if not dry_run and writer and out_file:
                writer.writerow(out_row)
                out_file.flush()

            results_summary.append(out_row)

            if (i + 1) % 5 == 0 or (i + 1) == len(rows):
                done = i + 1
                elapsed_min = done * eff_sleep / 60.0
                print(
                    f"  {done:3d}/{len(rows)}  {ms:20s}  status={status}  "
                    f"~{elapsed_min:.1f}min",
                    file=sys.stderr, flush=True,
                )

    finally:
        if out_file:
            out_file.close()

    if not dry_run:
        print(f"\nReporte guardado: {output_path}")

    total = len(results_summary)

    print(f"\n=== mapping_status (modo={mode}, total={total}) ===")
    for ms in ("PASS_STRONG", "PASS_WEAK", "REVIEW_MAPPING", "CONTRACT_GAP", "ERROR"):
        n = ms_counters.get(ms, 0)
        if n:
            pct = round(100 * n / total, 1) if total else 0
            print(f"  {ms:20s} {n:4d}  ({pct}%)")

    print(f"\n=== status compat ===")
    for st in ("PASS", "REVIEW", "FAIL", "ERROR"):
        n = status_counters.get(st, 0)
        if n:
            pct = round(100 * n / total, 1) if total else 0
            print(f"  {st:10s} {n:4d}  ({pct}%)")

    reviews = [
        r for r in results_summary
        if r.get("mapping_status") in ("REVIEW_MAPPING", "CONTRACT_GAP", "ERROR")
        or r.get("status") in ("FAIL", "ERROR")
    ]
    if reviews:
        print(f"\n=== REVIEW / FAIL / ERROR ({len(reviews)} total) ===")
        for r in reviews[:15]:
            ms = r.get("mapping_status", "")
            sec = r.get("actual_secondary_intents", "[]")
            src = r.get("match_source", "")
            print(
                f"  [{r['status']}/{ms}] {r['qa_id']} | "
                f"route={r['route_esperada_sugerida']} | "
                f"primary={r['actual_intent']} secondary={sec} src={src}"
            )
            if r.get("comment"):
                print(f"         {str(r['comment'])[:160]}")

    fail_by_route: Counter[str] = Counter(
        r["route_esperada_sugerida"] for r in reviews
    )
    if fail_by_route:
        print("\n=== REVIEW/FAIL por ruta ===")
        for route, n in fail_by_route.most_common():
            print(f"  {n:3d}  {route}")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--input", default=str(DEFAULT_INPUT))
    p.add_argument("--output", default=str(DEFAULT_OUTPUT))
    p.add_argument("--mode", choices=["dry", "classify", "full"], default="dry")
    p.add_argument("--limit", type=int, default=0, help="0 = todos los casos")
    p.add_argument("--start-index", type=int, default=0,
                   help="Índice de inicio en el dataframe filtrado (para bloques)")
    p.add_argument("--route-filter", help="Filtrar por route_esperada_sugerida exacta")
    p.add_argument("--priority", help="Filtrar por prioridad (Alta, Media)")
    # Rate-limit
    p.add_argument("--requests-per-minute", type=float, default=1.5)
    p.add_argument("--tokens-per-minute", type=int, default=6000)
    p.add_argument("--estimated-tokens-per-call", type=int, default=2800)
    p.add_argument("--sleep-seconds", type=float, default=0.0)
    # Retry
    p.add_argument("--max-retries", type=int, default=3)
    p.add_argument("--retry-base-seconds", type=float, default=20.0)
    # Presupuesto diario
    p.add_argument("--daily-token-budget", type=int, default=450000)
    p.add_argument("--stop-before-daily-budget", action="store_true")
    # Reanudación
    p.add_argument("--append", action="store_true")
    p.add_argument("--dry-run", action="store_true", help="No escribe archivos de salida")
    args = p.parse_args()

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
        start_index=args.start_index,
        route_filter=args.route_filter,
        priority_filter=args.priority,
        rpm=args.requests_per_minute,
        tpm=args.tokens_per_minute,
        tokens_per_call=args.estimated_tokens_per_call,
        sleep_override=args.sleep_seconds,
        max_retries=args.max_retries,
        retry_base_seconds=args.retry_base_seconds,
        daily_budget=args.daily_token_budget,
        stop_before_budget=args.stop_before_daily_budget,
        append=args.append,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
