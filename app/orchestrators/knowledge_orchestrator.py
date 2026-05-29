from __future__ import annotations

import json
from typing import Any

from app.indexer import call_llm
from app.knowledge.current_turn import (
    build_current_turn_ack,
    extract_current_turn_facts,
    should_prioritize_current_turn,
)
from app.knowledge.neo4j_client import resolve_message


def _safe_text(value: Any, default: str = "") -> str:
    text = str(value or default or "").strip()
    return text or default


def _facts_summary(facts: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in facts.items() if value not in (None, "")}


def _try_graph_contract(message: str) -> dict[str, Any]:
    try:
        return resolve_message(message)
    except Exception as exc:
        return {
            "intent": "unknown",
            "route": "fallback",
            "risk_level": "low",
            "requires_human": False,
            "requires_rag": False,
            "requires_clarification": False,
            "preferred_sources": [],
            "reply_template": None,
            "policies": [],
            "reason": f"neo4j_unavailable:{type(exc).__name__}",
            "error": str(exc)[:300],
        }


def _reply_from_template(contract: dict[str, Any]) -> str | None:
    template = contract.get("reply_template")
    if isinstance(template, dict):
        text = _safe_text(template.get("text"))
        return text or None
    return None


def _rag_reply(message: str, contract: dict[str, Any]) -> str:
    try:
        from app.knowledge.context_builder import build_generation_prompt, retrieve_preferred_context

        retrieved = retrieve_preferred_context(
            message,
            preferred_sources=contract.get("preferred_sources") or [],
        )
        prompt = build_generation_prompt(
            message=message,
            knowledge_contract=contract,
            context_text=retrieved.get("context_text") or "",
        )
        answer = _safe_text(call_llm(prompt))
        if answer:
            return answer
    except Exception:
        pass

    return "Para no darte información incorrecta, ese dato lo valida Capital Humano con la información interna actualizada."


def _fallback_reply(message: str, contract: dict[str, Any]) -> str:
    if contract.get("requires_clarification"):
        return "Para no malinterpretarte, ¿puedes explicarme un poco más a qué te refieres?"
    if contract.get("requires_human"):
        return "Ese punto debe revisarlo Capital Humano antes de continuar. Lo dejo anotado para seguimiento."
    return "No quiero darte información incorrecta. Dime si tu duda es sobre pago, documentos, licencia, apto médico, rutas o experiencia."


def _persist_best_effort(payload: dict[str, Any], result: dict[str, Any]) -> None:
    """Best-effort persistence hook.

    Main DB truth is rh_leads_v2/rh_lead_facts_v2. This compact orchestrator
    intentionally does not fail candidate replies if DB persistence changes.
    """
    try:
        from app.lead_memory.profile_extractor import extract_profile_facts
        from app.lead_memory.repository import (
            log_lead_event,
            save_lead_message,
            upsert_lead_fact,
            upsert_lead_identity,
            update_lead_summary,
        )

        identity = upsert_lead_identity(
            channel=payload.get("channel") or "chatwoot",
            channel_user_id=str(payload.get("channel_user_id") or "unknown"),
            username=payload.get("username"),
            phone=payload.get("phone"),
        )
        lead_key = identity.get("lead_key")
        conversation_key = identity.get("conversation_key")
        message = payload.get("message") or ""
        source_message_id = payload.get("external_message_id")

        saved = save_lead_message(
            lead_key=lead_key,
            conversation_key=conversation_key,
            role="user",
            message=message,
            source_message_id=source_message_id,
        )
        saved_id = saved.get("id") if saved else None

        extracted = extract_profile_facts(message, result.get("intent"))
        for fact in extracted:
            upsert_lead_fact(
                lead_key=lead_key,
                fact_group=fact.get("fact_group"),
                fact_key=fact.get("fact_key"),
                fact_value=str(fact.get("fact_value")),
                confidence=float(fact.get("confidence") or 0.7),
                source_message_id=saved_id,
                source_text=message,
            )

        save_lead_message(
            lead_key=lead_key,
            conversation_key=conversation_key,
            role="assistant",
            message=result.get("reply") or result.get("text") or "",
        )
        log_lead_event(
            lead_key=lead_key,
            conversation_key=conversation_key,
            event_type="knowledge_orchestrator_answered",
            intent=result.get("intent"),
            route=result.get("route"),
            risk_level=result.get("risk_level") or "low",
            requires_human=bool(result.get("requires_human")),
            metadata={"facts": result.get("current_turn_facts") or {}, "graph": result.get("knowledge_contract") or {}},
        )
        update_lead_summary(
            lead_key=lead_key,
            funnel_stage=result.get("funnel_stage") or "interested",
            next_best_action=result.get("next_best_action"),
            memory_summary=result.get("memory_summary"),
            facts_summary={"current_turn_facts": result.get("current_turn_facts") or {}},
            risk_level=result.get("risk_level") or "low",
            requires_human=bool(result.get("requires_human")),
        )
    except Exception:
        return


def handle_message(payload: dict[str, Any]) -> dict[str, Any]:
    message = _safe_text(payload.get("message"))
    contract = _try_graph_contract(message)
    current_facts = extract_current_turn_facts(message)

    if should_prioritize_current_turn(message):
        reply = build_current_turn_ack(message)
        route = "profile"
        intent = "candidate_profile_signal"
    else:
        reply = _reply_from_template(contract)
        route = contract.get("route") or "fallback"
        intent = contract.get("intent") or "unknown"
        if not reply and contract.get("requires_rag"):
            reply = _rag_reply(message, contract)
        if not reply:
            reply = _fallback_reply(message, contract)

    result = {
        "reply": reply,
        "text": reply,
        "route": route,
        "selected_route": route,
        "intent": intent,
        "risk_level": contract.get("risk_level") or "low",
        "requires_human": bool(contract.get("requires_human")),
        "requires_rag": bool(contract.get("requires_rag")),
        "requires_clarification": bool(contract.get("requires_clarification")),
        "current_stage": "START",
        "funnel_stage": "interested" if route in {"greeting", "profile", "rag"} else "followup_pending",
        "next_best_action": "Continuar flujo según datos faltantes del candidato.",
        "memory_summary": "Respuesta generada desde knowledge mode con prioridad al mensaje actual.",
        "facts_summary": _facts_summary(current_facts),
        "current_turn_facts": current_facts,
        "knowledge_contract": contract,
        "graph_trace": {"mode": "knowledge", "route": route, "intent": intent},
    }

    _persist_best_effort(payload, result)
    return result
