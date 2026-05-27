from __future__ import annotations

import logging
import time
from typing import Any, Callable

LOGGER = logging.getLogger("hr_graph_timing")
_PATCHED_ATTR = "_hr_timing_add_node_patched"


def timed_graph_node(node_name: str, fn: Callable[[dict[str, Any]], dict[str, Any]]) -> Callable[[dict[str, Any]], dict[str, Any]]:
    """Wrap a LangGraph node and append deterministic timing data.

    The wrapper does not change business behavior. It only adds:
    - timings[node_name] = elapsed milliseconds
    - events[] += node_timing event

    This lets us identify latency sources before cutting nodes or changing prompts.
    """
    if getattr(fn, "_hr_timing_wrapped", False):
        return fn

    def wrapper(state: dict[str, Any]) -> dict[str, Any]:
        start = time.perf_counter()
        status = "ok"
        error: str | None = None
        update: dict[str, Any] = {}

        try:
            result = fn(state)  # type: ignore[arg-type]
            update = result if isinstance(result, dict) else {}
            return update
        except Exception as exc:
            status = "error"
            error = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            elapsed_ms = round((time.perf_counter() - start) * 1000, 2)

            previous_timings = state.get("timings") or {}
            timings = dict(previous_timings) if isinstance(previous_timings, dict) else {}
            timings[node_name] = round(float(timings.get(node_name) or 0.0) + elapsed_ms, 2)

            events = list(update.get("events") or [])
            events.append(
                {
                    "type": "node_timing",
                    "node": node_name,
                    "elapsed_ms": elapsed_ms,
                    "status": status,
                    "error": error,
                }
            )

            update["timings"] = timings
            update["events"] = events

            LOGGER.info("hr_node_timing node=%s elapsed_ms=%s status=%s", node_name, elapsed_ms, status)

    wrapper.__name__ = f"timed_{getattr(fn, '__name__', node_name)}"
    setattr(wrapper, "_hr_timing_wrapped", True)
    return wrapper


def install_stategraph_timing_patch() -> None:
    """Patch LangGraph's StateGraph.add_node once so every node is timed."""
    try:
        from langgraph.graph import StateGraph
    except Exception:
        LOGGER.exception("Could not import StateGraph for timing patch")
        return

    if getattr(StateGraph, _PATCHED_ATTR, False):
        return

    original_add_node = StateGraph.add_node

    def timed_add_node(self: Any, node: Any, action: Any = None, *args: Any, **kwargs: Any) -> Any:
        node_name = str(node) if isinstance(node, str) else getattr(node, "__name__", "unknown_node")
        wrapped_action = action

        if callable(action):
            wrapped_action = timed_graph_node(node_name, action)
        elif callable(node) and action is None:
            wrapped_action = timed_graph_node(node_name, node)
            return original_add_node(self, wrapped_action, *args, **kwargs)

        return original_add_node(self, node, wrapped_action, *args, **kwargs)

    StateGraph.add_node = timed_add_node
    setattr(StateGraph, _PATCHED_ATTR, True)
    LOGGER.info("Installed HR StateGraph timing patch")
