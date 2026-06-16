"""Tarea 9.2 — parser/reporte offline de logs shadow multi-intent.

Deterministas: solo parsean texto. Sin Groq, sin Chroma, sin DB.
"""
from __future__ import annotations

import json

from scripts.shadow_log_report import (
    build_report,
    collect_diffs,
    parse_log,
)


def _line(**fields) -> str:
    base = {
        "message": "hola",
        "message_type": "simple",
        "primary_intent": "greeting",
        "secondary_intents": [],
        "facts_to_persist": [],
        "action_order": [],
        "core_completeness": 0,
        "handoff": False,
        "shadow_reply": "R",
        "actual_reply": "R",
        "shadow_ms": 12.0,
    }
    base.update(fields)
    # con prefijo de log realista antes del marcador
    return "2026-06-16T10:00:00 INFO [MULTI_INTENT_SHADOW] " + json.dumps(base, ensure_ascii=False)


# ── parseo ────────────────────────────────────────────────────────────────────

def test_parse_extracts_records_errors_and_ignores_noise():
    lines = [
        _line(),
        "alguna línea de log no relacionada",
        "2026-06-16 [MULTI_INTENT_SHADOW_ERROR] KeyError: 'x'",
        _line(primary_intent="pay_question"),
    ]
    parsed = parse_log(lines)
    assert len(parsed["records"]) == 2
    assert parsed["errors"] == 1
    assert parsed["malformed"] == 0


def test_parse_counts_malformed_json():
    lines = ["[MULTI_INTENT_SHADOW] {esto no es json}"]
    parsed = parse_log(lines)
    assert parsed["records"] == []
    assert parsed["malformed"] == 1


def test_error_marker_not_confused_with_shadow_marker():
    # la línea de error NO debe contar como record (comparten prefijo)
    parsed = parse_log(["[MULTI_INTENT_SHADOW_ERROR] boom"])
    assert parsed["records"] == []
    assert parsed["errors"] == 1


# ── reporte ───────────────────────────────────────────────────────────────────

def test_report_reply_match_and_differ():
    lines = [
        _line(shadow_reply="A", actual_reply="A"),   # match
        _line(shadow_reply="A", actual_reply="B"),   # differ
        _line(shadow_reply="C", actual_reply="C"),   # match
    ]
    rep = build_report(parse_log(lines))
    assert rep["turns"] == 3
    assert rep["reply"]["match"] == 2
    assert rep["reply"]["differ"] == 1
    assert rep["reply"]["match_rate"] == round(2 / 3, 3)


def test_report_ms_stats_and_intents():
    lines = [
        _line(primary_intent="greeting", shadow_ms=10.0),
        _line(primary_intent="pay_question", shadow_ms=20.0, handoff=True),
        _line(primary_intent="pay_question", shadow_ms=30.0),
    ]
    rep = build_report(parse_log(lines))
    assert rep["handoff"] == 1
    assert rep["primary_intent"] == {"pay_question": 2, "greeting": 1}
    ms = rep["shadow_ms"]
    assert ms["count"] == 3 and ms["min"] == 10.0 and ms["max"] == 30.0
    assert ms["mean"] == 20.0
    assert ms["p50"] == 20.0 and ms["p95"] == 30.0


def test_report_empty_is_safe():
    rep = build_report(parse_log([]))
    assert rep["turns"] == 0
    assert rep["shadow_ms"] is None
    assert rep["reply"]["match_rate"] is None


def test_collect_diffs_limit():
    lines = [
        _line(message="m1", shadow_reply="A", actual_reply="B"),
        _line(message="m2", shadow_reply="C", actual_reply="C"),  # igual, no diff
        _line(message="m3", shadow_reply="D", actual_reply="E"),
    ]
    diffs = collect_diffs(parse_log(lines)["records"], limit=1)
    assert len(diffs) == 1
    assert diffs[0]["message"] == "m1"
