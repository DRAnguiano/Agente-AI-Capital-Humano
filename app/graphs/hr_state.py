from operator import add
from typing import Annotated, Any, Literal
from typing_extensions import TypedDict


RouteName = Literal[
    "legacy_orchestrator",
    "rag",
    "profile",
    "human_handoff",
    "clarification",
    "fallback",
    "web_review",
    "policy_boundary",
]

CheckResult = Literal["PASS", "FAIL", "SKIP"]


class HRState(TypedDict, total=False):
    """
    Shared state for the HR recruiting graph.

    MVP note:
    - The first production step keeps the current orchestrator as a compatibility node.
    - RAG-specific keys are included now so we can progressively move debt out of
      app/orchestrator.py without changing the external API contract.
    """

    # Input from API / Chatwoot / tests
    channel: str
    channel_user_id: str
    username: str | None
    phone: str | None
    message: str
    external_message_id: str | None

    # Optional Chatwoot metadata. The webhook migration will use these later.
    account_id: int | str | None
    chatwoot_conversation_id: int | str | None
    chatwoot_message_id: int | str | None
    chatwoot_contact_id: int | str | None

    # Internal identity / DB state
    conversation_key: str
    conversation_id: int | None
    candidate_id: int | None
    current_stage: str
    next_stage: str
    conversation_snapshot: dict[str, Any]
    profile_snapshot: dict[str, Any]
    history_messages: list[dict[str, Any]]
    incoming_message_saved: bool
    assistant_message_saved: bool

    # Classifier / semantic routing
    classifier: dict[str, Any]
    classifier_intent: str
    classifier_confidence: float
    safe_reply_mode: str
    requires_web_lookup: bool
    web_query: str | None

    # Routing / risk / intent
    route: RouteName
    intent: str
    risk_level: str
    requires_human: bool
    requires_rag: bool
    requires_clarification: bool
    reason: str | None
    route_detection: dict[str, Any]
    route_stub_used: bool
    profile_real_flow_used: bool
    human_handoff_real_flow_used: bool
    clarification_real_flow_used: bool
    fallback_real_flow_used: bool
    policy_boundary_real_flow_used: bool

    # Candidate profile
    extracted_fields: dict[str, Any]
    profile_updates: dict[str, Any]
    profile_private_context: dict[str, Any]
    profile_updated: bool
    stage_updated: bool
    profile_event_logged: bool

    # RAG state
    question: str
    retrieved_docs: list[dict[str, Any]]
    relevant_docs: list[dict[str, Any]]
    docs_are_relevant: bool
    sources: list[dict[str, Any]]

    # Web review state
    web_results: list[dict[str, Any]]
    web_answer: str | None
    web_search_used: bool
    web_search_error: str | None
    new_information_review: dict[str, Any]

    # Generation / grading
    draft_answer: str
    hallucination_check: CheckResult
    answer_check: CheckResult

    # Final output
    reply: str
    text: str
    chunks: list[str]
    status: str
    labels: list[str]
    events: Annotated[list[dict[str, Any]], add]

    # Compatibility payload returned by the legacy orchestrator node.
    legacy_result: dict[str, Any]
