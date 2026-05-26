from __future__ import annotations

import json
import re
from typing import Any

from app.graphs.hr_state import HRState
from app.indexer import call_llm


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


def _clean_candidates(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []

    cleaned = []
    for item in value:
        text = str(item or "").strip()
        if text and text.lower() not in {x.lower() for x in cleaned}:
            cleaned.append(text)

    return cleaned[:3]


def semantic_uncertainty_analyzer_node(state: HRState) -> dict[str, Any]:
    """
    LLM-based ambiguity detector.

    Purpose:
    - Detect when contextual_rewrite assumed too much about a critical unclear term.
    - Ask clarification only for the single term that most changes the meaning.
    - Avoid regex dictionaries as decision logic.

    This node does not answer the candidate and does not classify risk.
    """
    original = str(state.get("message") or "")
    unknown_term_review = state.get("unknown_term_review") or {}
    rewrite = state.get("contextual_rewrite") or {}
    rewritten = str(rewrite.get("rewritten") or "")
    corrections = rewrite.get("corrections") or []
    confidence = rewrite.get("confidence")

    if not unknown_term_review.get("has_unclear_terms"):
        result = {
            "should_clarify": False,
            "unclear_token": None,
            "candidates": [],
            "confidence": 0.95,
            "reason": "No hay términos inciertos detectados antes del rewrite; dejar pasar a router/RAG.",
        }
        return {
            "semantic_uncertainty": result,
            "events": [
                {
                    "type": "semantic_uncertainty_checked",
                    **result,
                }
            ],
        }

    prompt = f"""
You are a semantic uncertainty analyzer inside a Mexican trucking recruiting graph.

Your job:
Decide if the previous rewrite assumed too much about a critical unclear word.

Do NOT answer the candidate.
Do NOT classify hiring eligibility.
Do NOT use a fixed dictionary.
Return JSON only.

Important:
- Many candidates write with informal spelling.
- Normal typos should not trigger clarification.
- Ask clarification only when one unclear word changes the meaning of the whole message.
- If several words are unclear, choose only the one with the lowest confidence / biggest impact.
- If the rewrite inferred a sensitive or operational meaning that was not clearly stated, prefer clarification.
- But do NOT ask clarification when the user intent is already clear and can be answered by internal documents/RAG.
- Do NOT ask clarification for normal recruiting questions about pay, sueldo, kilómetro, rutas, documentos, licencia, experiencia, horarios, pruebas toxicológicas, pruebas de orina, descanso, café, baño or paradas autorizadas.
- If the candidate asks a clear question with spelling mistakes, let it continue to RAG.
- Candidate-facing options must be polite and non-accusatory.
- Do not use terms like "droga", "adicto", "marihuana", "cocaína" in clarification options unless the candidate explicitly wrote them.
- Use safe wording like "tema de política interna", "paradas breves en ruta", "trabajar/chambear", or "otro significado".

Return:
{{
  "should_clarify": true/false,
  "unclear_token": "one original word or phrase, or null",
  "candidates": ["public-safe option 1", "public-safe option 2", "otro significado"],
  "confidence": 0.0,
  "reason": "short reason"
}}

=== ORIGINAL MESSAGE ===
{original}

=== PRE-REWRITE UNKNOWN TERM REVIEW ===
{json.dumps(unknown_term_review, ensure_ascii=False, default=str)}

=== CONTEXTUAL REWRITE ===
{rewritten}

=== REWRITE CONFIDENCE ===
{confidence}

=== CORRECTIONS MADE BY REWRITE NODE ===
{json.dumps(corrections, ensure_ascii=False, default=str)}
""".strip()

    try:
        raw = call_llm(prompt)
        parsed = _json_from_text(raw)
    except Exception as exc:
        parsed = {
            "should_clarify": False,
            "unclear_token": None,
            "candidates": [],
            "confidence": 0.0,
            "reason": f"semantic_uncertainty_exception:{type(exc).__name__}",
        }

    should_clarify = bool(parsed.get("should_clarify"))
    unclear_token = str(parsed.get("unclear_token") or "").strip() or None
    candidates = _clean_candidates(parsed.get("candidates"))

    try:
        score = float(parsed.get("confidence") or 0.0)
    except Exception:
        score = 0.0

    score = max(0.0, min(1.0, score))

    # Safety fallback: if the LLM says clarify but gives no usable token/options,
    # do not interrupt the flow.
    if should_clarify and (not unclear_token or len(candidates) < 2):
        should_clarify = False

    result = {
        "should_clarify": should_clarify,
        "unclear_token": unclear_token,
        "candidates": candidates,
        "confidence": score,
        "reason": str(parsed.get("reason") or "semantic_uncertainty_checked").strip(),
    }

    return {
        "semantic_uncertainty": result,
        "events": [
            {
                "type": "semantic_uncertainty_checked",
                **result,
            }
        ],
    }


def semantic_clarification_node(state: HRState) -> dict[str, Any]:
    uncertainty = state.get("semantic_uncertainty") or {}
    token = str(uncertainty.get("unclear_token") or "esa parte").strip()
    candidates = _clean_candidates(uncertainty.get("candidates"))

    if len(candidates) >= 3:
        options = f"{candidates[0]}, {candidates[1]}, o {candidates[2]}"
    elif len(candidates) == 2:
        options = f"{candidates[0]} o {candidates[1]}"
    else:
        options = "trabajar/chambear, hacer paradas breves en ruta, u otra cosa"

    reply = (
        f"Me perdí tantito con “{token}” 😅 "
        f"¿te refieres a {options}? "
        "Con eso te respondo bien y sin inventarte información."
    )

    return {
        "reply": reply,
        "text": reply,
        "route": "clarification",
        "selected_route": "clarification",
        "requires_clarification": True,
        "reason": "semantic_uncertainty_clarification",
        "events": [
            {
                "type": "semantic_clarification_requested",
                "unclear_token": token,
                "candidates": candidates,
            }
        ],
    }
