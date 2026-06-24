"""Tarea 9.1 (variante replay) — shadow del pipeline multi-intent sobre conversaciones
históricas de Postgres.

Como NO hay tráfico real entrante, en vez de activar el shadow en vivo se REPLAYAN
los turnos reales ya guardados: por cada turno de usuario se corre el pipeline
(classify→enrich→plan) y se emite la MISMA línea `[MULTI_INTENT_SHADOW]` que produce
`intent_shadow.run_shadow`, comparando `shadow_reply` vs el `actual_reply` histórico.
La salida se canaliza al reporte de 9.2:

    docker compose --profile test run --rm api-test python scripts/shadow_replay.py --max-leads 30 > shadow.log
    python scripts/shadow_log_report.py shadow.log --diffs 10
    # o directo:
    docker compose --profile test run --rm api-test python scripts/shadow_replay.py | python scripts/shadow_log_report.py -

MIDE, NO DECIDE. Read-only: NO escribe Postgres, NO envía a Chatwoot. Requiere Groq
(el clasificador es LLM) + acceso a Postgres → correr vía api-test.

Limitaciones: usa los facts ACTUALES del lead como `known_facts` (aproximación, no
punto-en-el-tiempo); por eso replaya el ÚLTIMO turno de usuario por lead (donde los
facts actuales ≈ estado del turno). El progreso va a stderr; stdout queda limpio (solo
líneas shadow) para canalizar al reporte.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Prefijos de laboratorio/smoke a excluir del replay (espeja scheduler._BLOCKED_PREFIXES;
# aquí SÍ incluimos telegram_demo, que es el canal de pruebas con conversaciones reales).
_LAB_PREFIXES = ("test_", "debug_", "shadow_test")


def _eprint(*args) -> None:
    print(*args, file=sys.stderr, flush=True)


def _candidate_lead_keys(channels: list[str] | None) -> list[str]:
    """lead_keys con al menos un turno de usuario, excluyendo prefijos de laboratorio."""
    from app.db import get_conn
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT DISTINCT lead_key FROM rh_lead_messages_v2 "
                "WHERE role = 'user' AND lead_key IS NOT NULL ORDER BY lead_key"
            )
            keys = [r["lead_key"] for r in cur.fetchall()]

    out: list[str] = []
    for k in keys:
        if any(k.startswith(p) for p in _LAB_PREFIXES):
            continue
        if channels:
            channel = k.split(":", 1)[0]
            if channel not in channels:
                continue
        out.append(k)
    return out


def _last_user_exchange(messages: list[dict]) -> tuple[str, str, list[dict]] | None:
    """Último (mensaje_usuario, respuesta_assistant_siguiente, mensajes_previos).

    messages viene ascendente por created_at. Devuelve None si no hay un par
    usuario→assistant.
    """
    for i in range(len(messages) - 1, -1, -1):
        if (messages[i].get("role") or "") != "user":
            continue
        # primera respuesta assistant después del turno de usuario i
        for j in range(i + 1, len(messages)):
            if (messages[j].get("role") or "") != "user":
                reply = str(messages[j].get("message") or "")
                if reply:
                    return str(messages[i].get("message") or ""), reply, messages[:i]
        # sin respuesta posterior: seguir buscando un turno previo
    return None


def replay(max_leads: int, channels: list[str] | None, throttle: float) -> int:
    """Replaya el último intercambio por lead y emite líneas shadow. Devuelve nº emitido."""
    from app.lead_memory.repository import get_lead_memory
    from app.knowledge.intent_shadow import run_shadow

    leads = _candidate_lead_keys(channels)
    _eprint(f"[replay] leads candidatos: {len(leads)} (límite {max_leads})")
    emitted = 0
    for lead_key in leads[:max_leads]:
        try:
            mem = get_lead_memory(lead_key=lead_key, limit_messages=50)
        except Exception as exc:  # noqa: BLE001
            _eprint(f"[replay] {lead_key}: error leyendo memoria: {exc}")
            continue
        exchange = _last_user_exchange(mem.get("messages") or [])
        if exchange is None:
            _eprint(f"[replay] {lead_key}: sin par usuario→assistant, omitido")
            continue
        user_msg, actual_reply, prev_msgs = exchange
        # snapshot con los mensajes PREVIOS al turno (para last_bot_question correcto)
        snapshot = {"lead": mem.get("lead"), "facts": mem.get("facts") or [], "messages": prev_msgs}
        run_shadow(user_msg, snapshot, actual_reply)  # imprime la línea [MULTI_INTENT_SHADOW]
        emitted += 1
        if throttle:
            time.sleep(throttle)
    _eprint(f"[replay] turnos emitidos: {emitted}")
    return emitted


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Replay shadow multi-intent sobre histórico (9.1). Requiere Groq+Postgres.")
    ap.add_argument("--max-leads", type=int, default=30, help="Máximo de leads a replayar (default 30).")
    ap.add_argument("--channels", default=None,
                    help="Filtro de canales separados por coma (p. ej. 'chatwoot,telegram_demo'). Default: todos menos laboratorio.")
    ap.add_argument("--throttle", type=float, default=0.0,
                    help="Segundos de espera entre turnos (para respetar RPM de Groq; p. ej. 2).")
    args = ap.parse_args(argv)

    import os
    if not os.getenv("GROQ_API_KEY"):
        _eprint("ERROR: falta GROQ_API_KEY (el clasificador es LLM).")
        return 2

    channels = [c.strip() for c in args.channels.split(",")] if args.channels else None
    replay(args.max_leads, channels, args.throttle)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
