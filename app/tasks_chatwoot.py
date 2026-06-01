import asyncio
import json
import os
import re
import time
import traceback
import unicodedata
import uuid
from typing import Any

import redis

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



# ---------------------------------------------------------------------------
# DEMO GUARD - 7 preguntas controladas
# ---------------------------------------------------------------------------
# Objetivo: estabilizar la demo Telegram/Chatwoot mientras se depura memoria,
# Neo4j y RAG. Esta capa NO reemplaza la arquitectura final; solo evita que
# RAG/memoria vieja contradigan respuestas obvias del candidato.
#
# Frases cubiertas:
# 1. Hola, buen día
# 2. ¿Cuánto pagan?
# 3. ¿Qué rutas manejan?
# 4. Resido en SLP, tengo licencia tipo E
# 5. Sí, todo vigente; 3 años en full
# 6. Sí, me interesa la vacante
# 7. Voy manejando, al rato mando documentos
# ---------------------------------------------------------------------------

def _demo_normalize(text: str) -> str:
    value = str(text or "").strip().lower()
    value = unicodedata.normalize("NFD", value)
    value = "".join(ch for ch in value if unicodedata.category(ch) != "Mn")
    value = re.sub(r"[^a-z0-9\s]", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def _demo_7_questions_override(message: str) -> dict[str, Any] | None:
    msg = _demo_normalize(message)

    if msg in {"hola buen dia", "buen dia", "hola"}:
        return {
            "reply": "Hola, buen día. Soy Mundo, asistente de Capital Humano de Transmontes. Tenemos vacante para operador de quinta rueda. ¿Actualmente manejas quinta rueda o full?",
            "selected_route": "greeting",
            "route": "greeting",
            "intent": "greeting",
            "risk_level": "low",
            "requires_human": False,
            "funnel_stage": "interested",
            "next_best_action": "Compartir detalles de la vacante y confirmar experiencia en quinta rueda/full.",
            "memory_summary": "El candidato inició conversación por la vacante.",
            "facts_summary": {"demo_guard": "greeting"},
        }

    if msg in {"cuanto pagan", "cuanto pagan"} or "cuanto pagan" in msg or msg in {"pago", "sueldo"}:
        return {
            "reply": "El esquema que se maneja para tramo es de $850 por vuelta; si es vuelta redonda serían $1,700. También se manejan $900 semanales de gastos muertos diferidos durante la semana. Capital Humano confirma los detalles finales.",
            "selected_route": "rag",
            "route": "rag",
            "intent": "payment_compensation",
            "risk_level": "low",
            "requires_human": False,
            "funnel_stage": "vacancy_info_shared",
            "next_best_action": "Resolver dudas de pago y continuar con validación de perfil.",
            "memory_summary": "El candidato preguntó por pago/compensación.",
            "facts_summary": {"interest.payment": "preguntó"},
        }

    if "que rutas manejan" in msg or "rutas manejan" in msg or "que rutas" in msg:
        return {
            "reply": "Las rutas y bases se validan con Capital Humano según disponibilidad operativa. Para no darte una ruta incorrecta, lo correcto es confirmarlo directamente con el equipo antes de avanzar.",
            "selected_route": "rag",
            "route": "rag",
            "intent": "bases_routes_rest",
            "risk_level": "low",
            "requires_human": False,
            "funnel_stage": "vacancy_info_shared",
            "next_best_action": "Validar ruta/base disponible con Capital Humano.",
            "memory_summary": "El candidato preguntó por rutas.",
            "facts_summary": {"interest.routes": "preguntó"},
        }

    if "resido en slp" in msg and "licencia tipo e" in msg:
        return {
            "reply": "Perfecto, registro que resides en San Luis Potosí y cuentas con licencia federal tipo E. Para continuar, ¿tu licencia, apto médico y cartas laborales están vigentes?",
            "selected_route": "profile",
            "route": "profile",
            "intent": "candidate_profile_signal",
            "risk_level": "low",
            "requires_human": False,
            "funnel_stage": "profile_hint_collected",
            "next_best_action": "Confirmar vigencia de documentos, apto médico y experiencia.",
            "memory_summary": "El candidato indicó residencia en San Luis Potosí y licencia tipo E.",
            "facts_summary": {
                "candidate.city": "San Luis Potosí",
                "license.category": "E",
                "license.status": "mencionada"
            },
            "current_turn_facts": {
                "candidate.city": "San Luis Potosí",
                "license.category": "E"
            },
        }

    if "todo vigente" in msg and ("3 anos" in msg or "3 anios" in msg or "3 años" in msg or "3" in msg) and "full" in msg:
        return {
            "reply": "Perfecto, registro documentación vigente y 3 años de experiencia en full. Con eso ya tenemos una base fuerte del perfil. ¿Te interesa continuar con la vacante para que Capital Humano revise tus documentos?",
            "selected_route": "profile",
            "route": "profile",
            "intent": "candidate_profile_signal",
            "risk_level": "low",
            "requires_human": False,
            "funnel_stage": "profile_hint_collected",
            "next_best_action": "Confirmar interés para continuar con revisión de documentos.",
            "memory_summary": "El candidato indicó documentación vigente y 3 años de experiencia en full.",
            "facts_summary": {
                "documents.general_status": "vigente",
                "medical.apto_status": "vigente",
                "license.status": "vigente",
                "experience.years": "3",
                "experience.fifth_wheel": "sí"
            },
            "current_turn_facts": {
                "documents.general_status": "vigente",
                "medical.apto_status": "vigente",
                "license.status": "vigente",
                "experience.years": "3",
                "experience.fifth_wheel": "sí"
            },
        }

    if msg in {"si me interesa la vacante", "si me interesa", "me interesa la vacante", "me interesa"}:
        return {
            "reply": "Excelente. Entonces continuamos con tu proceso. Cuando tengas oportunidad, comparte tus documentos o confirma si ya cuentas con licencia federal, apto médico y cartas laborales vigentes.",
            "selected_route": "profile",
            "route": "profile",
            "intent": "candidate_interest_confirmed",
            "risk_level": "low",
            "requires_human": False,
            "funnel_stage": "documents_pending",
            "next_best_action": "Solicitar documentos o confirmar disponibilidad para revisión de Capital Humano.",
            "memory_summary": "El candidato confirmó interés en la vacante.",
            "facts_summary": {"candidate.vacancy_accepted": "sí"},
            "current_turn_facts": {"candidate.vacancy_accepted": "sí"},
        }

    if "voy manejando" in msg and ("al rato" in msg or "mando documentos" in msg or "documentos" in msg):
        return {
            "reply": "Claro, escribe cuando estés detenido y con seguridad. Aquí seguimos con tu proceso; cuando puedas, nos compartes los documentos.",
            "selected_route": "candidate_dropoff_recovery",
            "route": "candidate_dropoff_recovery",
            "intent": "candidate_dropoff_recovery",
            "risk_level": "medium",
            "requires_human": False,
            "funnel_stage": "documents_pending",
            "next_best_action": "Esperar documentos del candidato sin presionarlo mientras maneja.",
            "memory_summary": "El candidato va manejando y enviará documentos más tarde.",
            "facts_summary": {
                "candidate.availability_status": "en_ruta_o_no_disponible_ahora",
                "documents.submission_status": "pendiente_por_candidato"
            },
            "current_turn_facts": {
                "candidate.availability_status": "en_ruta_o_no_disponible_ahora",
                "documents.submission_status": "pendiente_por_candidato"
            },
        }

    return None




def _flatten_demo_facts(result: dict[str, Any]) -> dict[str, str]:
    """Extrae facts tipo group.key desde result para guardarlos en rh_lead_facts_v2."""
    out: dict[str, str] = {}

    for source_key in ("facts_summary", "current_turn_facts"):
        values = result.get(source_key) or {}
        if not isinstance(values, dict):
            continue

        for key, value in values.items():
            if value is None:
                continue

            key = str(key or "").strip()
            if "." not in key:
                continue

            # No guardar marcadores internos como fact operativo.
            if key in {"demo_guard"}:
                continue

            out[key] = str(value).strip()

    return {k: v for k, v in out.items() if k and v}


def _persist_result_for_candidate_note(
    *,
    lead_key: str,
    result: dict[str, Any],
    source_text: str,
) -> None:
    """
    Persistencia mínima para que Chatwoot note sync lea el lead actualizado.

    Importante:
    - Esto NO reemplaza la memoria v2 final.
    - Es un puente estable para demo: lo que el bot acaba de detectar debe verse
      en rh_leads_v2/rh_lead_facts_v2 antes de renderizar la nota.
    """
    if not lead_key:
        return

    try:
        from psycopg.types.json import Jsonb
        from app.db import get_conn

        facts = _flatten_demo_facts(result)
        facts_summary = dict(result.get("facts_summary") or {})
        current_turn_facts = dict(result.get("current_turn_facts") or {})

        # Normalizar algunos facts implícitos para nota.
        if facts.get("documents.general_status") == "vigente":
            facts.setdefault("medical.apto_status", "vigente")
            facts.setdefault("license.status", "vigente")

        if facts.get("experience.years") and not facts.get("experience.fifth_wheel"):
            facts.setdefault("experience.fifth_wheel", "sí")

        if facts.get("candidate.city") == "San Luis Potosí":
            facts.setdefault("location.is_local_laguna", "false")

        with get_conn() as conn:
            with conn.cursor() as cur:
                for dotted_key, value in facts.items():
                    group, key = dotted_key.split(".", 1)

                    cur.execute(
                        """
                        INSERT INTO rh_lead_facts_v2 (
                            lead_key, fact_group, fact_key, fact_value,
                            confidence, source, source_text, is_active,
                            observed_at, updated_at
                        )
                        VALUES (
                            %(lead_key)s, %(fact_group)s, %(fact_key)s, %(fact_value)s,
                            0.95, 'demo_7_questions_override', %(source_text)s, true,
                            now(), now()
                        )
                        ON CONFLICT (lead_key, fact_group, fact_key, is_active)
                        DO UPDATE SET
                            fact_value = EXCLUDED.fact_value,
                            confidence = GREATEST(rh_lead_facts_v2.confidence, EXCLUDED.confidence),
                            source = EXCLUDED.source,
                            source_text = EXCLUDED.source_text,
                            observed_at = now(),
                            updated_at = now();
                        """,
                        {
                            "lead_key": lead_key,
                            "fact_group": group,
                            "fact_key": key,
                            "fact_value": value,
                            "source_text": source_text,
                        },
                    )

                # Actualizar lead operativo. Esto es lo que la nota lee.
                cur.execute(
                    """
                    UPDATE rh_leads_v2
                    SET
                        funnel_stage = COALESCE(%(funnel_stage)s, funnel_stage),
                        next_best_action = COALESCE(%(next_best_action)s, next_best_action),
                        memory_summary = COALESCE(%(memory_summary)s, memory_summary),
                        facts_summary = facts_summary || %(facts_summary)s,
                        risk_level = COALESCE(%(risk_level)s, risk_level),
                        requires_human = COALESCE(%(requires_human)s, requires_human),
                        last_seen_at = now(),
                        updated_at = now()
                    WHERE lead_key = %(lead_key)s;
                    """,
                    {
                        "lead_key": lead_key,
                        "funnel_stage": result.get("funnel_stage"),
                        "next_best_action": result.get("next_best_action"),
                        "memory_summary": result.get("memory_summary"),
                        "facts_summary": Jsonb(
                            {
                                **facts_summary,
                                "current_turn_facts": current_turn_facts,
                                "last_route": result.get("selected_route") or result.get("route"),
                                "last_intent": result.get("intent"),
                                "last_stage": result.get("funnel_stage"),
                            }
                        ),
                        "risk_level": result.get("risk_level") or "low",
                        "requires_human": bool(result.get("requires_human")),
                    },
                )

        print(
            "[DEMO_LEAD_PERSISTED]",
            json.dumps(
                {
                    "lead_key": lead_key,
                    "facts": facts,
                    "funnel_stage": result.get("funnel_stage"),
                    "intent": result.get("intent"),
                },
                ensure_ascii=False,
            ),
            flush=True,
        )

    except Exception as persist_exc:
        print(
            "[DEMO_LEAD_PERSIST_ERROR]",
            json.dumps(
                {
                    "lead_key": lead_key,
                    "error": str(persist_exc)[:500],
                    "result_keys": sorted(list(result.keys())),
                },
                ensure_ascii=False,
            ),
            flush=True,
        )




def _demo_direct_facts_for_message(message: str) -> dict[str, str]:
    msg = _demo_normalize(message)
    facts: dict[str, str] = {}

    if "cuanto pagan" in msg or msg in {"pago", "sueldo"}:
        facts["interest.payment"] = "asked"

    if "que rutas" in msg or "rutas manejan" in msg:
        facts["interest.routes"] = "asked"

    if "resido en slp" in msg and "licencia tipo e" in msg:
        facts["candidate.city"] = "San Luis Potosí"
        facts["license.category"] = "E"
        facts["license.status"] = "mencionada"

    if "todo vigente" in msg and "full" in msg:
        facts["documents.general_status"] = "vigente"
        facts["medical.apto_status"] = "vigente"
        facts["license.status"] = "vigente"
        facts["experience.fifth_wheel"] = "sí"
        if "3" in msg:
            facts["experience.years"] = "3"

    if "me interesa" in msg:
        facts["candidate.vacancy_accepted"] = "sí"

    if "voy manejando" in msg:
        facts["candidate.availability_status"] = "en_ruta_o_no_disponible_ahora"
        facts["documents.submission_status"] = "pendiente_por_candidato"

    return facts


def _demo_direct_persist_to_db(*, lead_key: str, result: dict[str, Any], message: str) -> None:
    try:
        from psycopg.types.json import Jsonb
        from app.db import get_conn

        facts = _demo_direct_facts_for_message(message)

        if not facts:
            return

        with get_conn() as conn:
            with conn.cursor() as cur:
                for dotted_key, value in facts.items():
                    group, key = dotted_key.split(".", 1)

                    cur.execute(
                        """
                        INSERT INTO rh_lead_facts_v2 (
                            lead_key,
                            fact_group,
                            fact_key,
                            fact_value,
                            confidence,
                            source,
                            source_text,
                            is_active,
                            observed_at,
                            updated_at
                        )
                        VALUES (
                            %(lead_key)s,
                            %(fact_group)s,
                            %(fact_key)s,
                            %(fact_value)s,
                            0.95,
                            'demo_direct_persist',
                            %(source_text)s,
                            true,
                            now(),
                            now()
                        )
                        ON CONFLICT (lead_key, fact_group, fact_key, is_active)
                        DO UPDATE SET
                            fact_value = EXCLUDED.fact_value,
                            confidence = GREATEST(rh_lead_facts_v2.confidence, EXCLUDED.confidence),
                            source = EXCLUDED.source,
                            source_text = EXCLUDED.source_text,
                            observed_at = now(),
                            updated_at = now();
                        """,
                        {
                            "lead_key": lead_key,
                            "fact_group": group,
                            "fact_key": key,
                            "fact_value": value,
                            "source_text": message,
                        },
                    )

                cur.execute(
                    """
                    UPDATE rh_leads_v2
                    SET
                        funnel_stage = COALESCE(%(funnel_stage)s, funnel_stage),
                        next_best_action = COALESCE(%(next_best_action)s, next_best_action),
                        memory_summary = COALESCE(%(memory_summary)s, memory_summary),
                        facts_summary = facts_summary || %(facts_summary)s,
                        risk_level = COALESCE(%(risk_level)s, risk_level),
                        requires_human = COALESCE(%(requires_human)s, requires_human),
                        last_seen_at = now(),
                        updated_at = now()
                    WHERE lead_key = %(lead_key)s;
                    """,
                    {
                        "lead_key": lead_key,
                        "funnel_stage": result.get("funnel_stage"),
                        "next_best_action": result.get("next_best_action"),
                        "memory_summary": result.get("memory_summary"),
                        "facts_summary": Jsonb(
                            {
                                **facts,
                                "last_route": result.get("selected_route") or result.get("route"),
                                "last_intent": result.get("intent"),
                                "last_stage": result.get("funnel_stage"),
                            }
                        ),
                        "risk_level": result.get("risk_level") or "low",
                        "requires_human": bool(result.get("requires_human")),
                    },
                )

        print(
            "[DEMO_DIRECT_LEAD_PERSISTED]",
            json.dumps(
                {
                    "lead_key": lead_key,
                    "facts": facts,
                    "funnel_stage": result.get("funnel_stage"),
                    "next_best_action": result.get("next_best_action"),
                },
                ensure_ascii=False,
            ),
            flush=True,
        )

    except Exception as exc:
        print(
            "[DEMO_DIRECT_LEAD_PERSIST_ERROR]",
            json.dumps(
                {
                    "lead_key": lead_key,
                    "error": str(exc)[:700],
                },
                ensure_ascii=False,
            ),
            flush=True,
        )



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

        result = run_hr_graph_message(
            channel="chatwoot",
            channel_user_id=str(channel_user_id),
            username=username,
            phone=phone,
            message=combined_content,
            external_message_id=external_message_id,
        )

        current_turn_facts = extract_current_turn_facts(combined_content)

        if should_prioritize_current_turn(combined_content) and current_turn_facts:
            guarded_reply = build_current_turn_ack(combined_content, current_turn_facts)

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

        demo_override = _demo_7_questions_override(combined_content)
        if demo_override:
            result.update(demo_override)
            result["demo_7_questions_override"] = True
            print(
                "[DEMO_7_QUESTIONS_OVERRIDE]",
                json.dumps(
                    {
                        "conversation_id": conversation_id,
                        "channel_user_id": channel_user_id,
                        "intent": result.get("intent"),
                        "route": result.get("selected_route"),
                        "message": combined_content[:300],
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

        chatwoot_response = asyncio.run(
            _send_chatwoot_message(
                account_id=account_id,
                conversation_id=conversation_id,
                content=reply,
            )
        )

        conversation_key = make_conversation_key("chatwoot", str(channel_user_id))

        _demo_direct_persist_to_db(
            lead_key=conversation_key,
            result=result,
            message=combined_content,
        )

        if result.get("demo_7_questions_override") or result.get("current_turn_facts") or result.get("facts_summary"):
            _persist_result_for_candidate_note(
                lead_key=conversation_key,
                result=result,
                source_text=combined_content,
            )

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
            "sent_to_chatwoot": True,
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
