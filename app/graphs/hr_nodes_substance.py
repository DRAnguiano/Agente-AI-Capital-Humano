import json
from datetime import datetime, timezone
from typing import Any

from app.db import log_event, sync_conversation_risk_from_profile, update_candidate_profile
from app.graphs.hr_state import HRState
from app.indexer import call_llm


STATUS_VALUES = {
    "NONE",
    "AMBIGUOUS",
    "ACTIVE_OR_INTENDED_USE",
    "RECENT_PAST_USE",
    "PAST_USE",
    "MEDICAL_TREATMENT",
}
CONTEXT_VALUES = {
    "para_aguantar",
    "recreativo",
    "medicamento_recetado",
    "prueba_orina",
    "desconocido",
}
RISK_VALUES = {"none", "medium", "high"}
CATEGORY_VALUES = {
    "active_or_intended_use",
    "recent_past_use",
    "past_use",
    "medical_treatment",
    "ambiguous",
}


def _json_from_text(text: str) -> dict[str, Any]:
    raw = (text or "").strip()
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end <= start:
        return {}
    try:
        return json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return {}


def _clean_text(value: Any, max_len: int = 500) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text[:max_len]


def _clean_float(value: Any, default: float = 0.0) -> float:
    try:
        score = float(value)
    except Exception:
        score = default
    return max(0.0, min(1.0, score))


def _clean_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "si", "sí"}
    return bool(value)


def _clean_choice(value: Any, allowed: set[str], default: str) -> str:
    text = str(value or default).strip()
    if text in allowed:
        return text
    upper = text.upper()
    if upper in allowed:
        return upper
    lower = text.lower()
    if lower in allowed:
        return lower
    return default


def _web_context_text(state: HRState) -> str:
    results = state.get("web_results") or []
    web_answer = state.get("web_answer")
    chunks: list[str] = []
    if web_answer:
        chunks.append(f"WEB_ANSWER: {web_answer}")
    for item in results[:3]:
        title = item.get("title") or "sin título"
        content = item.get("content") or ""
        chunks.append(f"- {title}: {content[:700]}")
    return "\n".join(chunks) if chunks else "No hay contexto web disponible."


def _default_analysis(reason: str = "no_substance_signal") -> dict[str, Any]:
    return {
        "detected": False,
        "status": "NONE",
        "context": "desconocido",
        "last_use_text": None,
        "operational_risk": "none",
        "requires_human": False,
        "requires_review": False,
        "analytics_flag": False,
        "analytics_category": None,
        "raw_mention": None,
        "confidence": 0.0,
        "needs_web_context": False,
        "needs_clarification": False,
        "reason": reason,
    }


def _normalize_analysis(payload: dict[str, Any], message: str) -> dict[str, Any]:
    data = payload.get("substance_disclosure") if isinstance(payload.get("substance_disclosure"), dict) else payload

    status = _clean_choice(data.get("status"), STATUS_VALUES, "NONE")
    context = _clean_choice(data.get("context"), CONTEXT_VALUES, "desconocido")
    risk = _clean_choice(data.get("operational_risk"), RISK_VALUES, "none")
    category = data.get("analytics_category")
    if category is not None:
        category = _clean_choice(category, CATEGORY_VALUES, "ambiguous")

    confidence = _clean_float(data.get("confidence"), 0.0)
    detected = status != "NONE" and confidence >= 0.45

    if not detected:
        return _default_analysis(data.get("reason") or "analysis_below_threshold")

    # Business policy: past use is captured for analytics and can continue capture.
    # Active/intended use for staying awake is the restrictive safety case.
    if status in {"RECENT_PAST_USE", "PAST_USE"}:
        risk = "medium"
        requires_human = False
        requires_review = False
        analytics_flag = True
        if not category:
            category = "recent_past_use" if status == "RECENT_PAST_USE" else "past_use"
    elif status == "ACTIVE_OR_INTENDED_USE":
        risk = "high"
        requires_human = True
        requires_review = True
        analytics_flag = True
        category = category or "active_or_intended_use"
    elif status == "MEDICAL_TREATMENT":
        risk = "medium"
        requires_human = False
        requires_review = False
        analytics_flag = True
        category = category or "medical_treatment"
    else:
        requires_human = False
        requires_review = False
        analytics_flag = True
        category = category or "ambiguous"

    return {
        "detected": True,
        "status": status,
        "context": context,
        "last_use_text": _clean_text(data.get("last_use_text"), 160),
        "operational_risk": risk,
        "requires_human": requires_human,
        "requires_review": requires_review,
        "analytics_flag": analytics_flag,
        "analytics_category": category,
        "raw_mention": _clean_text(data.get("raw_mention") or message, 500),
        "confidence": confidence,
        "needs_web_context": _clean_bool(data.get("needs_web_context", False)),
        "needs_clarification": _clean_bool(data.get("needs_clarification", False)) or confidence < 0.75,
        "reason": _clean_text(data.get("reason"), 500) or "substance_signal_detected",
    }


