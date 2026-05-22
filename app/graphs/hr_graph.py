import os
from typing import Any

from langgraph.graph import END, START, StateGraph

from app.graphs.hr_nodes_classifier import classify_message_node, contextual_rewrite_node
from app.graphs.hr_nodes_core import (
    load_conversation_node,
    normalize_input_node,
    save_assistant_message_node,
    save_incoming_message_node,
)
from app.graphs.hr_nodes_lead import ingest_lead_node
from app.graphs.hr_nodes_memory import build_conversation_memory_node
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
from app.graphs.hr_nodes_response_guard import profile_response_guard_node
from app.graphs.hr_nodes_review import review_new_information_node
from app.graphs.hr_nodes_router import route_message_node
from app.graphs.hr_nodes_stubs import route_stub_response_node
from app.graphs.hr_nodes_substance import substance_disclosure_analysis_node
from app.graphs.hr_nodes_web_search import tavily_web_search_node
from app.graphs.hr_routes import route_after_grading, route_after_grading_or_web
from app.graphs.hr_state import HRState


INPUT_TEST_CHANNEL = "test_input_nodes"
ROUTER_TEST_CHANNEL = "test_router_nodes"
RAG_TEST_CHANNEL = "test_rag_nodes"
RAG_REPLACEMENT_TEST_CHANNEL = "test_rag_replacement"
FULL_ROUTER_TEST_CHANNEL = "test_full_router"
ORCHESTRATE_GRAPH_TEST_CHANNEL = "test_orchestrate_graph"


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def build_hr_graph():
    workflow = StateGraph(HRState)
    workflow.add_node("normalize_input", normalize_input_node)
    workflow.add_node("legacy_orchestrator", legacy_orchestrator_node)
    workflow.add_node("save_output", save_output_node)
    workflow.add_edge(START, "normalize_input")
    workflow.add_edge("normalize_input", "legacy_orchestrator")
    workflow.add_edge("legacy_orchestrator", "save_output")
    workflow.add_edge("save_output", END)
    return workflow.compile()


def build_hr_input_test_graph():
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
    return "retrieve_documents" if state.get("route") == "rag" else "save_output"


def _route_after_full_router(state: HRState) -> str:
    route = state.get("route")
    if route == "rag":
        return "retrieve_documents"
    if route == "web_review":
        return "tavily_web_search"
    return "route_stub_response"


def _route_after_rag_answer_check(state: HRState) -> str:
    return "save_output" if state.get("answer_check") == "PASS" else "fallback_no_context"


def _route_after_rag_replacement_answer_check(state: HRState) -> str:
    return "save_assistant_message" if state.get("answer_check") == "PASS" else "fallback_no_context"


def _route_after_rag_replacement_fallback(state: HRState) -> str:
    reply = (state.get("reply") or state.get("text") or "").strip()
    return "save_assistant_message" if reply else "save_output"


def _add_rag_nodes(workflow: StateGraph):
    workflow.add_node("retrieve_documents", retrieve_documents_node)
    workflow.add_node("grade_documents", grade_documents_node)
    workflow.add_node("fallback_no_context", fallback_no_context_node)
    workflow.add_node("generate_answer", generate_answer_node)
    workflow.add_node("hallucination_check", hallucination_check_node)
    workflow.add_node("answer_check", answer_check_node)


def build_hr_rag_test_graph():
    workflow = StateGraph(HRState)
    workflow.add_node("normalize_input", normalize_input_node)
    workflow.add_node("load_conversation", load_conversation_node)
    workflow.add_node("save_incoming_message", save_incoming_message_node)
    workflow.add_node("route_message", route_message_node)
    _add_rag_nodes(workflow)
    workflow.add_node("save_output", save_output_node)

    workflow.add_edge(START, "normalize_input")
    workflow.add_edge("normalize_input", "load_conversation")
    workflow.add_edge("load_conversation", "save_incoming_message")
    workflow.add_edge("save_incoming_message", "route_message")
    workflow.add_conditional_edges(
        "route_message",
        _route_after_rag_test_router,
        {"retrieve_documents": "retrieve_documents", "save_output": "save_output"},
    )
    workflow.add_edge("retrieve_documents", "grade_documents")
    workflow.add_conditional_edges(
        "grade_documents",
        route_after_grading,
        {"generate_answer": "generate_answer", "fallback_no_context": "fallback_no_context"},
    )
    workflow.add_edge("generate_answer", "hallucination_check")
    workflow.add_edge("hallucination_check", "answer_check")
    workflow.add_conditional_edges(
        "answer_check",
        _route_after_rag_answer_check,
        {"save_output": "save_output", "fallback_no_context": "fallback_no_context"},
    )
    workflow.add_edge("fallback_no_context", "save_output")
    workflow.add_edge("save_output", END)
    return workflow.compile()


