from __future__ import annotations

import os
import time
from typing import Any

from app.indexer import _embed_texts, _get_collection, _normalize_text, _to_int

_COLLECTION_CACHE: Any | None = None
_WARMUP_RESULT: dict[str, Any] | None = None


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except Exception:
        return default


def _get_cached_collection():
    global _COLLECTION_CACHE
    if _COLLECTION_CACHE is None:
        _COLLECTION_CACHE = _get_collection()
    return _COLLECTION_CACHE


def _source_where(preferred_sources: list[str]) -> dict[str, Any] | None:
    clean = [str(item).strip() for item in preferred_sources or [] if str(item).strip()]
    if not clean:
        return None
    if len(clean) == 1:
        return {"source": clean[0]}
    return {"source": {"$in": clean}}


def _score_from_distance(distance: Any) -> float:
    try:
        return max(0.0, 1.0 - float(distance))
    except Exception:
        return 0.0


def _dedupe_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for item in items:
        item_id = str(item.get("id") or "")
        if item_id and item_id in seen:
            continue
        if item_id:
            seen.add(item_id)
        out.append(item)
    return out


def warmup_controlled_rag_runtime() -> dict[str, Any]:
    """Load Chroma collection and embedding model before the first candidate request.

    This avoids making the first real user pay the BAAI/bge-m3 cold start.
    The function performs no LLM call and spends no Groq tokens.
    """
    global _WARMUP_RESULT
    if _WARMUP_RESULT is not None:
        return _WARMUP_RESULT

    started = time.perf_counter()
    try:
        collection = _get_cached_collection()
        _embed_texts([os.getenv("KNOWLEDGE_RAG_WARMUP_TEXT", "cuanto pagan por kilometro")])
        count = collection.count()
        _WARMUP_RESULT = {
            "ok": True,
            "collection_count": count,
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
            "error": None,
        }
    except Exception as exc:
        _WARMUP_RESULT = {
            "ok": False,
            "collection_count": None,
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
            "error": f"{type(exc).__name__}: {exc}",
        }

    print(f"[knowledge_rag_warmup] {_WARMUP_RESULT}", flush=True)
    return _WARMUP_RESULT


def retrieve_preferred_context(
    question: str,
    preferred_sources: list[str] | None = None,
    *,
    top_k: int | None = None,
) -> dict[str, Any]:
    """Retrieve compact internal context constrained by Neo4j preferred sources.

    This function intentionally does not use rerankers or web search. Neo4j
    decides the source bucket; Chroma only retrieves chunks inside that bucket.
    """
    started = time.perf_counter()
    query = _normalize_text(question)
    if not query:
        return {
            "items": [],
            "context_text": "",
            "sources": [],
            "timing_ms": 0.0,
            "error": "empty_query",
            "source_filter_used": preferred_sources or [],
        }

    requested_k = _to_int(top_k, _to_int(os.getenv("RAG_TOP_K"), 3))
    min_score = _env_float("RAG_MIN_SCORE", 0.25)
    max_context_chars = _to_int(os.getenv("RAG_MAX_CONTEXT_CHARS"), 2200)
    max_chars_per_doc = _to_int(os.getenv("RAG_MAX_CHARS_PER_DOC"), 850)
    source_filter = [str(item).strip() for item in preferred_sources or [] if str(item).strip()]

    try:
        collection = _get_cached_collection()
        query_embedding = _embed_texts([query])[0]
        where = _source_where(source_filter)

        query_kwargs: dict[str, Any] = {
            "query_embeddings": [query_embedding],
            "n_results": requested_k,
            "include": ["documents", "distances", "metadatas"],
        }
        if where:
            query_kwargs["where"] = where

        results = collection.query(**query_kwargs)
    except Exception as exc:
        return {
            "items": [],
            "context_text": "",
            "sources": [],
            "timing_ms": round((time.perf_counter() - started) * 1000, 2),
            "error": f"{type(exc).__name__}: {exc}",
            "source_filter_used": source_filter,
        }

    docs = results.get("documents", [[]])[0]
    distances = results.get("distances", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]
    ids = results.get("ids", [[]])[0]

    items: list[dict[str, Any]] = []
    for doc, distance, metadata, chunk_id in zip(docs, distances, metadatas, ids):
        metadata = metadata or {}
        source = metadata.get("source")
        score = _score_from_distance(distance)
        if score < min_score:
            continue
        if source_filter and source not in source_filter:
            continue
        items.append(
            {
                "id": chunk_id,
                "text": doc or "",
                "distance": distance,
                "score": score,
                "source": source,
                "metadata": metadata,
            }
        )

    items = _dedupe_items(items)[:requested_k]

    context_parts: list[str] = []
    used_chars = 0
    for index, item in enumerate(items, start=1):
        source = item.get("source") or "fuente_interna"
        text = str(item.get("text") or "").strip()[:max_chars_per_doc]
        block = f"[Fuente {index}: {source} | score={round(float(item.get('score') or 0), 3)}]\n{text}"
        if used_chars + len(block) > max_context_chars:
            remaining = max_context_chars - used_chars
            if remaining <= 120:
                break
            block = block[:remaining]
        context_parts.append(block)
        used_chars += len(block)

    source_names: list[str] = []
    for item in items:
        source = item.get("source")
        if source and source not in source_names:
            source_names.append(source)

    return {
        "items": items,
        "context_text": "\n\n---\n\n".join(context_parts).strip(),
        "sources": source_names,
        "timing_ms": round((time.perf_counter() - started) * 1000, 2),
        "error": None,
        "source_filter_used": source_filter,
        "min_score": min_score,
        "top_k": requested_k,
    }


