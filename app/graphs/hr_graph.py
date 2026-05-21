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
from app.graphs.hr_routes import route_after_answer_check, route_after_grading
from app.graphs.hr_state import HRState


def build_hr_graph():
    """
    Build the LangGraph MVP for the HR agent.

    Current active route:
        START -> normalize_input -> legacy_orchestrator -> save_output -> END

    The first real input nodes are already registered:
        load_conversation
        save_incoming_message

    They are intentionally not wired into the active route yet because the
    legacy orchestrator still performs those DB side effects internally. The
    next cut will remove that responsibility from the legacy path and then wire:
        normalize_input -> load_conversation -> save_incoming_message -> route_message
    """
    workflow = StateGraph(HRState)

    # Core input nodes.
    workflow.add_node("normalize_input", normalize_input_node)
    workflow.add_node("load_conversation", load_conversation_node)
    workflow.add_node("save_incoming_message", save_incoming_message_node)

    # Compatibility node.
    workflow.add_node("legacy_orchestrator", legacy_orchestrator_node)

    # Native RAG nodes prepared for the next extraction steps.
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


hr_graph = build_hr_graph()


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
    initial_state: HRState = {
        "channel": channel,
        "channel_user_id": channel_user_id,
        "username": username,
        "phone": phone,
        "message": message,
        "external_message_id": external_message_id,
    }

    config = {
        "configurable": {
            "thread_id": f"{channel}:{channel_user_id}",
        }
    }

    final_state = hr_graph.invoke(initial_state, config=config)
    legacy_result = final_state.get("legacy_result") or {}

    if legacy_result:
        # Preserve the current API response shape while adding graph metadata.
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
