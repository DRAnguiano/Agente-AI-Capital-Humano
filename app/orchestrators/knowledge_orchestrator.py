from __future__ import annotations

from typing import Any

from app.db import get_conversation_state, log_event, make_conversation_key, save_message, update_stage, upsert_conversation
from app.knowledge.neo4j_client import resolve_message


CONTROLLED_CLARIFICATION_REPLY = (
    "Para responderte bien, ¿me puedes explicar a qué te refieres? "
    "Así evitamos malinterpretar tu mensaje."
)

CONTROLLED_FALLBACK_REPLY = (
    "No quiero darte información incorrecta. Puedo ayudarte con pago, documentos, "
    "requisitos, ubicación, licencia, apto médico o disponibilidad."
)


def _route_flags(route: str, risk_level: str) -> dict[str, bool]:
    route = route or "fallback"
    risk = (risk_level or "low").lower()
    return {
        "requires_rag": route == "rag",
        "requires_human": route in {"human_handoff", "policy_boundary"} or risk == "high",
        "requires_clarification": route == "clarification",
    }


def _reply_from_contract(contract: dict[str, Any]) -> str:
    template = contract.get("reply_template")
    if isinstance(template, dict) and template.get("text"):
        return str(template["text"])

    if contract.get("requires_clarification"):
        return CONTROLLED_CLARIFICATION_REPLY

    if contract.get("requires_human"):
        return "Ese punto debe revisarlo Capital Humano antes de continuar. Lo dejo anotado para seguimiento."

    return CONTROLLED_FALLBACK_REPLY


def handle_message(payload: dict[str, Any]) -> dict[str, Any]:
    """Resolve a candidate message through Neo4j and return a clean contract.

    Phase 2.2 scope: no LLM call, no RAG call. This lets us test the knowledge
    graph cheaply before connecting generation in Phase 2.3.
    """
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
    reply = _reply_from_contract(contract)

    update_stage(
        conversation_key=conversation_key,
        stage_to=next_stage,
        intent=contract.get("intent"),
        risk_level=contract.get("risk_level") or "low",
        requires_human=bool(contract.get("requires_human")),
    )

    log_event(
        conversation_key=conversation_key,
        event_type="knowledge_contract_resolved",
        stage_from=current_stage,
        stage_to=next_stage,
        intent=contract.get("intent"),
        risk_level=contract.get("risk_level") or "low",
        requires_human=bool(contract.get("requires_human")),
        metadata={
            "route": contract.get("route"),
            "recognized_terms": contract.get("recognized_terms"),
            "matched_aliases": contract.get("matched_aliases"),
            "preferred_sources": contract.get("preferred_sources"),
            "reason": contract.get("reason"),
            "all_matches": contract.get("all_matches"),
        },
    )

    save_message(conversation_key, "assistant", reply)

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
        "knowledge_contract": contract,
        "graph_trace": {
            "mode": "knowledge",
            "route": contract.get("route"),
            "intent": contract.get("intent"),
            "risk_level": contract.get("risk_level"),
            "requires_rag": contract.get("requires_rag"),
            "requires_human": contract.get("requires_human"),
            "requires_clarification": contract.get("requires_clarification"),
            "nodes": [
                {
                    "node": "neo4j_knowledge_node",
                    "decision": contract.get("route"),
                    "recognized_terms": contract.get("recognized_terms"),
                    "matched_aliases": contract.get("matched_aliases"),
                    "preferred_sources": contract.get("preferred_sources"),
                    "reason": contract.get("reason"),
                }
            ],
        },
    }
