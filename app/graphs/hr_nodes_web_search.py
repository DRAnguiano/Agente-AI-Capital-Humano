import os
from typing import Any

import httpx

from app.graphs.hr_state import HRState


TAVILY_SEARCH_URL = "https://api.tavily.com/search"


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _to_int(value: str | None, default: int) -> int:
    try:
        return int(value) if value is not None else default
    except Exception:
        return default


def tavily_web_search_node(state: HRState) -> dict[str, Any]:
    """
    Search the web through Tavily for contextual understanding only.

    This node must not generate final candidate replies. Its output is reviewed
    by review_new_information_node before routing/answering.
    """
    if not _env_bool("WEB_SEARCH_ENABLED", False):
        return {
            "web_results": [],
            "web_search_used": False,
            "web_search_error": "web_search_disabled",
            "events": [{"type": "web_search_skipped", "reason": "disabled"}],
        }

    api_key = os.getenv("TAVILY_API_KEY", "").strip()
    if not api_key:
        return {
            "web_results": [],
            "web_search_used": False,
            "web_search_error": "missing_tavily_api_key",
            "events": [{"type": "web_search_skipped", "reason": "missing_tavily_api_key"}],
        }

    classifier = state.get("classifier") or {}
    raw_query = state.get("web_query") or classifier.get("web_query") or state.get("message") or ""
    query = f"{raw_query} significado México transporte carretera operador tractocamión"
    max_results = _to_int(os.getenv("WEB_SEARCH_MAX_RESULTS"), 3)
    timeout_s = _to_int(os.getenv("WEB_SEARCH_TIMEOUT_SECONDS"), 8)

    payload = {
        "api_key": api_key,
        "query": query,
        "search_depth": os.getenv("TAVILY_SEARCH_DEPTH", "basic"),
        "max_results": max_results,
        "include_answer": True,
        "include_raw_content": False,
    }

    try:
        with httpx.Client(timeout=float(timeout_s)) as client:
            response = client.post(TAVILY_SEARCH_URL, json=payload)
            response.raise_for_status()
            data = response.json()
    except Exception as exc:
        return {
            "web_results": [],
            "web_search_used": False,
            "web_search_error": f"{type(exc).__name__}: {exc}",
            "events": [
                {
                    "type": "web_search_failed",
                    "query": query,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            ],
        }

    results = []
    for item in data.get("results", []) or []:
        results.append(
            {
                "title": item.get("title"),
                "url": item.get("url"),
                "content": item.get("content"),
                "score": item.get("score"),
            }
        )

    return {
        "web_query": query,
        "web_results": results,
        "web_answer": data.get("answer"),
        "web_search_used": True,
        "web_search_error": None,
        "events": [
            {
                "type": "web_search_completed",
                "query": query,
                "result_count": len(results),
            }
        ],
    }
