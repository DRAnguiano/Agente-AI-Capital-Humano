from __future__ import annotations

import json
import os
import re
from typing import Any

import httpx

from app.graphs.hr_state import HRState
from app.indexer import call_llm


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


def _extract_unclear_terms_with_llm(message: str) -> dict[str, Any]:
    prompt = f"""
You are an uncertainty detector for a Mexican trucking recruiting assistant.

Task:
Identify unclear, misspelled, phonetic, regional, or unknown terms that could change the meaning of the candidate message.

Do NOT rewrite the full message.
Do NOT infer sensitive meanings.
Do NOT classify eligibility.
Do NOT decide risk.

Return JSON only:
{{
  "has_unclear_terms": true/false,
  "terms": [
    {{
      "term": "original unclear word or short phrase",
      "why_important": "why this word changes meaning",
      "candidate_search_queries": [
        "term traileros transporte significado México",
        "term corrector ortográfico español",
        "term reddit traileros"
      ]
    }}
  ],
  "full_sentence_query": "full candidate sentence + traileros transporte significado México"
}}

Rules:
- Choose only terms that materially change the meaning.
- Ignore normal typos that are obvious: k/que, pa/para, io/yo, m/me.
- If several terms are unclear, keep at most 3.
- Do not output drug names unless the candidate explicitly wrote them.
- If the message is understandable without web review, return has_unclear_terms=false.

Candidate message:
{message}
""".strip()

    try:
        raw = call_llm(prompt)
        parsed = _json_from_text(raw)
    except Exception as exc:
        return {
            "has_unclear_terms": False,
            "terms": [],
            "full_sentence_query": "",
            "error": f"{type(exc).__name__}: {exc}",
        }

    terms = parsed.get("terms") if isinstance(parsed.get("terms"), list) else []
    clean_terms = []

    for item in terms[:3]:
        if not isinstance(item, dict):
            continue

        term = str(item.get("term") or "").strip()
        if not term:
            continue

        queries = item.get("candidate_search_queries")
        if not isinstance(queries, list):
            queries = []

        clean_queries = [str(q).strip() for q in queries if str(q).strip()][:4]
        if not clean_queries:
            clean_queries = [
                f"{term} traileros transporte significado México",
                f"{term} corrector ortográfico español",
                f"{term} reddit traileros",
            ]

        clean_terms.append(
            {
                "term": term,
                "why_important": str(item.get("why_important") or "").strip(),
                "candidate_search_queries": clean_queries,
            }
        )

    return {
        "has_unclear_terms": bool(parsed.get("has_unclear_terms") and clean_terms),
        "terms": clean_terms,
        "full_sentence_query": str(parsed.get("full_sentence_query") or "").strip(),
    }


def _tavily_search(query: str, api_key: str, max_results: int, timeout_s: int) -> dict[str, Any]:
    payload = {
        "api_key": api_key,
        "query": query,
        "search_depth": os.getenv("TAVILY_SEARCH_DEPTH", "basic"),
        "max_results": max_results,
        "include_answer": True,
        "include_raw_content": False,
    }

    with httpx.Client(timeout=float(timeout_s)) as client:
        response = client.post(TAVILY_SEARCH_URL, json=payload)
        response.raise_for_status()
        data = response.json()

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
        "query": query,
        "answer": data.get("answer"),
        "results": results,
    }


def _summarize_unknown_terms(message: str, term_reviews: list[dict[str, Any]]) -> dict[str, Any]:
    prompt = f"""
You are a web evidence reviewer for a Mexican trucking recruiting assistant.

You receive Tavily search snippets about unclear candidate terms.

Task:
Create a cautious interpretation summary for the rewrite node.

Rules:
- Do NOT decide hiring eligibility.
- Do NOT answer the candidate.
- Do NOT claim a term means drugs/alcohol unless the web evidence clearly supports it.
- If evidence is weak, say evidence is weak and preserve ambiguity.
- Prefer safe public categories:
  - trabajar/chambear
  - paradas breves en ruta
  - jerga de transporte
  - unknown/needs clarification
- Do not invent meanings.

Return JSON only:
{{
  "summary": "short Spanish summary",
  "terms": [
    {{
      "term": "original term",
      "candidate_meanings": ["meaning1", "meaning2"],
      "confidence": 0.0,
      "needs_clarification": true/false,
      "do_not_infer_sensitive_fact": true/false
    }}
  ],
  "safe_rewrite_guidance": "instruction for contextual rewrite"
}}

Original candidate message:
{message}

Tavily term reviews:
{json.dumps(term_reviews, ensure_ascii=False, default=str)}
""".strip()

    try:
        raw = call_llm(prompt)
        parsed = _json_from_text(raw)
    except Exception as exc:
        return {
            "summary": "No se pudo sintetizar evidencia web.",
            "terms": [],
            "safe_rewrite_guidance": "Preserva términos ambiguos y pide aclaración si son críticos.",
            "error": f"{type(exc).__name__}: {exc}",
        }

    terms = parsed.get("terms") if isinstance(parsed.get("terms"), list) else []
    clean_terms = []

    for item in terms:
        if not isinstance(item, dict):
            continue

        meanings = item.get("candidate_meanings")
        if not isinstance(meanings, list):
            meanings = []

        try:
            confidence = float(item.get("confidence") or 0.0)
        except Exception:
            confidence = 0.0

        clean_terms.append(
            {
                "term": str(item.get("term") or "").strip(),
                "candidate_meanings": [str(x).strip() for x in meanings if str(x).strip()][:4],
                "confidence": max(0.0, min(1.0, confidence)),
                "needs_clarification": bool(item.get("needs_clarification")),
                "do_not_infer_sensitive_fact": bool(item.get("do_not_infer_sensitive_fact", True)),
            }
        )

    return {
        "summary": str(parsed.get("summary") or "").strip(),
        "terms": clean_terms,
        "safe_rewrite_guidance": str(parsed.get("safe_rewrite_guidance") or "").strip()
        or "Preserva términos ambiguos y pide aclaración si son críticos.",
    }


