from __future__ import annotations

from app.graphs.hr_timing import install_stategraph_timing_patch

"""LangGraph workflows for the HR recruiting agent."""

# Instrument LangGraph node registration before app.graphs.hr_graph builds graphs.
# This keeps timing centralized and avoids editing every workflow.add_node call.
install_stategraph_timing_patch()

# Phase 1 optimization: compact RAG context before expensive generation.
# Imported after timing patch so patched RAG nodes are also timed when the graph is built.
try:
    from app.graphs.hr_rag_optimized import install_optimized_rag_patch

    install_optimized_rag_patch()
except Exception:
    # Do not block API startup if the optimization patch fails.
    # The original graph remains available for debugging.
    import logging

    logging.getLogger("hr_rag_optimized").exception("Could not install optimized RAG patch")