def build_generation_prompt(
    *,
    message: str,
    knowledge_contract: dict[str, Any],
    context_text: str,
) -> str:
    policies = knowledge_contract.get("policies") or []
    policy_text = "\n".join(
        f"- {item.get('public_guidance')}" for item in policies if isinstance(item, dict) and item.get("public_guidance")
    ) or "- No prometas contratación, sueldo exacto ni condiciones no confirmadas."

    preferred_sources = ", ".join(knowledge_contract.get("preferred_sources") or []) or "N/D"

    return f"""
Eres Mundo, asistente de Capital Humano de Transmontes.

CONTEXTO DE CONTROL DESDE NEO4J:
- Intención: {knowledge_contract.get('intent')}
- Ruta: {knowledge_contract.get('route')}
- Riesgo: {knowledge_contract.get('risk_level')}
- Términos reconocidos: {knowledge_contract.get('recognized_terms')}
- Fuentes preferidas: {preferred_sources}

POLÍTICAS A RESPETAR:
{policy_text}

CONTEXTO INTERNO RECUPERADO:
{context_text or 'No se encontró contexto interno suficiente.'}

MENSAJE DEL CANDIDATO:
{message}

INSTRUCCIONES:
1. Responde solo con base en el contexto interno recuperado y el contrato de Neo4j.
2. Si el contexto no tiene el dato suficiente, dilo con claridad y sugiere validarlo con Capital Humano.
3. No inventes pagos, prestaciones, rutas, requisitos, horarios ni condiciones.
4. No prometas contratación ni selección.
5. Responde en español natural, breve y profesional.
6. No cierres con frases genéricas tipo "si tienes otra duda".
7. No hagas una lista larga si una respuesta corta basta.

RESPUESTA:
""".strip()


def estimate_llm_cost(prompt: str, reply: str) -> dict[str, Any]:
    chars_per_token = _env_float("COST_ESTIMATE_CHARS_PER_TOKEN", 4.0)
    if chars_per_token <= 0:
        chars_per_token = 4.0

    input_tokens = int(len(prompt or "") / chars_per_token)
    output_tokens = int(len(reply or "") / chars_per_token)
    input_price = _env_float("GROQ_INPUT_PRICE_PER_1M_TOKENS", 0.59)
    output_price = _env_float("GROQ_OUTPUT_PRICE_PER_1M_TOKENS", 0.79)

    input_usd = (input_tokens / 1_000_000) * input_price
    output_usd = (output_tokens / 1_000_000) * output_price

    return {
        "estimated": True,
        "input_tokens_est": input_tokens,
        "output_tokens_est": output_tokens,
        "input_usd_est": round(input_usd, 8),
        "output_usd_est": round(output_usd, 8),
        "total_usd_est": round(input_usd + output_usd, 8),
        "chars_per_token": chars_per_token,
    }


if _env_bool("KNOWLEDGE_RAG_WARMUP_ON_STARTUP", True):
    warmup_controlled_rag_runtime()