def build_hr_rag_replacement_test_graph():
    workflow = StateGraph(HRState)
    workflow.add_node("normalize_input", normalize_input_node)
    workflow.add_node("load_conversation", load_conversation_node)
    workflow.add_node("save_incoming_message", save_incoming_message_node)
    workflow.add_node("route_message", route_message_node)
    _add_rag_nodes(workflow)
    workflow.add_node("save_assistant_message", save_assistant_message_node)
    workflow.add_node("save_output", save_output_node)

    workflow.add_edge(START, "normalize_input")
    workflow.add_edge("normalize_input", "load_conversation")
    workflow.add_edge("load_conversation", "save_incoming_message")
    workflow.add_edge("save_incoming_message", "route_message")
    workflow.add_conditional_edges(
        "route_message",
        _route_after_rag_test_router,
        {"retrieve_documents": "retrieve_documents", "save_output": "save_output"},
    )
    workflow.add_edge("retrieve_documents", "grade_documents")
    workflow.add_conditional_edges(
        "grade_documents",
        route_after_grading,
        {"generate_answer": "generate_answer", "fallback_no_context": "fallback_no_context"},
    )
    workflow.add_edge("generate_answer", "hallucination_check")
    workflow.add_edge("hallucination_check", "answer_check")
    workflow.add_conditional_edges(
        "answer_check",
        _route_after_rag_replacement_answer_check,
        {"save_assistant_message": "save_assistant_message", "fallback_no_context": "fallback_no_context"},
    )
    workflow.add_conditional_edges(
        "fallback_no_context",
        _route_after_rag_replacement_fallback,
        {"save_assistant_message": "save_assistant_message", "save_output": "save_output"},
    )
    workflow.add_edge("save_assistant_message", "save_output")
    workflow.add_edge("save_output", END)
    return workflow.compile()


def build_hr_full_router_test_graph():
    workflow = StateGraph(HRState)
    workflow.add_node("normalize_input", normalize_input_node)
    workflow.add_node("load_conversation", load_conversation_node)
    workflow.add_node("build_conversation_memory", build_conversation_memory_node)
    workflow.add_node("save_incoming_message", save_incoming_message_node)
    workflow.add_node("ingest_lead", ingest_lead_node)
    workflow.add_node("substance_disclosure_analysis", substance_disclosure_analysis_node)
    workflow.add_node("contextual_rewrite", contextual_rewrite_node)
    workflow.add_node("classify_message", classify_message_node)
    workflow.add_node("route_message", route_message_node)
    workflow.add_node("route_stub_response", route_stub_response_node)
    workflow.add_node("profile_response_guard", profile_response_guard_node)
    workflow.add_node("tavily_web_search", tavily_web_search_node)
    workflow.add_node("review_new_information", review_new_information_node)
    _add_rag_nodes(workflow)
    workflow.add_node("save_assistant_message", save_assistant_message_node)
    workflow.add_node("save_output", save_output_node)

    workflow.add_edge(START, "normalize_input")
    workflow.add_edge("normalize_input", "load_conversation")
    workflow.add_edge("load_conversation", "build_conversation_memory")
    workflow.add_edge("build_conversation_memory", "save_incoming_message")
    workflow.add_edge("save_incoming_message", "ingest_lead")
    workflow.add_edge("ingest_lead", "substance_disclosure_analysis")
    workflow.add_edge("substance_disclosure_analysis", "contextual_rewrite")
    workflow.add_edge("contextual_rewrite", "classify_message")
    workflow.add_edge("classify_message", "route_message")
    workflow.add_conditional_edges(
        "route_message",
        _route_after_full_router,
        {
            "retrieve_documents": "retrieve_documents",
            "tavily_web_search": "tavily_web_search",
            "route_stub_response": "route_stub_response",
        },
    )
    workflow.add_edge("tavily_web_search", "review_new_information")
    workflow.add_edge("review_new_information", "route_stub_response")
    workflow.add_edge("route_stub_response", "profile_response_guard")
    workflow.add_edge("profile_response_guard", "save_assistant_message")
    workflow.add_edge("retrieve_documents", "grade_documents")
    workflow.add_conditional_edges(
        "grade_documents",
        route_after_grading_or_web,
        {
            "generate_answer": "generate_answer",
            "tavily_web_search": "tavily_web_search",
            "fallback_no_context": "fallback_no_context",
        },
    )
    workflow.add_edge("generate_answer", "hallucination_check")
    workflow.add_edge("hallucination_check", "answer_check")
    workflow.add_conditional_edges(
        "answer_check",
        _route_after_rag_replacement_answer_check,
        {"save_assistant_message": "save_assistant_message", "fallback_no_context": "fallback_no_context"},
    )
    workflow.add_conditional_edges(
        "fallback_no_context",
        _route_after_rag_replacement_fallback,
        {"save_assistant_message": "save_assistant_message", "save_output": "save_output"},
    )
    workflow.add_edge("save_assistant_message", "save_output")
    workflow.add_edge("save_output", END)
    return workflow.compile()


