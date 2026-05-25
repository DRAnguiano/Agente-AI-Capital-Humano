import json
import os
import re
from typing import Any

from app.graphs.hr_state import HRState
from app.indexer import call_llm


DEFAULT_REWRITE = {
    "rewritten_question": None,
    "normalized_terms": [],
    "reason": "rewrite_not_needed",
    "confidence": 0.0,
}


def _env_bool(name: str, default: bool = True) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _json_from_text(text: str) -> dict[str, Any]:
    raw = (text or "").strip()
    if not raw:
        return {}

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
    if not match:
        return {}

    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return {}


def _normalize_rewrite(payload: dict[str, Any], original_question: str) -> dict[str, Any]:
    data = {**DEFAULT_REWRITE, **(payload or {})}
    rewritten = str(data.get("rewritten_question") or "").strip()

    try:
        confidence = float(data.get("confidence", 0.0))
    except Exception:
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))

    if not rewritten:
        rewritten = original_question

    if len(rewritten) > 280:
        rewritten = original_question
        confidence = 0.0

    terms = data.get("normalized_terms") or []
    if not isinstance(terms, list):
        terms = []

    return {
        "rewritten_question": rewritten,
        "normalized_terms": [str(item).strip() for item in terms if str(item).strip()][:8],
        "reason": str(data.get("reason") or "rewrite_completed").strip().lower(),
        "confidence": confidence,
    }



def _is_ambiguous_cachimba_retrieval_case(state: HRState, question: str) -> bool:
    substance = state.get("substance_disclosure_analysis") or {}
    contextual = state.get("contextual_rewrite") or {}

    haystack = " ".join(
        str(x or "")
        for x in (
            question,
            contextual.get("rewritten"),
            contextual.get("original"),
            substance.get("raw_mention"),
        )
    ).lower()

    has_cachimba = any(
        term in haystack
        for term in ("cachimba", "cachimbear", "cachimbr", "cachimb")
    )

    return bool(
        has_cachimba
        and substance.get("detected") is True
        and str(substance.get("status") or "").upper() == "AMBIGUOUS"
    )


def _ambiguous_cachimba_retrieval_rewrite(original_question: str) -> dict[str, Any]:
    return {
        "rewritten_question": (
            "significado cachimbear cachimba paradores autorizados descanso alimentos "
            "política cero tolerancia pruebas toxicológicas sustancias alcohol operador quinta rueda"
        ),
        "normalized_terms": [
            "cachimbear",
            "cachimba",
            "paradores autorizados",
            "cero tolerancia",
            "pruebas toxicológicas",
            "sustancias",
            "alcohol",
        ],
        "reason": "ambiguous_cachimba_dual_retrieval",
        "confidence": 0.95,
    }


def rewrite_question_node(state: HRState) -> dict[str, Any]:
    """
    Rewrite only the retrieval query, not the final user-facing answer.

    This improves vector search recall for informal spelling, phonetic variants,
    abbreviations, regional wording and short follow-up messages. It does not
    make business decisions and it does not classify risk.
    """
    original_question = state.get("message") or state.get("question") or ""

    if not _env_bool("QUERY_REWRITE_ENABLED", True):
        return {
            "question": original_question,
            "question_rewrite": {**DEFAULT_REWRITE, "reason": "rewrite_disabled"},
            "events": [{"type": "question_rewrite_skipped", "reason": "disabled"}],
        }

    if not original_question.strip():
        return {
            "question": original_question,
            "question_rewrite": {**DEFAULT_REWRITE, "reason": "empty_question"},
        }

    classifier = state.get("classifier") or {}
    conversation_memory = state.get("conversation_memory") or {}

    if _is_ambiguous_cachimba_retrieval_case(state, original_question):
        rewrite = _ambiguous_cachimba_retrieval_rewrite(original_question)
        rewritten_question = rewrite["rewritten_question"]
        return {
            "question": rewritten_question,
            "question_rewrite": rewrite,
            "events": [
                {
                    "type": "question_rewritten",
                    "original_question": original_question,
                    "rewritten_question": rewritten_question,
                    "normalized_terms": rewrite.get("normalized_terms", []),
                    "reason": rewrite.get("reason"),
                    "confidence": rewrite.get("confidence"),
                }
            ],
        }

    prompt = f"""
You are a query rewrite node for document retrieval in a Mexican trucking recruiting assistant.
Do not answer the candidate. Return JSON only.

Rewrite the candidate message into a clear Spanish search query for internal HR documents.
Handle informal spelling, phonetic similarity, abbreviations, regional wording,
Mexican trucking colloquialisms and short follow-up messages using conversation memory.

Important boundaries:
- Do not decide if the candidate is eligible.
- Do not classify risk.
- Do not add facts that are not implied by the message.
- Keep the rewrite short and suitable for vector search.

=== ROUTER OUTPUT ===
{json.dumps(classifier, ensure_ascii=False, default=str)}

=== CONVERSATION MEMORY ===
{json.dumps(conversation_memory, ensure_ascii=False, default=str)}

=== ORIGINAL CANDIDATE MESSAGE ===
{original_question}

Return JSON:
{{
  "rewritten_question": "short Spanish search query for retrieval",
  "normalized_terms": ["term1", "term2"],
  "reason": "short_reason",
  "confidence": 0.0
}}
""".strip()

    try:
        raw = call_llm(prompt)
        parsed = _json_from_text(raw)
        rewrite = _normalize_rewrite(parsed, original_question)
    except Exception as exc:
        rewrite = {
            **DEFAULT_REWRITE,
            "rewritten_question": original_question,
            "reason": "rewrite_exception",
            "error": f"{type(exc).__name__}: {exc}",
        }

    rewritten_question = rewrite.get("rewritten_question") or original_question

    return {
        "question": rewritten_question,
        "question_rewrite": rewrite,
        "events": [
            {
                "type": "question_rewritten",
                "original_question": original_question,
                "rewritten_question": rewritten_question,
                "normalized_terms": rewrite.get("normalized_terms", []),
                "reason": rewrite.get("reason"),
                "confidence": rewrite.get("confidence"),
            }
        ],
    }
