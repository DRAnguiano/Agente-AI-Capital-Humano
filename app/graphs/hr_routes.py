import os

from app.graphs.hr_state import HRState


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def route_after_router(state: HRState) -> str:
    return state.get("route", "fallback")


def route_after_grading(state: HRState) -> str:
    if state.get("docs_are_relevant"):
        return "generate_answer"
    return "fallback_no_context"


def route_after_grading_or_web(state: HRState) -> str:
    if state.get("docs_are_relevant"):
        return "generate_answer"
    if _env_bool("WEB_SEARCH_ENABLED", False):
        return "tavily_web_search"
    return "fallback_no_context"


def route_after_answer_check(state: HRState) -> str:
    if state.get("answer_check") == "PASS":
        return "save_output"
    return "human_handoff"
