from __future__ import annotations

import os
import re
import time
from typing import Any

from app.db import get_conversation_state, log_event, make_conversation_key, save_message, update_stage, upsert_conversation
from app.indexer import call_llm
from app.knowledge.context_builder import build_generation_prompt, estimate_llm_cost, retrieve_preferred_context
from app.knowledge.neo4j_client import resolve_message


CONTROLLED_CLARIFICATION_REPLY = (
    "Para responderte bien, ¿me puedes explicar a qué te refieres? "
    "Así evitamos malinterpretar tu mensaje."
)

CONTROLLED_FALLBACK_REPLY = (
    "No quiero darte información incorrecta. Puedo ayudarte con pago, documentos, "
    "requisitos, ubicación, licencia, apto médico o disponibilidad."
)

NO_CONTEXT_REPLY = (
    "No encontré información interna suficiente para responder eso con seguridad. "
    "Lo correcto es que Capital Humano lo valide antes de confirmarte el dato."
)

GENERIC_CLOSING_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\s*Si tienes (m[aá]s |alguna )?(otra )?duda[s]?,? puedo ayudarte\.?\s*$", re.IGNORECASE),
    re.compile(r"\s*Si necesitas m[aá]s informaci[oó]n,? puedo ayudarte[^.?!]*(\.|!|\?)?\s*$", re.IGNORECASE),
    re.compile(r"\s*Estoy aqu[ií] para ayudarte\.?\s*$", re.IGNORECASE),
    re.compile(r"\s*¿?Tienes alguna otra duda\??\s*$", re.IGNORECASE),
)


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _route_flags(route: str, risk_level: str) -> dict[str, bool]:
    route = route or "fallback"
    risk = (risk_level or "low").lower()
    return {
        "requires_rag": route == "rag",
        "requires_human": route in {"human_handoff", "policy_boundary"} or risk == "high",
        "requires_clarification": route == "clarification",
    }


def _clean_reply(text: str) -> str:
    clean = (text or "").strip()
    for pattern in GENERIC_CLOSING_PATTERNS:
        clean = pattern.sub("", clean).strip()
    return clean


def _controlled_reply_from_contract(contract: dict[str, Any]) -> str:
    template = contract.get("reply_template")
    if isinstance(template, dict) and template.get("text"):
        return str(template["text"])

    if contract.get("requires_clarification"):
        return CONTROLLED_CLARIFICATION_REPLY

    if contract.get("requires_human"):
        return "Ese punto debe revisarlo Capital Humano antes de continuar. Lo dejo anotado para seguimiento."

    return CONTROLLED_FALLBACK_REPLY


def _answer_rag_message(message: str, contract: dict[str, Any]) -> dict[str, Any]:
    """Controlled RAG + generation path for route=rag.

    This is intentionally small: Neo4j chooses preferred sources, Chroma retrieves
    inside that source bucket, and one LLM call writes the final answer.
    """
    started = time.perf_counter()
    rag_enabled = _env_bool("KNOWLEDGE_RAG_GENERATION_ENABLED", True)

    context = retrieve_preferred_context(
        message,
        preferred_sources=contract.get("preferred_sources") or [],
    )

    if not context.get("items"):
        return {
            "reply": NO_CONTEXT_REPLY,
            "rag_context": context,
            "llm_prompt_chars": 0,
            "llm_reply_chars": len(NO_CONTEXT_REPLY),
            "llm_cost_estimate": estimate_llm_cost("", NO_CONTEXT_REPLY),
            "timings": {
                "rag_total_ms": round((time.perf_counter() - started) * 1000, 2),
                "retrieve_context_ms": context.get("timing_ms"),
                "generate_answer_ms": 0.0,
            },
            "rag_generation_used": False,
            "rag_generation_skipped_reason": context.get("error") or "no_relevant_context",
        }

    prompt = build_generation_prompt(
        message=message,
        knowledge_contract=contract,
        context_text=context.get("context_text") or "",
    )

    if not rag_enabled:
        debug_reply = (
            "RAG detectado y contexto interno recuperado, pero la generación LLM está desactivada "
            "por KNOWLEDGE_RAG_GENERATION_ENABLED=false."
        )
        return {
            "reply": debug_reply,
            "rag_context": context,
            "llm_prompt_chars": len(prompt),
            "llm_reply_chars": len(debug_reply),
            "llm_cost_estimate": estimate_llm_cost(prompt, debug_reply),
            "timings": {
                "rag_total_ms": round((time.perf_counter() - started) * 1000, 2),
                "retrieve_context_ms": context.get("timing_ms"),
                "generate_answer_ms": 0.0,
            },
            "rag_generation_used": False,
            "rag_generation_skipped_reason": "generation_disabled",
        }

    gen_started = time.perf_counter()
    raw_reply = call_llm(prompt)
    generate_ms = round((time.perf_counter() - gen_started) * 1000, 2)
    reply = _clean_reply(raw_reply)

    return {
        "reply": reply,
        "rag_context": context,
        "llm_prompt_chars": len(prompt),
        "llm_reply_chars": len(reply),
        "llm_cost_estimate": estimate_llm_cost(prompt, reply),
        "timings": {
            "rag_total_ms": round((time.perf_counter() - started) * 1000, 2),
            "retrieve_context_ms": context.get("timing_ms"),
            "generate_answer_ms": generate_ms,
        },
        "rag_generation_used": True,
        "rag_generation_skipped_reason": None,
    }


