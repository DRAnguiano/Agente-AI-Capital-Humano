from __future__ import annotations

from app.graphs.hr_timing import install_stategraph_timing_patch

"""LangGraph workflows for the HR recruiting agent."""

# Instrument LangGraph node registration before app.graphs.hr_graph builds graphs.
# This keeps timing centralized and avoids editing every workflow.add_node call.
install_stategraph_timing_patch()
