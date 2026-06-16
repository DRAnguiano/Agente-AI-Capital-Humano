"""Task 10b.17 — elegibilidad por canal productivo del follow-up scheduler.

Contrato: el follow-up automático solo aplica a canales productivos operados por
Chatwoot; `telegram_demo` es laboratorio (flag) y los prefijos de prueba se bloquean.
El canal se deriva del prefijo del `lead_key` ("{channel}:{id}"), sin tocar la vista.

Deterministas: prueban el helper puro `is_eligible_for_followup`. Sin DB.
"""
from __future__ import annotations

from app.followup.scheduler import is_eligible_for_followup


# ── Canales de laboratorio / prueba bloqueados ───────────────────────────────

def test_scheduler_excludes_test_prefix_leads():
    assert is_eligible_for_followup("test_knowledge_orchestrator:abc") is False
    assert is_eligible_for_followup("test_faq:1") is False       # cubierto por test_
    assert is_eligible_for_followup("test_verify:1") is False


def test_scheduler_excludes_debug_prefix_leads():
    assert is_eligible_for_followup("debug_saludo:1") is False
    assert is_eligible_for_followup("debug_guard:1") is False
    assert is_eligible_for_followup("debug_direct:1") is False


def test_scheduler_excludes_shadow_test_leads():
    assert is_eligible_for_followup("shadow_test:1") is False


# ── Canal productivo Chatwoot ────────────────────────────────────────────────

def test_scheduler_allows_chatwoot_leads():
    assert is_eligible_for_followup("chatwoot:53") is True
    assert is_eligible_for_followup("chatwoot:64") is True


# ── telegram_demo: laboratorio, bloqueado salvo flag explícito ───────────────

def test_scheduler_blocks_telegram_demo_by_default():
    assert is_eligible_for_followup("telegram_demo:demo_1", enable_demo_followup=False) is False


def test_scheduler_allows_telegram_demo_when_enable_demo_followup_true():
    assert is_eligible_for_followup("telegram_demo:demo_1", enable_demo_followup=True) is True


# ── Canales directos no integrados a Chatwoot todavía → no productivos ────────

def test_scheduler_blocks_unknown_direct_channels():
    # WhatsApp/web entrarán como 'chatwoot'; un canal directo desconocido no es productivo aún.
    assert is_eligible_for_followup("whatsapp:1") is False
    assert is_eligible_for_followup("web:1") is False


def test_scheduler_handles_malformed_lead_key():
    assert is_eligible_for_followup("") is False
    assert is_eligible_for_followup(None) is False
    # sin ':' el lead_key entero es el "canal"; desconocido → no productivo
    assert is_eligible_for_followup("chatwoot") is False
