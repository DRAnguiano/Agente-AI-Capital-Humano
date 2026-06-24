"""Tarea 9.2 — reporte offline de los logs del shadow multi-intent.

Lee líneas de log que emite `app/knowledge/intent_shadow.run_shadow`
(`[MULTI_INTENT_SHADOW] {json}` por turno, y `[MULTI_INTENT_SHADOW_ERROR] ...`)
y produce un reporte de comparación: cuántos turnos, divergencia
`shadow_reply` vs `actual_reply`, distribución de intents, handoffs, errores y
estadística de `shadow_ms` (latencia del pipeline shadow).

MIDE, NO DECIDE. Puro y offline: NO toca Postgres, Chatwoot, Groq ni el flujo
vivo. Solo parsea texto. Pensado para correr sobre logs recolectados:

    python scripts/shadow_log_report.py /ruta/al/worker.log
    docker compose logs worker | python scripts/shadow_log_report.py -
    python scripts/shadow_log_report.py worker.log --json
    python scripts/shadow_log_report.py worker.log --diffs 5

Nota: `shadow_reply`/`actual_reply` vienen truncados a 400 chars en el log, así
que la igualdad es una señal **gruesa** de divergencia, no exacta byte a byte.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from typing import Any, Iterable

SHADOW_MARKER = "[MULTI_INTENT_SHADOW] "
ERROR_MARKER = "[MULTI_INTENT_SHADOW_ERROR]"


def parse_log(lines: Iterable[str]) -> dict[str, Any]:
    """Extrae los registros shadow de un iterable de líneas de log.

    Devuelve ``{"records": [...], "errors": int, "malformed": int}``:
      - records: dicts JSON de cada turno shadow bien formado.
      - errors: líneas `[MULTI_INTENT_SHADOW_ERROR]` (el shadow falló ese turno).
      - malformed: líneas con el marcador pero JSON ilegible (se omiten del reporte).
    """
    records: list[dict[str, Any]] = []
    errors = 0
    malformed = 0
    for line in lines:
        if ERROR_MARKER in line:
            errors += 1
            continue
        idx = line.find(SHADOW_MARKER)
        if idx == -1:
            continue
        payload = line[idx + len(SHADOW_MARKER):].strip()
        try:
            obj = json.loads(payload)
        except (ValueError, TypeError):
            malformed += 1
            continue
        if isinstance(obj, dict):
            records.append(obj)
        else:
            malformed += 1
    return {"records": records, "errors": errors, "malformed": malformed}


def _percentile(sorted_values: list[float], pct: float) -> float:
    """Percentil por rango más cercano (nearest-rank). Sin dependencias."""
    if not sorted_values:
        return 0.0
    rank = math.ceil(pct / 100.0 * len(sorted_values))
    idx = min(max(rank - 1, 0), len(sorted_values) - 1)
    return sorted_values[idx]


def _ms_stats(values: list[float]) -> dict[str, float] | None:
    if not values:
        return None
    s = sorted(values)
    return {
        "count": len(s),
        "min": s[0],
        "max": s[-1],
        "mean": round(sum(s) / len(s), 1),
        "p50": _percentile(s, 50),
        "p95": _percentile(s, 95),
    }


def build_report(parsed: dict[str, Any]) -> dict[str, Any]:
    """Construye el reporte de comparación a partir de `parse_log`."""
    records = parsed.get("records") or []
    total = len(records)

    reply_match = 0
    reply_differ = 0
    handoff = 0
    ms_values: list[float] = []
    primary_intent: dict[str, int] = {}
    message_type: dict[str, int] = {}

    for r in records:
        shadow = r.get("shadow_reply")
        actual = r.get("actual_reply")
        if shadow is not None and actual is not None:
            if shadow == actual:
                reply_match += 1
            else:
                reply_differ += 1
        if r.get("handoff"):
            handoff += 1
        ms = r.get("shadow_ms")
        if isinstance(ms, (int, float)):
            ms_values.append(float(ms))
        pi = r.get("primary_intent")
        if pi is not None:
            primary_intent[pi] = primary_intent.get(pi, 0) + 1
        mt = r.get("message_type")
        if mt is not None:
            message_type[mt] = message_type.get(mt, 0) + 1

    compared = reply_match + reply_differ
    match_rate = round(reply_match / compared, 3) if compared else None

    return {
        "turns": total,
        "errors": parsed.get("errors", 0),
        "malformed": parsed.get("malformed", 0),
        "reply": {"match": reply_match, "differ": reply_differ, "match_rate": match_rate},
        "handoff": handoff,
        "shadow_ms": _ms_stats(ms_values),
        "primary_intent": dict(sorted(primary_intent.items(), key=lambda kv: -kv[1])),
        "message_type": dict(sorted(message_type.items(), key=lambda kv: -kv[1])),
    }


def collect_diffs(records: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    """Ejemplos de turnos donde shadow_reply != actual_reply (para inspección)."""
    out: list[dict[str, Any]] = []
    for r in records:
        if len(out) >= limit:
            break
        shadow, actual = r.get("shadow_reply"), r.get("actual_reply")
        if shadow is not None and actual is not None and shadow != actual:
            out.append({
                "message": r.get("message"),
                "primary_intent": r.get("primary_intent"),
                "shadow_reply": shadow,
                "actual_reply": actual,
            })
    return out


def format_report(report: dict[str, Any]) -> str:
    """Render humano del reporte."""
    lines = ["[MULTI_INTENT_SHADOW] reporte de comparación", ""]
    lines.append(f"turnos shadow:    {report['turns']}")
    lines.append(f"errores shadow:   {report['errors']}")
    if report.get("malformed"):
        lines.append(f"líneas ilegibles: {report['malformed']}")
    rep = report["reply"]
    rate = "n/a" if rep["match_rate"] is None else f"{rep['match_rate'] * 100:.1f}%"
    lines.append(f"reply iguales:    {rep['match']}  (coincidencia: {rate})")
    lines.append(f"reply distintos:  {rep['differ']}")
    lines.append(f"handoffs:         {report['handoff']}")
    ms = report.get("shadow_ms")
    if ms:
        lines.append(
            f"shadow_ms:        n={ms['count']} min={ms['min']} "
            f"p50={ms['p50']} p95={ms['p95']} max={ms['max']} mean={ms['mean']}"
        )
    if report["primary_intent"]:
        lines.append("primary_intent:")
        for intent, n in report["primary_intent"].items():
            lines.append(f"  {intent}: {n}")
    if report["message_type"]:
        lines.append("message_type:")
        for mt, n in report["message_type"].items():
            lines.append(f"  {mt}: {n}")
    return "\n".join(lines)


def _read_inputs(paths: list[str]) -> list[str]:
    if not paths or paths == ["-"]:
        return sys.stdin.read().splitlines()
    out: list[str] = []
    for p in paths:
        if p == "-":
            out.extend(sys.stdin.read().splitlines())
        else:
            with open(p, encoding="utf-8", errors="replace") as fh:
                out.extend(fh.read().splitlines())
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Reporte offline de logs shadow multi-intent (9.2).")
    ap.add_argument("paths", nargs="*", default=["-"], help="Archivos de log o '-' para stdin.")
    ap.add_argument("--json", action="store_true", help="Salida JSON en vez de texto.")
    ap.add_argument("--diffs", type=int, default=0, metavar="N",
                    help="Mostrar hasta N ejemplos de reply shadow≠actual.")
    args = ap.parse_args(argv)

    parsed = parse_log(_read_inputs(args.paths))
    report = build_report(parsed)

    if args.json:
        payload: dict[str, Any] = {"report": report}
        if args.diffs:
            payload["diffs"] = collect_diffs(parsed["records"], args.diffs)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(format_report(report))
        if args.diffs:
            print("\nEjemplos shadow≠actual:")
            for d in collect_diffs(parsed["records"], args.diffs):
                print(f"\n- mensaje: {d['message']}")
                print(f"  intent:  {d['primary_intent']}")
                print(f"  shadow:  {d['shadow_reply']}")
                print(f"  actual:  {d['actual_reply']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
