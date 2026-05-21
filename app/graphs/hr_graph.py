from typing import Any

from langgraph.graph import END, START, StateGraph

from app.graphs.hr_nodes_core import (
    load_conversation_node,
    normalize_input_node,
    save_incoming_message_node,
)
from app.graphs.hr_nodes_rag import (
    answer_check_node,
    fallback_no_context_node,
    generate_answer_node,
    grade_documents_node,
    hallucination_check_node,
    legacy_orchestrator_node,
    retrieve_documents_node,
    save_output_node,
)
from app.graphs.hr_nodes_router import route_message_node
from app.graphs.hr_routes import route_after_grading
from app.graphs.hr_state import HRState


INPUT_TEST_CHANNEL = "test_input_nodes"
ROUTER_TEST_CHANNEL = "test_router_nodes"
RAG_TEST_CHANNEL = "test_rag_nodes"


def build_hr_graph():
    """
    Production-safe MVP graph.

    Current active production route:
        START -> normalize_input -> legacy_orchestrator -> save_output -> END

    Native nodes are registered but not wired into production yet because
    legacy_orchestrator still performs setup, message persistence and routing.
    """
    workflow = StateGraph(HRState)

    workflow.add_node("normalize_input", normalize_input_node)
    workflow.add_node("load_conversation", load_conversation_node)
    workflow.add_node("save_incoming_message", save_incoming_message_node)
    workflow.add_node("route_message", route_message_node)

    workflow.add_node("legacy_orchestrator", legacy_orchestrator_node)

    workflow.add_node("retrieve_documents", retrieve_documents_node)
    workflow.add_node("grade_documents", grade_documents_node)
    workflow.add_node("fallback_no_context", fallback_no_context_node)
    workflow.add_node("generate_answer", generate_answer_node)
    workflow.add_node("hallucination_check", hallucination_check_node)
    workflow.add_node("answer_check", answer_check_node)

    workflow.add_node("save_output", save_output_node)

    workflow.add_edge(START, "normalize_input")
    workflow.add_edge("normalize_input", "legacy_orchestrator")
    workflow.add_edge("legacy_orchestrator", "save_output")
    workflow.add_edge("save_output", END)

    return workflow.compile()


def build_hr_input_test_graph():
    """
    Diagnostic graph for input nodes.

    Trigger:
        channel = "test_input_nodes"
    """
    workflow = StateGraph(HRState)

    workflow.add_node("normalize_input", normalize_input_node)
    workflow.add_node("load_conversation", load_conversation_node)
    workflow.add_node("save_incoming_message", save_incoming_message_node)
    workflow.add_node("save_output", save_output_node)

    workflow.add_edge(START, "normalize_input")
    workflow.add_edge("normalize_input", "load_conversation")
    workflow.add_edge("load_conversation", "save_incoming_message")
    workflow.add_edge("save_incoming_message", "save_output")
    workflow.add_edge("save_output", END)

    return workflow.compile()


def build_hr_router_test_graph():
    """
    Diagnostic graph for input nodes + router node.

    Trigger:
        channel = "test_router_nodes"
    """
    workflow = StateGraph(HRState)

    workflow.add_node("normalize_input", normalize_input_node)
    workflow.add_node("load_conversation", load_conversation_node)
    workflow.add_node("save_incoming_message", save_incoming_message_node)
    workflow.add_node("route_message", route_message_node)
    workflow.add_node("save_output", save_output_node)

    workflow.add_edge(START, "normalize_input")
    workflow.add_edge("normalize_input", "load_conversation")
    workflow.add_edge("load_conversation", "save_incoming_message")
    workflow.add_edge("save_incoming_message", "route_message")
    workflow.add_edge("route_message", "save_output")
    workflow.add_edge("save_output", END)

    return workflow.compile()


def _route_after_rag_test_router(state: HRState) -> str:
    """
    RAG diagnostic gate.

    Only document-question routes continue into the RAG chain. Other routes stop
    at save_output, so this diagnostic endpoint does not accidentally execute
    profile/handoff behavior.
    """
    if state.get("route") == "rag":
        return "retrieve_documents"
    return "save_output"


def _route_after_rag_answer_check(state: HRState) -> str:
    """
    If the generated answer fails validation, use the safe no-context fallback
    instead of creating handoff records in this diagnostic graph.
    """
    if state.get("answer_check") == "PASS":
        return "save_output"
    return "fallback_no_context"