hr_graph = build_hr_graph()
hr_input_test_graph = build_hr_input_test_graph()
hr_router_test_graph = build_hr_router_test_graph()
hr_rag_test_graph = build_hr_rag_test_graph()
hr_rag_replacement_test_graph = build_hr_rag_replacement_test_graph()
hr_full_router_test_graph = build_hr_full_router_test_graph()


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
    return {"configurable": {"thread_id": f"{channel}:{channel_user_id}"}}


def _base_payload(final_state: HRState) -> dict[str, Any]:
    retrieved_docs = final_state.get("retrieved_docs", []) or []
    relevant_docs = final_state.get("relevant_docs", []) or []
    web_results = final_state.get("web_results", []) or []
    memory = final_state.get("conversation_memory") or {}
    return {
        "status": final_state.get("status", "ok"),
        "conversation_key": final_state.get("conversation_key"),
        "conversation_id": final_state.get("conversation_id"),
        "candidate_id": final_state.get("candidate_id"),
        "current_stage": final_state.get("current_stage"),
        "next_stage": final_state.get("next_stage"),
        "incoming_message_saved": bool(final_state.get("incoming_message_saved", False)),
        "assistant_message_saved": bool(final_state.get("assistant_message_saved", False)),
        "intent": final_state.get("intent"),
        "risk_level": final_state.get("risk_level"),
        "requires_human": bool(final_state.get("requires_human", False)),
        "requires_rag": bool(final_state.get("requires_rag", False)),
        "requires_clarification": bool(final_state.get("requires_clarification", False)),
        "reason": final_state.get("reason"),
        "selected_route": final_state.get("route"),
        "classifier_intent": final_state.get("classifier_intent"),
        "classifier_confidence": final_state.get("classifier_confidence"),
        "safe_reply_mode": final_state.get("safe_reply_mode"),
        "conversation_memory_built": bool(memory),
        "current_may_reference_previous": bool(memory.get("current_may_reference_previous", False)),
        "lead_ingestion": final_state.get("lead_ingestion"),
        "substance_disclosure_analysis": final_state.get("substance_disclosure_analysis"),
        "contextual_rewrite": final_state.get("contextual_rewrite"),
        "profile_followup_plan": final_state.get("profile_followup_plan"),
        "profile_response_guard": final_state.get("profile_response_guard"),
        "requires_web_lookup": bool(final_state.get("requires_web_lookup", False)),
        "web_search_used": bool(final_state.get("web_search_used", False)),
        "web_results_count": len(web_results),
        "web_search_error": final_state.get("web_search_error"),
        "new_information_review": final_state.get("new_information_review"),
        "route_stub_used": bool(final_state.get("route_stub_used", False)),
        "greeting_real_flow_used": bool(final_state.get("greeting_real_flow_used", False)),
        "profile_real_flow_used": bool(final_state.get("profile_real_flow_used", False)),
        "human_handoff_real_flow_used": bool(final_state.get("human_handoff_real_flow_used", False)),
        "clarification_real_flow_used": bool(final_state.get("clarification_real_flow_used", False)),
        "fallback_real_flow_used": bool(final_state.get("fallback_real_flow_used", False)),
        "policy_boundary_real_flow_used": bool(final_state.get("policy_boundary_real_flow_used", False)),
        "retrieved_docs_count": len(retrieved_docs),
        "relevant_docs_count": len(relevant_docs),
        "docs_are_relevant": bool(final_state.get("docs_are_relevant", False)),
        "hallucination_check": final_state.get("hallucination_check"),
        "answer_check": final_state.get("answer_check"),
        "reply": final_state.get("reply") or final_state.get("text") or "",
        "sources": final_state.get("sources", []),
        "events": final_state.get("events", []),
    }


