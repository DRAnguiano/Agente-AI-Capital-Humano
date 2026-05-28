"""Lead memory v2 package.

PostgreSQL stores operational lead memory for Chatwoot/RH analytics.
This package should not decide the conversation by itself; it only records and
retrieves facts, messages and funnel state.
"""

from app.lead_memory.repository import (
    get_lead_memory,
    log_lead_event,
    save_lead_message,
    upsert_lead_identity,
    upsert_lead_fact,
    update_lead_summary,
)

__all__ = [
    "get_lead_memory",
    "log_lead_event",
    "save_lead_message",
    "upsert_lead_identity",
    "upsert_lead_fact",
    "update_lead_summary",
]
