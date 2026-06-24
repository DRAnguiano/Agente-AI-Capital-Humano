"""Fase 2B.4 (Opción B) — shadow OFFLINE/REPLAY del planner canónico.

MIDE, NO DECIDE. Solo lectura contra Postgres. No escribe, no crea tablas, no toca el
flujo vivo, no wiring. Pensado para correr en `api-test` vía stdin:

    docker compose --profile test run --rm -T api-test python - < scripts/shadow_canonical_funnel.py
    docker compose --profile test run --rm -T api-test python - --anchors-only < scripts/shadow_canonical_funnel.py
    docker compose --profile test run --rm -T api-test python - --limit 50 --jsonl < scripts/shadow_canonical_funnel.py

Compara, por lead real:
  planner (read_canonical_facts → compute_funnel_state)  vs.  estado vivo (rh_leads_v2 +
  última pregunta del assistant en rh_lead_messages_v2 — heurística, no fuente absoluta).
Lo accionable: repreguntas evitables (forbidden_questions), conflictos y needs_confirmation.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone

from app.db import get_conn
from app.knowledge.funnel_state_planner import compute_funnel_state
from app.knowledge.text_normalizer import normalize_text
from app.lead_memory.canonical_profile_reader import read_canonical_facts, canonical_view_exists

# Anclas obligatorias: (lead_key, es_test_anchor)
ANCHORS: list[tuple[str, bool]] = [
    ("chatwoot:53", False),
    ("chatwoot:64", False),
    ("chatwoot:75", False),
    ("chatwoot:56", False),
    ("test_input_nodes:audit_test_1", True),  # ancla técnica de quinta_rueda
]

_TIME_CANDIDATES = ["created_at", "observed_at", "timestamp", "inserted_at"]

# Heurística para "repregunta evitable": si la última pregunta viva menciona un concepto de
# un campo que el planner ya tiene completado/forbidden, es candidata a repregunta evitable.
_FIELD_KEYWORDS = {
    "license.type": ["licencia", "federal"],
    "medical.apto_status": ["apto", "medico"],
    "documents.proof": ["cartas", "documento", "documentos", "imss", "semanas"],
    "candidate.city": ["ciudad", "estado", "radica", "vive"],
    "experience.vehicle_type": ["full", "sencillo", "unidad"],
    "experience.years": ["años", "anos", "experiencia"],
    "candidate.availability_to_attend": ["disponibilidad", "acudir"],
}


def _detect_time_col(cur) -> str | None:
    cur.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_name='rh_lead_messages_v2'"
    )
    cols = {r["column_name"] for r in cur.fetchall()}
    for c in _TIME_CANDIDATES:
        if c in cols:
            return c
    return None


def _recent_chatwoot_leads(cur, limit: int) -> list[str]:
    cur.execute(
        """
        SELECT lead_key FROM rh_leads_v2
        WHERE source_channel = 'chatwoot'
          AND lead_key NOT ILIKE 'test%%'
          AND lead_key NOT ILIKE 'prueba%%'
          AND lead_key NOT ILIKE 'debug%%'
        ORDER BY last_seen_at DESC NULLS LAST
        LIMIT %(n)s
        """,
        {"n": limit},
    )
    return [r["lead_key"] for r in cur.fetchall()]


def _live_snapshot(cur, lead_key: str, time_col: str | None) -> dict:
    cur.execute(
        "SELECT funnel_stage, next_best_action FROM rh_leads_v2 WHERE lead_key = %(lk)s",
        {"lk": lead_key},
    )
    row = cur.fetchone() or {}
    last_q = None
    if time_col:
        try:
            cur.execute(
                f"""SELECT message FROM rh_lead_messages_v2
                    WHERE lead_key = %(lk)s AND role <> 'user'
                    ORDER BY {time_col} DESC NULLS LAST LIMIT 1""",
                {"lk": lead_key},
            )
            r = cur.fetchone()
            last_q = (r or {}).get("message")
        except Exception:
            last_q = None  # heurística, nunca rompe
    return {
        "funnel_stage": row.get("funnel_stage"),
        "next_best_action": row.get("next_best_action"),
        "last_assistant_q": last_q,
    }


def _avoidable_reasks(forbidden: list[str], completed: dict, last_q: str | None) -> list[str]:
    if not last_q:
        return []
    norm = normalize_text(last_q)
    done = set(forbidden) | set(completed.keys())
    out = []
    for field in done:
        for kw in _FIELD_KEYWORDS.get(field, []):
            if kw in norm:
                out.append(field)
                break
    return out


def run(limit: int, anchors_only: bool, single: str | None, jsonl: bool) -> int:
    if not canonical_view_exists():
        print("[SHADOW] v_rh_lead_facts_canonical NO existe; aplica db/010_... antes. Abortando.")
        return 2

    # Construir lista de leads (anclas primero; recientes después)
    anchor_keys = {k for k, _ in ANCHORS}
    is_test = {k: t for k, t in ANCHORS}
    leads: list[str] = []
    if single:
        leads = [single]
    elif anchors_only:
        leads = [k for k, _ in ANCHORS]
    else:
        leads = [k for k, _ in ANCHORS]
        with get_conn() as conn:
            with conn.cursor() as cur:
                recent = _recent_chatwoot_leads(cur, limit)
        for lk in recent:
            if lk not in anchor_keys:
                leads.append(lk)

    jsonl_path = None
    jf = None
    if jsonl:
        os.makedirs("reports", exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        jsonl_path = f"reports/shadow_canonical_funnel_{ts}.jsonl"
        jf = open(jsonl_path, "w", encoding="utf-8")

    conflict_leads: list[str] = []
    needs_conf_leads: list[str] = []
    avoidable: list[tuple[str, list[str]]] = []
    ready_count = 0
    evaluated = 0

    with get_conn() as conn:
        with conn.cursor() as cur:
            time_col = _detect_time_col(cur)
            print(f"[SHADOW] columna de tiempo en rh_lead_messages_v2: {time_col or 'NINGUNA (last_q=None)'}")
            print(f"[SHADOW] leads a evaluar: {len(leads)}\n")
            for lk in leads:
                try:
                    facts = read_canonical_facts(lk)
                    st = compute_funnel_state(facts)
                    live = _live_snapshot(cur, lk, time_col)
                    ev = _avoidable_reasks(st.forbidden_questions, st.completed_fields, live["last_assistant_q"])
                except Exception as exc:  # un lead no debe abortar el run
                    print(f"  ! {lk}: error {type(exc).__name__}: {exc}")
                    continue

                evaluated += 1
                if st.conflict_fields:
                    conflict_leads.append(lk)
                if st.needs_confirmation_fields:
                    needs_conf_leads.append(lk)
                if ev:
                    avoidable.append((lk, ev))
                if st.profile_ready:
                    ready_count += 1

                tag = " [test_anchor]" if is_test.get(lk) else ""
                print(
                    f"- {lk}{tag} | facts={len(facts)} | next={st.next_question_field}"
                    f" ({st.next_question_reason}) | completed={len(st.completed_fields)}"
                    f" | missing={st.missing_fields} | needs_conf={st.needs_confirmation_fields}"
                    f" | conflict={st.conflict_fields} | ready={st.profile_ready}"
                    f" | live_stage={live['funnel_stage']} | live_next={live['next_best_action']}"
                )
                if jf:
                    jf.write(json.dumps({
                        "lead_key": lk, "is_test_anchor": is_test.get(lk, False),
                        "planner": {
                            "completed_fields": list(st.completed_fields.keys()),
                            "missing_fields": st.missing_fields,
                            "forbidden_questions": st.forbidden_questions,
                            "needs_confirmation_fields": st.needs_confirmation_fields,
                            "conflict_fields": st.conflict_fields,
                            "next_question_field": st.next_question_field,
                            "next_question_reason": st.next_question_reason,
                            "next_question_text": st.next_question_text,
                            "profile_ready": st.profile_ready,
                        },
                        "live": live,
                        "avoidable_reasks": ev,
                    }, ensure_ascii=False) + "\n")

    if jf:
        jf.close()

    # ── Resumen ──
    print("\n========== RESUMEN ==========")
    print(f"leads evaluados:           {evaluated}")
    print(f"profile_ready:             {ready_count}")
    print(f"con conflict_fields:       {len(conflict_leads)} -> {conflict_leads}")
    print(f"con needs_confirmation:    {len(needs_conf_leads)} -> {needs_conf_leads}")
    print(f"posibles repreguntas evitables (heurística): {len(avoidable)}")
    for lk, fields in avoidable:
        print(f"   - {lk}: el vivo parece repreguntar {fields} (planner ya los tiene)")
    if jsonl_path:
        print(f"\nJSONL: {jsonl_path}  (recuerda: reports/ debe ignorarse en Git si se commitea)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Shadow offline del planner canónico (solo lectura).")
    ap.add_argument("--limit", type=int, default=30, help="leads chatwoot recientes (default 30)")
    ap.add_argument("--anchors-only", action="store_true", help="solo las anclas")
    ap.add_argument("--lead", type=str, default=None, help="un solo lead_key")
    ap.add_argument("--jsonl", action="store_true", help="además de stdout, escribe reports/*.jsonl")
    args = ap.parse_args()
    return run(args.limit, args.anchors_only, args.lead, args.jsonl)


if __name__ == "__main__":
    sys.exit(main())