def pre_rewrite_unknown_term_review_node(state: HRState) -> dict[str, Any]:
    """
    Runs before contextual_rewrite.

    Purpose:
    - Identify unclear critical terms.
    - Search Tavily per term and with the full sentence.
    - Provide cautious evidence to contextual_rewrite.
    - Prevent the rewrite LLM from inventing sensitive meanings.
    """
    message = str(state.get("message") or "").strip()

    if not message:
        return {
            "unknown_term_review": {
                "enabled": False,
                "reason": "empty_message",
                "has_unclear_terms": False,
                "terms": [],
            }
        }

    if not _env_bool("PRE_REWRITE_WEB_TERM_REVIEW_ENABLED", True):
        return {
            "unknown_term_review": {
                "enabled": False,
                "reason": "disabled",
                "has_unclear_terms": False,
                "terms": [],
            },
            "events": [{"type": "unknown_term_review_skipped", "reason": "disabled"}],
        }

    extraction = _extract_unclear_terms_with_llm(message)

    if not extraction.get("has_unclear_terms"):
        return {
            "unknown_term_review": {
                "enabled": True,
                "has_unclear_terms": False,
                "terms": [],
                "reason": extraction.get("error") or "no_unclear_terms",
            },
            "events": [
                {
                    "type": "unknown_term_review_checked",
                    "has_unclear_terms": False,
                    "reason": extraction.get("error") or "no_unclear_terms",
                }
            ],
        }

    api_key = os.getenv("TAVILY_API_KEY", "").strip()
    if not api_key or not _env_bool("WEB_SEARCH_ENABLED", False):
        return {
            "unknown_term_review": {
                "enabled": True,
                "has_unclear_terms": True,
                "terms": extraction.get("terms") or [],
                "web_available": False,
                "summary": "Hay términos ambiguos, pero Tavily no está disponible.",
                "safe_rewrite_guidance": (
                    "No conviertas términos ambiguos en sustancias, delitos o hechos sensibles. "
                    "Preserva el término original o pide aclaración."
                ),
            },
            "events": [
                {
                    "type": "unknown_term_review_web_skipped",
                    "reason": "missing_tavily_or_web_disabled",
                    "terms": [t.get("term") for t in extraction.get("terms") or []],
                }
            ],
        }

    max_results = _to_int(os.getenv("PRE_REWRITE_WEB_MAX_RESULTS"), 3)
    timeout_s = _to_int(os.getenv("WEB_SEARCH_TIMEOUT_SECONDS"), 8)

    term_reviews = []

    for term_info in extraction.get("terms") or []:
        term = term_info.get("term")
        queries = list(term_info.get("candidate_search_queries") or [])

        full_sentence_query = extraction.get("full_sentence_query")
        if full_sentence_query:
            queries.append(full_sentence_query)

        searches = []
        for query in queries[:5]:
            try:
                searches.append(_tavily_search(query, api_key, max_results, timeout_s))
            except Exception as exc:
                searches.append(
                    {
                        "query": query,
                        "error": f"{type(exc).__name__}: {exc}",
                        "answer": None,
                        "results": [],
                    }
                )

        term_reviews.append(
            {
                "term": term,
                "why_important": term_info.get("why_important"),
                "queries": queries[:5],
                "searches": searches,
            }
        )

    synthesis = _summarize_unknown_terms(message, term_reviews)

    return {
        "unknown_term_review": {
            "enabled": True,
            "has_unclear_terms": True,
            "web_available": True,
            "extraction": extraction,
            "term_reviews": term_reviews,
            **synthesis,
        },
        "events": [
            {
                "type": "unknown_term_review_completed",
                "terms": [t.get("term") for t in extraction.get("terms") or []],
                "summary": synthesis.get("summary"),
                "safe_rewrite_guidance": synthesis.get("safe_rewrite_guidance"),
            }
        ],
    }