def _run_input_test_graph(initial_state: HRState, config: dict[str, Any]) -> dict[str, Any]:
    final_state = hr_input_test_graph.invoke(initial_state, config=config)
    payload = _base_payload(final_state)
    payload["graph"] = {
        "enabled": True,
        "route": "input_nodes_test",
        "thread_id": config["configurable"]["thread_id"],
        "input_nodes_extracted": True,
    }
    return payload


def _run_router_test_graph(initial_state: HRState, config: dict[str, Any]) -> dict[str, Any]:
    final_state = hr_router_test_graph.invoke(initial_state, config=config)
    payload = _base_payload(final_state)
    payload["graph"] = {
        "enabled": True,
        "route": "router_test",
        "selected_route": final_state.get("route"),
        "thread_id": config["configurable"]["thread_id"],
        "input_nodes_extracted": True,
        "router_node_extracted": True,
    }
    return payload


def _run_rag_test_graph(initial_state: HRState, config: dict[str, Any]) -> dict[str, Any]:
    final_state = hr_rag_test_graph.invoke(initial_state, config=config)
    payload = _base_payload(final_state)
    payload["graph"] = {
        "enabled": True,
        "route": "rag_test",
        "selected_route": final_state.get("route"),
        "thread_id": config["configurable"]["thread_id"],
        "input_nodes_extracted": True,
        "router_node_extracted": True,
        "rag_nodes_extracted": True,
        "assistant_persistence_enabled": False,
    }
    return payload


def _run_rag_replacement_test_graph(initial_state: HRState, config: dict[str, Any]) -> dict[str, Any]:
    final_state = hr_rag_replacement_test_graph.invoke(initial_state, config=config)
    payload = _base_payload(final_state)
    payload["graph"] = {
        "enabled": True,
        "route": "rag_replacement_test",
        "selected_route": final_state.get("route"),
        "thread_id": config["configurable"]["thread_id"],
        "input_nodes_extracted": True,
        "router_node_extracted": True,
        "rag_nodes_extracted": True,
        "assistant_persistence_enabled": True,
    }
    return payload


def _run_full_router_test_graph(
    initial_state: HRState,
    config: dict[str, Any],
    *,
    graph_route: str = "full_router_test",
) -> dict[str, Any]:
    final_state = hr_full_router_test_graph.invoke(initial_state, config=config)
    payload = _base_payload(final_state)
    payload["graph"] = {
        "enabled": True,
        "route": graph_route,
        "selected_route": final_state.get("route"),
        "thread_id": config["configurable"]["thread_id"],
        "input_nodes_extracted": True,
        "memory_node_enabled": True,
        "lead_ingestion_node_enabled": True,
        "substance_analysis_node_enabled": True,
        "contextual_rewrite_enabled": True,
        "profile_response_guard_enabled": True,
        "classifier_node_enabled": True,
        "router_node_extracted": True,
        "rag_nodes_extracted": True,
        "web_review_enabled": True,
        "assistant_persistence_enabled": True,
        "legacy_bypassed": True,
        "feature_flag": _env_bool("USE_LANGGRAPH_ORCHESTRATOR", False),
    }
    return payload


def _run_legacy_graph(initial_state: HRState, config: dict[str, Any]) -> dict[str, Any]:
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
                "legacy_bypassed": False,
                "feature_flag": _env_bool("USE_LANGGRAPH_ORCHESTRATOR", False),
            },
        }

    payload = _base_payload(final_state)
    payload["graph"] = {
        "enabled": True,
        "route": final_state.get("route"),
        "thread_id": config["configurable"]["thread_id"],
        "input_nodes_extracted": True,
        "legacy_bypassed": False,
        "feature_flag": _env_bool("USE_LANGGRAPH_ORCHESTRATOR", False),
    }
    return payload


def run_hr_graph_message(
    *,
    channel: str,
    channel_user_id: str,
    message: str,
    username: str | None = None,
    phone: str | None = None,
    external_message_id: str | None = None,
) -> dict[str, Any]:
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
    if normalized_channel == RAG_REPLACEMENT_TEST_CHANNEL:
        return _run_rag_replacement_test_graph(initial_state, config)
    if normalized_channel == FULL_ROUTER_TEST_CHANNEL:
        return _run_full_router_test_graph(initial_state, config)
    if normalized_channel == ORCHESTRATE_GRAPH_TEST_CHANNEL:
        return _run_full_router_test_graph(
            initial_state,
            config,
            graph_route="orchestrate_graph_test",
        )

    if _env_bool("USE_LANGGRAPH_ORCHESTRATOR", False):
        return _run_full_router_test_graph(
            initial_state,
            config,
            graph_route="langgraph_orchestrator",
        )

    return _run_legacy_graph(initial_state, config)
