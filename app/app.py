import time
import traceback

from fastapi import FastAPI, Header, Query
from fastapi.responses import JSONResponse, ORJSONResponse
from pydantic import BaseModel

from .indexer import build_index, call_llm, retrieve_context_for_guardrail, _to_int
from .persona_config import SYSTEM_PROMPT
from .settings import INCLUDE_ERROR_DETAILS, REINDEX_API_KEY

app = FastAPI(default_response_class=ORJSONResponse)


def _sanitize(text: str):
    if not text:
        return text
    return text.replace("\uFFFD", "").encode("utf-8", "ignore").decode("utf-8").strip()


def _split_for_telegram(text: str, limit: int = 3500):
    parts = []
    remaining = text or ""
    while len(remaining) > limit:
        cut = remaining.rfind("\n", 0, limit)
        if cut <= 0:
            cut = limit
        parts.append(remaining[:cut])
        remaining = remaining[cut:]
    if remaining:
        parts.append(remaining)
    return parts


def _public_error(exc: Exception):
    if INCLUDE_ERROR_DETAILS:
        return f"{type(exc).__name__}: {exc}"
    return "internal_error"


@app.get("/health")
def health():
    return {"status": "ok"}


class ReindexBody(BaseModel):
    top_k: int | None = None


@app.post("/reindex")
def reindex(
    body: ReindexBody | None = None,
    k: int | None = Query(default=None),
    x_api_key: str | None = Header(default=None),
):
    if REINDEX_API_KEY and x_api_key != REINDEX_API_KEY:
        return JSONResponse(status_code=401, content={"error": "unauthorized"})

    started = time.time()
    top_k = _to_int(k, _to_int(getattr(body, "top_k", None), 3))
    try:
        stats = build_index()
        return {
            "status": "ok",
            "top_k": top_k,
            "index": stats,
            "elapsed_s": round(time.time() - started, 2),
        }
    except Exception as exc:
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={"status": "error", "error": _public_error(exc)},
        )


class AskBody(BaseModel):
    q: str
    history: str | None = ""
    top_k: int | None = None


@app.post("/ask")
def ask(body: AskBody):
    try:
        question = body.q.strip()
        history_text = body.history.strip() if body.history else "No hay historial previo."

        ctx = retrieve_context_for_guardrail(question, top_k=body.top_k)
        valid_ctx = [item for item in ctx if (item["score"] or 0) >= 0.30]

        if valid_ctx:
            context_text = "\n\n---\n\n".join(item["text"] for item in valid_ctx)
        else:
            context_text = "No se encontro informacion en los manuales para esta pregunta."

        prompt = f"""
{SYSTEM_PROMPT}

=== HISTORIAL DE LA CONVERSACION RECIENTE ===
{history_text}

=== CONTEXTO RECUPERADO DE LOS MANUALES ===
{context_text}

=== MENSAJE ACTUAL DEL CANDIDATO ===
{question}

INSTRUCCIONES DE RESPUESTA:
1. Evalua el MENSAJE ACTUAL DEL CANDIDATO: es una RESPUESTA a tu pregunta anterior, o es una PREGUNTA hacia ti?
2. Si es una RESPUESTA, por ejemplo experiencia, edad, licencia, ubicacion o disponibilidad, ignora el contexto, agradece el dato y haz la siguiente pregunta del proceso de reclutamiento.
3. Si es una PREGUNTA hacia ti, usa unicamente el contexto recuperado. Si el contexto dice que no se encontro informacion, di que no tienes ese dato a la mano y regresa al perfilamiento.
4. Responde directo, natural, sin preambulos roboticos y sin repetir la misma pregunta.
5. Nunca hagas mas de una pregunta a la vez.

RESPUESTA:
"""
        final = _sanitize(call_llm(prompt))

        return {
            "text": final,
            "chunks": _split_for_telegram(final),
            "mode": "hr_recruiting_groq",
            "sources": [
                {"source": item["source"], "score": round(item["score"], 4)}
                for item in valid_ctx
            ],
        }
    except Exception as exc:
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": _public_error(exc)})