def build_hr_rag_test_graph():
    """
    Diagnostic graph for the Reliable RAG pattern.

    Trigger:
        channel = "test_rag_nodes"

    Pattern:
        route_message
        -> retrieve_documents
        -> grade_documents
        -> generate_answer
        -> hallucination_check
        -> answer_check
    """
    workflow = StateGraph(HRState)

    workflow.add_node("normalize_input", normalize_input_node)
    workflow.add_node("load_conversation", load_conversation_node)
    workflow.add_node("save_incoming_message", save_incoming_message_node)
    workflow.add_node("route_message", route_message_node)
    workflow.add_node("retrieve_documents", retrieve_documents_node)
    workflow.add_node("grade_documents", grade_documents_node)
    workflow.add_node("fallback_no_context", fallback_no_context_node)
    workflow.add_node("generate_answer", generate_answer_node)
    workflow.add_node("hallucination_check", hallucination_check_node)
    workflow.add_node("answer_check", answer_check_node)
    workflow.add_node("save_output", save_output_node)

    workflow.add_edge(START, "normalize_input")
    workflow.add_edge("normalize_input", "load_conversation")
    workflow.add_edge("load_conversation", "save_incoming_message")
    workflow.add_edge("save_incoming_message", "route_message")

    workflow.add_conditional_edges(
        "route_message",
        _route_after_rag_test_router,
        {
            "retrieve_documents": "retrieve_documents",
            "save_output": "save_output",
        },
    )

    workflow.add_edge("retrieve_documents", "grade_documents")

    workflow.add_conditional_edges(
        "grade_documents",
        route_after_grading,
        {
            "generate_answer": "generate_answer",
            "fallback_no_context": "fallback_no_context",
        },
    )

    workflow.add_edge("generate_answer", "hallucination_check")
    workflow.add_edge("hallucination_check", "answer_check")

    workflow.add_conditional_edges(
        "answer_check",
        _route_after_rag_answer_check,
        {
            "save_output": "save_output",
            "fallback_no_context": "fallback_no_context",
        },
    )

    workflow.add_edge("fallback_no_context", "save_output")
    workflow.add_edge("save_output", END)

    return workflow.compile()


hr_graph = build_hr_graph()
hr_input_test_graph = build_hr_input_test_graph()
hr_router_test_graph = build_hr_router_test_graph()
hr_rag_test_graph = build_hr_rag_test_graph()


def _initial_state(
    *,
    channel: str,
    channel_user_id: str,
    message: str,
    username: str | None = None,
    phone: str | None = None,
    external_message_id: str | None = None,
) -> HRState:
    return {
        "channel": channel,
        "channel_user_id": channel_user_id,
        "username": username,
        "phone": phone,
        "message": message,
        "external_message_id": external_message_id,
    }


def _config(channel: str, channel_user_id: str) -> dict[str, Any]:
    return {
        "configurable": {
            "thread_id": f"{channel}:{channel_user_id}",
        }
    }


def _run_input_test_graph(
    initial_state: HRState,
    config: dict[str, Any],
) -> dict[str, Any]:
    final_state = hr_input_test_graph.invoke(initial_state, config=config)

    return {
        "status": final_state.get("status", "ok"),
        "conversation_key": final_state.get("conversation_key"),
        "conversation_id": final_state.get("conversation_id"),
        "candidate_id": final_state.get("candidate_id"),
        "current_stage": final_state.get("current_stage"),
        "next_stage": final_state.get("next_stage"),
        "incoming_message_saved": bool(final_state.get("incoming_message_saved", False)),
        "reply": final_state.get("reply") or final_state.get("text") or "",
        "events": final_state.get("events", []),
        "graph": {
            "enabled": True,
            "route": "input_nodes_test",
            "thread_id": config["configurable"]["thread_id"],
            "input_nodes_extracted": True,
            "executed_nodes": [
                "normalize_input",
                "load_conversation",
                "save_incoming_message",
                "save_output",
            ],
        },
    }


def _run_router_test_graph(
    initial_state: HRState,
    config: dict[str, Any],
) -> dict[str, Any]:
    final_state = hr_router_test_graph.invoke(initial_state, config=config)

    return {
        "status": final_state.get("status", "ok"),
        "conversation_key": final_state.get("conversation_key"),
        "conversation_id": final_state.get("conversation_id"),
        "candidate_id": final_state.get("candidate_id"),
        "current_stage": final_state.get("current_stage"),
        "next_stage": final_state.get("next_stage"),
        "incoming_message_saved": bool(final_state.get("incoming_message_saved", False)),
        "intent": final_state.get("intent"),
        "risk_level": final_state.get("risk_level"),
        "requires_human": bool(final_state.get("requires_human", False)),
        "requires_rag": bool(final_state.get("requires_rag", False)),
        "requires_clarification": bool(final_state.get("requires_clarification", False)),
        "reason": final_state.get("reason"),
        "selected_route": final_state.get("route"),
        "reply": final_state.get("reply") or final_state.get("text") or "",
        "events": final_state.get("events", []),
        "graph": {
            "enabled": True,
            "route": "router_test",
            "selected_route": final_state.get("route"),
            "thread_id": config["configurable"]["thread_id"],
            "input_nodes_extracted": True,
            "router_node_extracted": True,
            "executed_nodes": [
                "normalize_input",
                "load_conversation",
                "save_incoming_message",
                "route_message",
                "save_output",
            ],
        },
    }


