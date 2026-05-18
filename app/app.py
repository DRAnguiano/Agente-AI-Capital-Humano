import time
import traceback
import os
import json
import httpx

from fastapi import FastAPI, Header, Query, Request
from fastapi.responses import JSONResponse, ORJSONResponse
from pydantic import BaseModel

from .indexer import build_index, call_llm, retrieve_context_for_guardrail, _to_int
from .orchestrator import orchestrate_message
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


class OrchestrateMessageBody(BaseModel):
    channel: str = "telegram_demo"
    channel_user_id: str
    username: str | None = None
    phone: str | None = None
    message: str
    external_message_id: str | None = None


@app.post("/ask")
def ask(body: AskBody):
    """
    Endpoint RAG original.
    Lo conservamos para compatibilidad con tu workflow actual de n8n.
    """
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


@app.post("/orchestrate/message")
def orchestrate(body: OrchestrateMessageBody):
    """
    Endpoint principal del sistema.

    Este endpoint:
    - crea/actualiza conversación
    - guarda mensaje entrante
    - detecta intención/riesgo
    - extrae datos del candidato
    - consulta RAG si aplica
    - crea handoff humano si aplica
    - guarda eventos analíticos
    - devuelve respuesta lista para Telegram/Chatwoot/WhatsApp
    """
    try:
        result = orchestrate_message(
            channel=body.channel,
            channel_user_id=body.channel_user_id,
            username=body.username,
            phone=body.phone,
            message=body.message,
            external_message_id=body.external_message_id,
        )
        return result
    except Exception as exc:
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": _public_error(exc)})


def _extract_chatwoot_contact(payload: dict) -> dict:
    """
    Extrae datos del contacto desde distintas formas de payload de Chatwoot.
    OJO: esta función NO debe tener decorador @app.post.
    """
    sender = payload.get("sender") or {}
    conversation = payload.get("conversation") or {}

    meta = conversation.get("meta") or {}
    sender_from_meta = meta.get("sender") or {}

    contact = sender or sender_from_meta or {}

    contact_id = (
        contact.get("id")
        or payload.get("sender_id")
        or payload.get("contact_id")
        or payload.get("source_id")
    )

    name = (
        contact.get("name")
        or contact.get("email")
        or contact.get("phone_number")
        or sender_from_meta.get("name")
        or sender_from_meta.get("email")
        or sender_from_meta.get("phone_number")
    )

    phone = contact.get("phone_number") or sender_from_meta.get("phone_number")
    email = contact.get("email") or sender_from_meta.get("email")

    return {
        "contact_id": contact_id,
        "name": name,
        "phone": phone,
        "email": email,
    }


