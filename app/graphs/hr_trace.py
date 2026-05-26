from __future__ import annotations

from typing import Any

from app.graphs.hr_state import HRState


def _compact(value: Any, limit: int = 280) -> Any:
    if value is None:
        return None
    if isinstance(value, (int, float, bool)):
        return value
    if isinstance(value, str):
        clean = value.strip()
        return clean if len(clean) <= limit else clean[:limit] + "..."
    if isinstance(value, list):
        return [_compact(x, limit=limit) for x in value[:10]]
    if isinstance(value, dict):
        return {str(k): _compact(v, limit=limit) for k, v in list(value.items())[:20]}
    return str(value)[:limit]


def build_graph_trace(state: HRState) -> dict[str, Any]:
    events = state.get("events") or []
    nodes: list[dict[str, Any]] = []

    for event in events:
        if not isinstance(event, dict):
            continue

        event_type = event.get("type")
        if not event_type:
            continue

        item: dict[str, Any] = {"event": event_type}

        if event_type == "unknown_term_review_completed":
            item.update({
                "node": "pre_rewrite_unknown_term_review",
                "decision": "unknown_terms_reviewed",
                "terms": _compact(event.get("terms")),
                "summary": _compact(event.get("summary")),
                "safe_rewrite_guidance": _compact(event.get("safe_rewrite_guidance")),
            })

        elif event_type == "unknown_term_review_checked":
            item.update({
                "node": "pre_rewrite_unknown_term_review",
                "decision": "no_unclear_terms" if not event.get("has_unclear_terms") else "has_unclear_terms",
                "reason": _compact(event.get("reason")),
            })

        elif event_type == "unknown_term_review_web_skipped":
            item.update({
                "node": "pre_rewrite_unknown_term_review",
                "decision": "web_skipped",
                "reason": _compact(event.get("reason")),
                "terms": _compact(event.get("terms")),
            })

        elif event_type == "contextual_rewrite_checked":
            item.update({
                "node": "contextual_rewrite",
                "decision": "use_rewrite" if event.get("should_use_rewrite") else "preserve_or_low_confidence",
                "confidence": event.get("confidence"),
                "rewritten": _compact(event.get("rewritten")),
                "reason": _compact(event.get("reason")),
            })

        elif event_type == "semantic_uncertainty_checked":
            item.update({
                "node": "semantic_uncertainty_analyzer",
                "decision": "clarify" if event.get("should_clarify") else "continue",
                "unclear_token": _compact(event.get("unclear_token")),
                "confidence": event.get("confidence"),
                "reason": _compact(event.get("reason")),
            })

        elif event_type == "semantic_clarification_requested":
            item.update({
                "node": "semantic_clarification",
                "decision": "ask_candidate",
                "unclear_token": _compact(event.get("unclear_token")),
                "candidates": _compact(event.get("candidates")),
            })

        elif event_type == "question_routed":
            item.update({
                "node": "route_message",
                "decision": _compact(event.get("recommended_route") or event.get("datasource")),
                "datasource": _compact(event.get("datasource")),
                "risk_level": _compact(event.get("risk_level")),
                "routing_message": _compact(event.get("routing_message")),
                "reason": _compact(event.get("reason")),
            })

        elif event_type == "question_rewritten":
            item.update({
                "node": "rewrite_question",
                "decision": _compact(event.get("reason")),
                "rewritten_question": _compact(event.get("rewritten_question")),
                "confidence": event.get("confidence"),
            })

        elif event_type == "web_search_completed":
            item.update({
                "node": "tavily_web_search",
                "decision": "completed",
                "query": _compact(event.get("query")),
                "result_count": event.get("result_count"),
            })

        elif event_type == "rag_answered":
            item.update({
                "node": "generate_answer",
                "decision": "answered_with_rag",
            })

        elif event_type == "fallback_answered":
            item.update({
                "node": "route_stub_response",
                "decision": "fallback_answered",
            })

        elif event_type == "assistant_message_saved":
            item.update({
                "node": "save_assistant_message",
                "decision": "saved",
            })

        else:
            item.update({
                "node": event_type,
                "decision": "event",
            })

        nodes.append(item)

    sources = state.get("sources") or []
    source_names = []
    for source in sources:
        if isinstance(source, dict):
            name = source.get("source")
            if name and name not in source_names:
                source_names.append(name)

    return {
        "route": state.get("route"),
        "requires_rag": state.get("requires_rag"),
        "requires_human": state.get("requires_human"),
        "requires_clarification": state.get("requires_clarification"),
        "risk_level": state.get("risk_level"),
        "nodes": nodes,
        "evidence": {
            "sources": source_names,
            "unknown_term_review": _compact(state.get("unknown_term_review")),
            "contextual_rewrite": _compact(state.get("contextual_rewrite")),
            "semantic_uncertainty": _compact(state.get("semantic_uncertainty")),
            "question_rewrite": _compact(state.get("question_rewrite")),
            "answer_check": state.get("answer_check"),
            "hallucination_check": state.get("hallucination_check"),
        },
    }