def _run_rag_test_graph(
    initial_state: HRState,
    config: dict[str, Any],
) -> dict[str, Any]:
    final_state = hr_rag_test_graph.invoke(initial_state, config=config)

    retrieved_docs = final_state.get("retrieved_docs", []) or []
    relevant_docs = final_state.get("relevant_docs", []) or []

    return {
        "status": final_state.get("status", "ok"),
        "conversation_key": final_state.get("conversation_key"),
        "conversation_id": final_state.get("conversation_id"),
        "candidate_id": final_state.get("candidate_id"),
        "current_stage": final_state.get("current_stage"),
        "next_stage": final_state.get("next_stage"),
        "incoming_message_saved": bool(final_state.get("incoming_message_saved", False)),
        "intent": final_state.get("intent"),
        "risk_level": final_state.get("risk_level"),
        "requires_human": bool(final_state.get("requires_human", False)),
        "requires_rag": bool(final_state.get("requires_rag", False)),
        "requires_clarification": bool(final_state.get("requires_clarification", False)),
        "reason": final_state.get("reason"),
        "selected_route": final_state.get("route"),
        "retrieved_docs_count": len(retrieved_docs),
        "relevant_docs_count": len(relevant_docs),
        "docs_are_relevant": bool(final_state.get("docs_are_relevant", False)),
        "hallucination_check": final_state.get("hallucination_check"),
        "answer_check": final_state.get("answer_check"),
        "reply": final_state.get("reply") or final_state.get("text") or "",
        "sources": final_state.get("sources", []),
        "events": final_state.get("events", []),
        "graph": {
            "enabled": True,
            "route": "rag_test",
            "selected_route": final_state.get("route"),
            "thread_id": config["configurable"]["thread_id"],
            "input_nodes_extracted": True,
            "router_node_extracted": True,
            "rag_nodes_extracted": True,
            "executed_nodes": [
                "normalize_input",
                "load_conversation",
                "save_incoming_message",
                "route_message",
                "retrieve_documents",
                "grade_documents",
                "generate_answer_or_fallback",
                "hallucination_check",
                "answer_check",
                "save_output",
            ],
        },
    }


def run_hr_graph_message(
    *,
    channel: str,
    channel_user_id: str,
    message: str,
    username: str | None = None,
    phone: str | None = None,
    external_message_id: str | None = None,
) -> dict[str, Any]:
    """Invoke the HR graph using the existing /orchestrate/message contract."""
    initial_state = _initial_state(
        channel=channel,
        channel_user_id=channel_user_id,
        username=username,
        phone=phone,
        message=message,
        external_message_id=external_message_id,
    )
    config = _config(channel, channel_user_id)
    normalized_channel = (channel or "").strip().lower()

    if normalized_channel == INPUT_TEST_CHANNEL:
        return _run_input_test_graph(initial_state, config)

    if normalized_channel == ROUTER_TEST_CHANNEL:
        return _run_router_test_graph(initial_state, config)

    if normalized_channel == RAG_TEST_CHANNEL:
        return _run_rag_test_graph(initial_state, config)

    final_state = hr_graph.invoke(initial_state, config=config)
    legacy_result = final_state.get("legacy_result") or {}

    if legacy_result:
        return {
            **legacy_result,
            "graph": {
                "enabled": True,
                "route": final_state.get("route"),
                "thread_id": config["configurable"]["thread_id"],
                "input_nodes_extracted": True,
            },
        }

    return {
        "status": final_state.get("status", "ok"),
        "reply": final_state.get("reply") or final_state.get("text") or "",
        "current_stage": final_state.get("next_stage") or final_state.get("current_stage"),
        "requires_human": bool(final_state.get("requires_human", False)),
        "risk_level": final_state.get("risk_level", "low"),
        "intent": final_state.get("intent"),
        "sources": final_state.get("sources", []),
        "graph": {
            "enabled": True,
            "route": final_state.get("route"),
            "thread_id": config["configurable"]["thread_id"],
            "input_nodes_extracted": True,
        },
    }
