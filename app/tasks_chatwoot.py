import asyncio
import json
import os
import re
import time
import traceback
import uuid
from typing import Any

import redis

# Registra las tareas de seguimiento para que el worker inbound las ejecute
import app.tasks_seguimiento  # noqa: F401

from app.celery_app import celery_app


def _env_int(name: str, default: int) -> int:
    try:
        value = os.getenv(name)
        if value is None or str(value).strip() == "":
            return default
        return int(value)
    except Exception:
        return default


def _redis_url() -> str:
    return (
        os.getenv("CELERY_BROKER_URL")
        or os.getenv("REDIS_URL")
        or "redis://chatwoot_redis:6379/1"
    )


def _redis_client() -> redis.Redis:
    return redis.Redis.from_url(_redis_url(), decode_responses=True)


def _safe_text(value: Any, max_len: int = 4000) -> str:
    text = str(value or "").strip()
    return text[:max_len]


def _dedupe_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    clean = []

    for item in messages:
        message_id = str(item.get("message_id") or item.get("external_message_id") or "").strip()
        dedupe_key = message_id or f"{item.get('received_at')}:{item.get('content')}"

        if dedupe_key in seen:
            continue

        seen.add(dedupe_key)
        clean.append(item)

    return clean


def _combine_contents(messages: list[dict[str, Any]]) -> str:
    parts = []

    for item in messages:
        content = _safe_text(item.get("content"), 2000)
        if content:
            parts.append(content)

    return "\n".join(parts).strip()






def _conversation_turns_count(result: dict[str, Any]) -> int | None:
    for event in result.get("events") or []:
        if isinstance(event, dict) and event.get("type") == "conversation_memory_built":
            try:
                return int(event.get("turns_count") or 0)
            except Exception:
                return None
    return None


def _maybe_prepend_first_reply_intro(reply: str, result: dict[str, Any]) -> str:
    """
    Adds Mundo's public intro only on the first assistant reply of a conversation.

    This is intentionally done at the Chatwoot/Telegram delivery layer so curl
    tests and internal graph behavior stay clean.
    """
    clean = (reply or "").strip()
    if not clean:
        return clean

    enabled = os.getenv("FIRST_REPLY_INTRO_ENABLED", "true").strip().lower()
    if enabled not in {"1", "true", "yes", "y", "on"}:
        return clean

    intro = os.getenv(
        "ASSISTANT_PUBLIC_INTRO",
        "Hola, soy Mundo, asistente de Capital Humano.",
    ).strip()

    if not intro:
        return clean

    normalized = clean.lower()
    if "soy mundo" in normalized[:180]:
        return clean

    turns_count = _conversation_turns_count(result)

    # Only first real assistant response. If the event is missing, avoid adding
    # the intro to prevent accidental repeated greetings.
    if turns_count is None or turns_count > 0:
        return clean

    return f"{intro}\n\n{clean}"


def enqueue_chatwoot_message(item: dict[str, Any]) -> dict[str, Any]:
    """
    Guarda un mensaje entrante en Redis y agenda procesamiento diferido.

    La última tarea programada gana. Las tareas anteriores despiertan,
    revisan el token y se descartan si ya llegó un mensaje más nuevo.
    """
    r = _redis_client()

    account_id = str(item.get("account_id") or "unknown")
    conversation_id = str(item.get("conversation_id") or "unknown")

    debounce_seconds = _env_int("INBOUND_DEBOUNCE_SECONDS", 6)
    ttl_seconds = max(_env_int("INBOUND_DEBOUNCE_TTL_SECONDS", 900), debounce_seconds + 60)

    token = uuid.uuid4().hex

    pending_key = f"hr:inbound:chatwoot:{account_id}:{conversation_id}:pending"
    latest_key = f"hr:inbound:chatwoot:{account_id}:{conversation_id}:latest_token"

    payload = {
        **item,
        "token": token,
        "received_at": time.time(),
    }

    r.rpush(pending_key, json.dumps(payload, ensure_ascii=False))
    r.expire(pending_key, ttl_seconds)
    r.set(latest_key, token, ex=ttl_seconds)

    process_chatwoot_debounced_message.apply_async(
        args=[pending_key, latest_key, token],
        countdown=debounce_seconds,
        queue="inbound",
    )

    return {
        "queued": True,
        "token": token,
        "pending_key": pending_key,
        "latest_key": latest_key,
        "debounce_seconds": debounce_seconds,
    }