def _analysis_prompt(state: HRState) -> str:
    message = state.get("message") or ""
    memory = state.get("conversation_memory") or {}
    profile = state.get("profile_snapshot") or {}
    lead = state.get("lead_ingestion") or {}
    web_context = _web_context_text(state)

    return f"""
You are a specialized contextual analysis node for a Mexican trucking recruiting graph.
Do not answer the candidate. Return JSON only.

Context:
- The role is operador/trailero de tractocamión / quinta rueda.
- Candidate spelling may be informal or incorrect: doopin, doping, miados, pastillas, pericos, etc.
- Use conversation context, not isolated keywords.
- You may use web context only to understand slang in trucking/recruiting context.
- Never infer or explain whether a toxicology/urine test will be positive or negative.
- Never provide detection windows or advice to evade tests.
- This output is for Capital Humano review and later analytics/PowerBI.

Classification policy:
- If the candidate only asks whether there are urine/doping tests: AMBIGUOUS, context=prueba_orina, risk=none or medium, analytics_flag=true.
- If the candidate mentions substances/pills/pericos used or intended "para aguantar" driving/work: ACTIVE_OR_INTENDED_USE, context=para_aguantar, operational_risk=high, requires_human=true.
- If the candidate says last use was around 1 month ago: RECENT_PAST_USE, operational_risk=medium, requires_human=false, analytics_flag=true. The process may continue, but keep analytics signal.
- If last use was 2-3+ months ago: PAST_USE, operational_risk=medium, requires_human=false, analytics_flag=true.
- If the candidate refers to prescribed medication/treatment: MEDICAL_TREATMENT, context=medicamento_recetado, operational_risk=medium, requires_human=false, analytics_flag=true.
- If unclear but suspicious: AMBIGUOUS and needs_clarification=true.
- If no substance/test/medication signal: NONE.

Confidence policy:
- confidence >= 0.75 means actionable structured classification.
- 0.45 to 0.74 means store only if useful, but ask clarification.
- < 0.45 means NONE.

=== CURRENT MESSAGE ===
{message}

=== CONVERSATION MEMORY ===
{json.dumps(memory, ensure_ascii=False, default=str)}

=== PROFILE SNAPSHOT ===
{json.dumps(profile, ensure_ascii=False, default=str)}

=== LEAD INGESTION ===
{json.dumps(lead, ensure_ascii=False, default=str)}

=== WEB CONTEXT, IF AVAILABLE ===
{web_context}

Return JSON exactly:
{{
  "substance_disclosure": {{
    "status": "NONE | AMBIGUOUS | ACTIVE_OR_INTENDED_USE | RECENT_PAST_USE | PAST_USE | MEDICAL_TREATMENT",
    "context": "para_aguantar | recreativo | medicamento_recetado | prueba_orina | desconocido",
    "last_use_text": null,
    "operational_risk": "none | medium | high",
    "requires_human": false,
    "requires_review": false,
    "analytics_flag": false,
    "analytics_category": null,
    "raw_mention": null,
    "confidence": 0.0,
    "needs_web_context": false,
    "needs_clarification": false,
    "reason": "brief explanation for internal audit"
  }}
}}
""".strip()


