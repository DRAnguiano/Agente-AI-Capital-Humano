from app.graphs.hr_state import HRState


def route_after_router(state: HRState) -> str:
    """Route to the next functional branch after initial classification."""
    return state.get("route", "fallback")


def route_after_grading(state: HRState) -> str:
    """Generate only when the retrieved internal context is relevant."""
    if state.get("docs_are_relevant"):
        return "generate_answer"
    return "fallback_no_context"


def route_after_answer_check(state: HRState) -> str:
    """If an answer is not safe/useful, force human handoff instead of retry loops."""
    if state.get("answer_check") == "PASS":
        return "save_output"
    return "human_handoff"