@celery_app.task(name="chatwoot.process_debounced_message")
def process_chatwoot_debounced_message(
    pending_key: str,
    latest_key: str,
    token: str,
) -> dict[str, Any]:
    """
    Procesa el lote de mensajes pendientes del mismo contacto/conversación.

    Si el token no es el último, significa que llegó otro mensaje después y
    esta tarea se descarta. La última tarea consolidará todo el lote.
    """
    r = _redis_client()

    latest_token = r.get(latest_key)
    if latest_token != token:
        return {
            "status": "stale",
            "reason": "newer_message_pending",
            "token": token,
            "latest_token": latest_token,
        }

    raw_messages = r.lrange(pending_key, 0, -1)

    # Evita que tareas posteriores reprocesen el mismo lote.
    r.delete(pending_key)
    r.delete(latest_key)

    messages: list[dict[str, Any]] = []
    for raw in raw_messages:
        try:
            messages.append(json.loads(raw))
        except Exception:
            continue

    messages = _dedupe_messages(messages)
    messages.sort(key=lambda item: float(item.get("received_at") or 0))

    print(
        "[CHATWOOT_DEBOUNCE_BATCH_ITEMS]",
        json.dumps(
            [
                {
                    "message_id": item.get("message_id"),
                    "received_at": item.get("received_at"),
                    "content": str(item.get("content") or "")[:300],
                }
                for item in messages
            ],
            ensure_ascii=False,
        ),
        flush=True,
    )

    if not messages:
        return {
            "status": "ignored",
            "reason": "empty_batch",
        }

    first = messages[0]
    last = messages[-1]

    combined_content = _combine_contents(messages)
    if not combined_content:
        return {
            "status": "ignored",
            "reason": "empty_combined_content",
            "batch_size": len(messages),
        }

    account_id = first.get("account_id")
    conversation_id = first.get("conversation_id")
    channel_user_id = first.get("channel_user_id")
    username = first.get("username")
    phone = first.get("phone")
    channel_label = first.get("channel_label") or "Chatwoot"

    message_ids = [
        str(item.get("message_id") or "")
        for item in messages
        if item.get("message_id") is not None
    ]

    external_message_id = (
        f"debounced:{message_ids[0]}:{message_ids[-1]}"
        if message_ids
        else f"debounced:{int(time.time())}:{token[:8]}"
    )

    print(
        "[CHATWOOT_DEBOUNCE_PROCESS]",
        json.dumps(
            {
                "account_id": account_id,
                "conversation_id": conversation_id,
                "channel_user_id": channel_user_id,
                "batch_size": len(messages),
                "external_message_id": external_message_id,
                "combined_content": combined_content[:500],
            },
            ensure_ascii=False,
        ),
        flush=True,
    )

    try:
        # Import diferido para evitar ciclos al cargar FastAPI/Celery.
        from app.app import (
            _build_chatwoot_internal_note,
            _fallback_chatwoot_labels,
            _get_rh_work_queue_metadata,
            _normalize_chatwoot_labels,
            _send_chatwoot_message,
            _send_chatwoot_private_note,
            _set_chatwoot_labels,
        )
        from app.db import make_conversation_key
        from app.graphs.hr_graph import run_hr_graph_message
        from app.knowledge.current_turn import (
            build_current_turn_ack,
            extract_current_turn_facts,
            should_prioritize_current_turn,
        )
        from app.chatwoot_note_sync import sync_chatwoot_candidate_note
        from app.lead_memory.repository import get_lead_memory

        # Pre-load context before orchestrator so we can read the last bot message
        conversation_key_for_facts = make_conversation_key("chatwoot", str(channel_user_id))
        pre_memory = get_lead_memory(conversation_key=conversation_key_for_facts)
        last_bot_message = None
        for _m in reversed(pre_memory.get("messages") or []):
            if isinstance(_m, dict) and _m.get("role") == "assistant":
                last_bot_message = str(_m.get("message") or "")[:500]
                break

        result = run_hr_graph_message(
            channel="chatwoot",
            channel_user_id=str(channel_user_id),
            username=username,
            phone=phone,
            message=combined_content,
            external_message_id=external_message_id,
        )

        current_turn_facts = extract_current_turn_facts(combined_content, last_bot_message)

        if (
            not result.get("requires_human")
            and should_prioritize_current_turn(combined_content, last_bot_message)
            and current_turn_facts
        ):
            lead_memory = get_lead_memory(conversation_key=conversation_key_for_facts)
            saved_facts = {
                f"{row['fact_group']}.{row['fact_key']}": row['fact_value']
                for row in (lead_memory.get("facts") or [])
            }
            lead_key_for_ctx = (
                (lead_memory.get("lead") or {}).get("lead_key")
                or conversation_key_for_facts
            )
            merged_facts = {**saved_facts, **current_turn_facts}
            guarded_reply = build_current_turn_ack(combined_content, merged_facts, last_bot_message)

            # Persist context-inferred facts (e.g. "si" → apto vigente) so funnel doesn't re-ask
            if lead_key_for_ctx:
                from app.lead_memory.repository import upsert_lead_fact, save_lead_message as _slm
                context_new = {
                    k: v for k, v in current_turn_facts.items()
                    if k not in saved_facts
                    and k in {"medical.apto_status", "license.status", "documents.labor_letters"}
                }
                for _k, _v in context_new.items():
                    _parts = _k.split(".", 1)
                    if len(_parts) == 2:
                        try:
                            upsert_lead_fact(
                                lead_key=lead_key_for_ctx,
                                fact_group=_parts[0],
                                fact_key=_parts[1],
                                fact_value=str(_v),
                                confidence=0.75,
                                source="guard_context",
                                source_text=combined_content[:300],
                            )
                        except Exception:
                            pass
                # Save guard reply so next turn has correct last_bot_message context.
                # Passive capture (Fase B): enrich the assistant row with the canonical
                # field the guard just asked, so route-1 shadow can read it next turn.
                # Only when the guard asked a clean single field (mixed/advisory → []).
                from app.knowledge.guard_asked_field import asked_field_keys_for_guard

                guard_keys = asked_field_keys_for_guard(merged_facts)
                guard_meta = (
                    {
                        "asked_field_keys": guard_keys,
                        "asked_field_source": "current_turn_guard",
                        "asked_field_key_space": "canonical",
                    }
                    if guard_keys
                    else None
                )
                try:
                    _slm(
                        lead_key=lead_key_for_ctx,
                        conversation_key=conversation_key_for_facts,
                        role="assistant",
                        message=guarded_reply,
                        external_metadata=guard_meta,
                    )
                except Exception:
                    pass

            result.update(
                {
                    "reply": guarded_reply,
                    "text": guarded_reply,
                    "selected_route": "profile",
                    "route": "profile",
                    "intent": "candidate_profile_signal",
                    "risk_level": "low",
                    "requires_human": False,
                    "current_turn_guard_applied": True,
                    "current_turn_facts": current_turn_facts,
                    "funnel_stage": "profile_hint_collected",
                    "next_best_action": "Validar datos del perfil y solicitar únicamente lo que falte.",
                    "memory_summary": "El candidato proporcionó datos explícitos de perfil en el último mensaje.",
                }
            )

            print(
                "[CURRENT_TURN_GUARD_APPLIED]",
                json.dumps(
                    {
                        "conversation_id": conversation_id,
                        "channel_user_id": channel_user_id,
                        "facts": current_turn_facts,
                        "reply": guarded_reply[:300],
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )

        reply = (result.get("reply") or result.get("text") or "").strip()
        reply = _maybe_prepend_first_reply_intro(reply, result)

        if not reply:
            return {
                "status": "ok",
                "processed": True,
                "sent_to_chatwoot": False,
                "reason": "empty_reply",
                "batch_size": len(messages),
                "orchestrator_result": result,
            }

        # Handoff humano: el bot deja de responder al candidato, pero la nota
        # privada + labels sí se generan para que el reclutador tome el caso.
        public_reply_suppressed = bool(result.get("requires_human"))
        if public_reply_suppressed:
            print(
                "[HUMAN_HANDOFF_NO_PUBLIC_REPLY]",
                json.dumps(
                    {
                        "conversation_id": conversation_id,
                        "channel_user_id": channel_user_id,
                        "reason": "requires_human",
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
            chatwoot_response = {}
        else:
            chatwoot_response = asyncio.run(
                _send_chatwoot_message(
                    account_id=account_id,
                    conversation_id=conversation_id,
                    content=reply,
                )
            )

        conversation_key = make_conversation_key("chatwoot", str(channel_user_id))

        work_queue = _get_rh_work_queue_metadata(conversation_key)

        labels = _normalize_chatwoot_labels(
            work_queue.get("suggested_chatwoot_labels")
        )

        if not labels:
            labels = _fallback_chatwoot_labels(result)

        labels_applied = False
        note_created = False
        labels_error = None
        note_error = None
        note_sync = None

        try:
            note_sync = asyncio.run(
                sync_chatwoot_candidate_note(
                    lead_key=conversation_key,
                    account_id=account_id,
                    conversation_id=conversation_id,
                    fallback_last_message=combined_content,
                    channel_label=channel_label,
                )
            )

            labels = note_sync.get("labels") or []
            labels_applied = bool(note_sync.get("ok"))
            note_created = bool(note_sync.get("ok"))

            print(
                "[CHATWOOT_NOTE_SYNC_OK]",
                json.dumps(
                    {
                        "lead_key": conversation_key,
                        "conversation_id": conversation_id,
                        "account_id": account_id,
                        "labels": labels,
                        "note_message_id": note_sync.get("note_message_id"),
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )

        except Exception as sync_exc:
            note_error = str(sync_exc)
            labels_error = str(sync_exc)

            print(
                "[CHATWOOT_NOTE_SYNC_ERROR]",
                json.dumps(
                    {
                        "lead_key": conversation_key,
                        "conversation_id": conversation_id,
                        "account_id": account_id,
                        "error": str(sync_exc)[:500],
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )

            # Fallback al comportamiento anterior si falla la nota/memoria v2.
            try:
                asyncio.run(
                    _set_chatwoot_labels(
                        account_id=account_id,
                        conversation_id=conversation_id,
                        labels=labels,
                    )
                )
                labels_applied = True
            except Exception as label_exc:
                labels_error = str(label_exc)
                print(
                    "[CHATWOOT_DEBOUNCE_LABELS_ERROR]",
                    json.dumps(
                        {
                            "conversation_id": conversation_id,
                            "account_id": account_id,
                            "labels": labels,
                            "error": labels_error[:500],
                        },
                        ensure_ascii=False,
                    ),
                    flush=True,
                )

            try:
                note = _build_chatwoot_internal_note(
                    result=result,
                    work_queue=work_queue,
                    labels=labels,
                    username=username,
                    content=combined_content,
                    channel_label=channel_label,
                )

                asyncio.run(
                    _send_chatwoot_private_note(
                        account_id=account_id,
                        conversation_id=conversation_id,
                        content=note,
                    )
                )
                note_created = True
            except Exception as fallback_note_exc:
                note_error = str(fallback_note_exc)
                print(
                    "[CHATWOOT_DEBOUNCE_NOTE_ERROR]",
                    json.dumps(
                        {
                            "conversation_id": conversation_id,
                            "account_id": account_id,
                            "error": note_error[:500],
                        },
                        ensure_ascii=False,
                    ),
                    flush=True,
                )

        return {
            "status": "ok",
            "processed": True,
            "sent_to_chatwoot": not public_reply_suppressed,
            "batch_size": len(messages),
            "combined_content": combined_content,
            "chatwoot_message_id": chatwoot_response.get("id"),
            "selected_route": result.get("selected_route"),
            "reason": result.get("reason"),
            "current_stage": result.get("current_stage"),
            "risk_level": result.get("risk_level"),
            "requires_human": result.get("requires_human"),
            "labels": labels,
            "labels_applied": labels_applied,
            "labels_error": labels_error,
            "note_created": note_created,
            "note_error": note_error,
            "note_sync": note_sync,
        }

    except Exception as exc:
        traceback.print_exc()
        return {
            "status": "error",
            "error": f"{type(exc).__name__}: {exc}",
            "batch_size": len(messages),
            "combined_content": combined_content[:500],
        }