async def _send_chatwoot_message(
    account_id: int | str,
    conversation_id: int | str,
    content: str,
) -> dict:
    """
    Envía una respuesta pública a una conversación de Chatwoot.
    """
    base_url = os.getenv("CHATWOOT_BASE_URL", "").strip().rstrip("/")
    api_token = os.getenv("CHATWOOT_API_TOKEN", "").strip()

    if not base_url:
        raise RuntimeError("CHATWOOT_BASE_URL is not configured")

    if not api_token:
        raise RuntimeError("CHATWOOT_API_TOKEN is not configured")

    url = (
        f"{base_url}/api/v1/accounts/{account_id}"
        f"/conversations/{conversation_id}/messages"
    )

    headers = {
        "api_access_token": api_token,
        "Content-Type": "application/json",
    }

    body = {
        "content": content,
        "message_type": "outgoing",
        "private": False,
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(url, headers=headers, json=body)
        response.raise_for_status()
        return response.json()


@app.post("/chatwoot/webhook")
async def chatwoot_webhook(
    request: Request,
    token: str | None = Query(default=None),
    x_chatwoot_webhook_token: str | None = Header(default=None),
):
    """
    Webhook de Chatwoot integrado con el orquestador RH.

    Flujo:
    - Recibe eventos de Chatwoot.
    - Ignora eventos que no sean mensajes entrantes reales.
    - Convierte el payload al formato del orquestador.
    - Ejecuta orchestrate_message().
    - Envía la respuesta de vuelta a la conversación en Chatwoot.
    """
    expected_token = os.getenv("CHATWOOT_WEBHOOK_TOKEN", "").strip()
    received_token = x_chatwoot_webhook_token or token

    if expected_token and received_token != expected_token:
        return JSONResponse(
            status_code=401,
            content={
                "status": "error",
                "error": "unauthorized",
            },
        )

    try:
        payload = await request.json()
    except Exception:
        payload = {
            "raw_body": (await request.body()).decode("utf-8", errors="ignore")
        }

    if not isinstance(payload, dict):
        return {
            "status": "ignored",
            "reason": "payload_not_dict",
        }

    event = payload.get("event")
    message_type = payload.get("message_type")
    content = (payload.get("content") or "").strip()

    conversation = payload.get("conversation") or {}
    account = payload.get("account") or {}
    inbox = payload.get("inbox") or {}

    conversation_id = conversation.get("id") or payload.get("conversation_id")
    account_id = account.get("id") or payload.get("account_id")
    inbox_id = inbox.get("id") or payload.get("inbox_id")
    message_id = payload.get("id") or payload.get("message_id")

    contact = _extract_chatwoot_contact(payload)

    print(
        "[CHATWOOT_WEBHOOK]",
        json.dumps(
            {
                "event": event,
                "message_type": message_type,
                "account_id": account_id,
                "conversation_id": conversation_id,
                "inbox_id": inbox_id,
                "message_id": message_id,
                "contact_id": contact.get("contact_id"),
                "contact_name": contact.get("name"),
                "content_preview": content[:300],
            },
            ensure_ascii=False,
        ),
        flush=True,
    )

    # Ignorar todo lo que no sea un mensaje entrante real del prospecto.
    # Esto evita responder a templates, mensajes salientes y eventos internos.
    if event != "message_created":
        return {
            "status": "ignored",
            "reason": "not_message_created",
            "event": event,
        }

    if message_type != "incoming":
        return {
            "status": "ignored",
            "reason": "not_incoming",
            "message_type": message_type,
        }

    if not content:
        return {
            "status": "ignored",
            "reason": "empty_content",
        }

    if not account_id or not conversation_id:
        return JSONResponse(
            status_code=400,
            content={
                "status": "error",
                "error": "missing_account_or_conversation_id",
            },
        )

    channel_user_id = str(
        contact.get("phone")
        or contact.get("contact_id")
        or conversation_id
    )

    username = contact.get("name") or f"Chatwoot Contact {channel_user_id}"

    try:
        result = orchestrate_message(
            channel="chatwoot",
            channel_user_id=channel_user_id,
            username=username,
            phone=contact.get("phone"),
            message=content,
            external_message_id=str(message_id or ""),
        )

        reply = (result.get("reply") or result.get("text") or "").strip()

        if not reply:
            return {
                "status": "ok",
                "processed": True,
                "sent_to_chatwoot": False,
                "reason": "empty_reply",
                "orchestrator_result": result,
            }

        chatwoot_response = await _send_chatwoot_message(
            account_id=account_id,
            conversation_id=conversation_id,
            content=reply,
        )

        return {
            "status": "ok",
            "processed": True,
            "sent_to_chatwoot": True,
            "conversation_id": conversation_id,
            "account_id": account_id,
            "current_stage": result.get("current_stage"),
            "intent": result.get("intent"),
            "requires_human": result.get("requires_human"),
            "risk_level": result.get("risk_level"),
            "chatwoot_message_id": chatwoot_response.get("id"),
        }

    except httpx.HTTPStatusError as exc:
        traceback.print_exc()
        return JSONResponse(
            status_code=502,
            content={
                "status": "error",
                "error": "chatwoot_api_error",
                "details": str(exc),
                "response_text": exc.response.text[:1000],
            },
        )

    except Exception as exc:
        traceback.print_exc()
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "error": _public_error(exc),
            },
        )