def _fields_from_analysis(analysis: dict[str, Any]) -> dict[str, Any]:
    if not analysis.get("detected"):
        return {}

    payload = {
        "status": analysis.get("status"),
        "context": analysis.get("context"),
        "last_use_text": analysis.get("last_use_text"),
        "operational_risk": analysis.get("operational_risk"),
        "requires_review": analysis.get("requires_review"),
        "analytics_flag": analysis.get("analytics_flag"),
        "analytics_category": analysis.get("analytics_category"),
        "raw_mention": analysis.get("raw_mention"),
        "confidence": analysis.get("confidence"),
        "reason": analysis.get("reason"),
        "captured_at": datetime.now(timezone.utc).isoformat(),
    }

    fields = {
        "substance_disclosure": payload,
        "substance_disclosure_status": analysis.get("status"),
        "substance_disclosure_context": analysis.get("context"),
        "substance_last_use_text": analysis.get("last_use_text"),
        "substance_operational_risk": analysis.get("operational_risk"),
        "substance_requires_review": bool(analysis.get("requires_review", False)),
        "substance_analytics_flag": bool(analysis.get("analytics_flag", False)),
        "substance_analytics_category": analysis.get("analytics_category"),
        "substance_raw_mention": analysis.get("raw_mention"),
    }

    if analysis.get("operational_risk") == "high" or analysis.get("requires_human"):
        fields["risk_level"] = "high"
        fields["requires_human"] = True

    return fields


def substance_disclosure_analysis_node(state: HRState) -> dict[str, Any]:
    message = state.get("message") or ""
    conversation_key = state.get("conversation_key")

    try:
        raw = call_llm(_analysis_prompt(state))
        parsed = _json_from_text(raw)
        analysis = _normalize_analysis(parsed, message)
    except Exception as exc:
        analysis = _default_analysis(f"analysis_exception: {type(exc).__name__}: {exc}")

    fields = _fields_from_analysis(analysis)
    aggregate_risk_sync = None

    if conversation_key and fields:
        update_candidate_profile(conversation_key, fields)
        aggregate_risk_sync = sync_conversation_risk_from_profile(
            conversation_key,
            risk_level=fields.get("risk_level") or state.get("risk_level") or "low",
            requires_human=bool(fields.get("requires_human", False)),
            intent=state.get("intent"),
        )
        log_event(
            conversation_key=conversation_key,
            event_type="substance_disclosure_analyzed",
            stage_from=state.get("current_stage"),
            stage_to=state.get("current_stage"),
            intent=state.get("intent"),
            risk_level=fields.get("risk_level") or analysis.get("operational_risk") or "low",
            requires_human=bool(fields.get("requires_human", False)),
            metadata={
                "analysis": analysis,
                "updated_fields": sorted(fields.keys()),
                "aggregate_risk_sync": aggregate_risk_sync,
            },
        )

    profile_snapshot = {**(state.get("profile_snapshot") or {}), **fields}
    next_risk = aggregate_risk_sync.get("risk_level") if aggregate_risk_sync else state.get("risk_level")
    next_requires_human = (
        bool(aggregate_risk_sync.get("requires_human"))
        if aggregate_risk_sync
        else bool(state.get("requires_human", False)) or bool(fields.get("requires_human", False))
    )

    web_query = state.get("web_query")
    if analysis.get("needs_web_context") and not state.get("web_search_used"):
        web_query = (
            f"jerga '{message}' significado en contexto de trailero operador de tractocamión México "
            "doping pruebas orina sustancias"
        )

    return {
        "profile_snapshot": profile_snapshot,
        "risk_level": next_risk,
        "requires_human": next_requires_human,
        "web_query": web_query,
        "substance_disclosure_analysis": analysis,
        "events": [
            {
                "type": "substance_disclosure_analyzed",
                "detected": analysis.get("detected"),
                "status": analysis.get("status"),
                "operational_risk": analysis.get("operational_risk"),
                "analytics_flag": analysis.get("analytics_flag"),
                "needs_web_context": analysis.get("needs_web_context"),
                "needs_clarification": analysis.get("needs_clarification"),
                "confidence": analysis.get("confidence"),
                "aggregate_risk_sync": aggregate_risk_sync,
            }
        ],
    }