def handle_message(payload: dict[str, Any]) -> dict[str, Any]:
    """Resolve a candidate message through Neo4j and optionally answer with controlled RAG."""
    started = time.perf_counter()
    channel = str(payload.get("channel") or "api").strip()
    channel_user_id = str(payload.get("channel_user_id") or "unknown").strip()
    username = payload.get("username")
    phone = payload.get("phone")
    message = str(payload.get("message") or "").strip()

    identity = upsert_conversation(channel=channel, channel_user_id=channel_user_id, username=username, phone=phone)
    conversation_key = identity.get("conversation_key") or make_conversation_key(channel, channel_user_id)
    state = get_conversation_state(conversation_key)
    conversation = state.get("conversation") or {}

    save_message(conversation_key, "user", message)

    contract = resolve_message(message, conversation_state=conversation)
    flags = _route_flags(str(contract.get("route") or "fallback"), str(contract.get("risk_level") or "low"))
    contract.update(flags)

    current_stage = str(conversation.get("current_stage") or "START")
    next_stage = "HUMAN_REVIEW_REQUIRED" if contract.get("requires_human") else current_stage

    rag_result: dict[str, Any] | None = None
    if contract.get("requires_rag"):
        rag_result = _answer_rag_message(message, contract)
        reply = rag_result["reply"]
    else:
        reply = _controlled_reply_from_contract(contract)

    update_stage(
        conversation_key=conversation_key,
        stage_to=next_stage,
        intent=contract.get("intent"),
        risk_level=contract.get("risk_level") or "low",
        requires_human=bool(contract.get("requires_human")),
    )

    metadata = {
        "route": contract.get("route"),
        "recognized_terms": contract.get("recognized_terms"),
        "matched_aliases": contract.get("matched_aliases"),
        "preferred_sources": contract.get("preferred_sources"),
        "reason": contract.get("reason"),
        "all_matches": contract.get("all_matches"),
    }
    if rag_result:
        metadata.update(
            {
                "rag_generation_used": rag_result.get("rag_generation_used"),
                "rag_generation_skipped_reason": rag_result.get("rag_generation_skipped_reason"),
                "rag_sources": (rag_result.get("rag_context") or {}).get("sources"),
                "rag_source_filter_used": (rag_result.get("rag_context") or {}).get("source_filter_used"),
                "rag_items_count": len((rag_result.get("rag_context") or {}).get("items") or []),
                "llm_cost_estimate": rag_result.get("llm_cost_estimate"),
                "timings": rag_result.get("timings"),
            }
        )

    log_event(
        conversation_key=conversation_key,
        event_type="knowledge_contract_resolved",
        stage_from=current_stage,
        stage_to=next_stage,
        intent=contract.get("intent"),
        risk_level=contract.get("risk_level") or "low",
        requires_human=bool(contract.get("requires_human")),
        metadata=metadata,
    )

    save_message(conversation_key, "assistant", reply)

    timings = {
        "total_ms": round((time.perf_counter() - started) * 1000, 2),
    }
    if rag_result and isinstance(rag_result.get("timings"), dict):
        timings.update(rag_result["timings"])

    sources = []
    if rag_result:
        for item in (rag_result.get("rag_context") or {}).get("items") or []:
            sources.append(
                {
                    "source": item.get("source"),
                    "score": round(float(item.get("score") or 0), 4),
                    "id": item.get("id"),
                }
            )

    return {
        "status": "ok",
        "selected_route": contract.get("route"),
        "intent": contract.get("intent"),
        "risk_level": contract.get("risk_level"),
        "requires_rag": contract.get("requires_rag"),
        "requires_human": contract.get("requires_human"),
        "requires_clarification": contract.get("requires_clarification"),
        "reply": reply,
        "text": reply,
        "conversation_key": conversation_key,
        "sources": sources,
        "knowledge_contract": contract,
        "rag": {
            "used": bool(rag_result and rag_result.get("rag_generation_used")),
            "skipped_reason": rag_result.get("rag_generation_skipped_reason") if rag_result else None,
            "preferred_sources": contract.get("preferred_sources") or [],
            "retrieved_sources": (rag_result.get("rag_context") or {}).get("sources") if rag_result else [],
            "items_count": len((rag_result.get("rag_context") or {}).get("items") or []) if rag_result else 0,
        },
        "cost": rag_result.get("llm_cost_estimate") if rag_result else None,
        "timings": timings,
        "graph_trace": {
            "mode": "knowledge",
            "route": contract.get("route"),
            "intent": contract.get("intent"),
            "risk_level": contract.get("risk_level"),
            "requires_rag": contract.get("requires_rag"),
            "requires_human": contract.get("requires_human"),
            "requires_clarification": contract.get("requires_clarification"),
            "timings": timings,
            "cost": rag_result.get("llm_cost_estimate") if rag_result else None,
            "nodes": [
                {
                    "node": "neo4j_knowledge_node",
                    "decision": contract.get("route"),
                    "recognized_terms": contract.get("recognized_terms"),
                    "matched_aliases": contract.get("matched_aliases"),
                    "preferred_sources": contract.get("preferred_sources"),
                    "reason": contract.get("reason"),
                },
                {
                    "node": "controlled_rag_generation",
                    "decision": "used" if rag_result and rag_result.get("rag_generation_used") else "skipped",
                    "sources": (rag_result.get("rag_context") or {}).get("sources") if rag_result else [],
                    "items_count": len((rag_result.get("rag_context") or {}).get("items") or []) if rag_result else 0,
                    "skipped_reason": rag_result.get("rag_generation_skipped_reason") if rag_result else None,
                },
            ],
        },
    }
