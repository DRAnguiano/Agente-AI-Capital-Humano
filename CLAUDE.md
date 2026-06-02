# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Agente AI Capital Humano Transmontes** — recruiting operations system for fifth-wheel/full truck operators. The bot's name is **Mundo**. Goal: a recruiter opens Chatwoot and sees a complete, actionable candidate profile (name, phone, city, age, license, medical fitness, experience, documents, foráneo flag, travel need, missing fields, next action, candidate temperature) — without reading the full chat.

GitHub repo: `DRAnguiano/Agente-AI-Capital-Humano`
Active branch: `migration/langgraph-step1`

## Commands

### Run locally (Docker — primary workflow)

```bash
# Start all services (FastAPI, Postgres, Chatwoot, Redis, Nginx, ngrok)
docker compose up -d --build

# Neo4j runs as an orphan container from its own compose file
docker compose -f docker-compose.neo4j.yml up -d neo4j

# Rebuild API + worker + beat only (faster iteration)
docker compose build api && docker compose up -d api worker beat

# Apply Neo4j seed (geo/vehicle nodes — idempotent)
docker cp db/neo4j_seed_geo_vehicle.cypher hr_neo4j:/tmp/seed.cypher
docker exec hr_neo4j cypher-shell -u neo4j -p $NEO4J_PASSWORD --file /tmp/seed.cypher
```

### Validate syntax before rebuilding
```bash
python3 -m py_compile \
  app/app.py \
  app/tasks_chatwoot.py \
  app/graphs/hr_graph.py \
  app/orchestrators/knowledge_orchestrator.py \
  app/knowledge/current_turn.py \
  app/knowledge/neo4j_client.py \
  app/knowledge/context_builder.py \
  app/knowledge/text_normalizer.py \
  app/lead_memory/profile_extractor.py
```

### Useful API calls
```bash
curl http://localhost:8000/health

curl -X POST http://localhost:8000/orchestrate/message \
  -H "Content-Type: application/json" \
  -d '{"channel":"test_input_nodes","channel_user_id":"test1","message":"Hola, quiero aplicar"}'

# Smoke test webhook + debounce (use real CHATWOOT_WEBHOOK_TOKEN)
curl -X POST http://localhost:8000/chatwoot/webhook \
  -H "Content-Type: application/json" \
  -H "X-Chatwoot-Webhook-Token: $CHATWOOT_WEBHOOK_TOKEN" \
  -d '{"event":"message_created","message_type":"incoming","id":1,"account":{"id":1},"conversation":{"id":63},"inbox":{"id":1,"channel":"Channel::Telegram"},"content":"soy de torreon","meta":{"sender":{"id":63,"name":"Test","phone_number":"+521800000001"}}}'
```

### Logs
```bash
docker logs hr_rag_api -f
docker logs hr_worker -f

# Filter for key events
docker logs --tail=200 hr_worker 2>&1 | \
  grep -Ei "CURRENT_TURN_GUARD|CHATWOOT_NOTE_SYNC|RATE_LIMITED|SCHEDULER|ERROR"
```

### Apply DB migrations
```bash
# SQL migrations live in db/ — apply in numeric order
psql $DATABASE_URL -f db/init_hr_memory.sql
# ... up to latest

# Pending city/location migrations live in sql/ (006–012), not yet applied
```

## Architecture

### Active message path (only path — legacy removed)

When `INBOUND_DEBOUNCE_ENABLED=true` (production default):

```
Telegram / WhatsApp → Chatwoot
  → POST /chatwoot/webhook (app/app.py)
  → Redis rate limit check (30 req/min per channel_user_id, db 2)
  → app/tasks_chatwoot.py  [Celery worker, queue=inbound, debounce=6s]
  → current_turn guard (extract_current_turn_facts → may override reply)
  → app/graphs/hr_graph.py  run_hr_graph_message()
  → app/orchestrators/knowledge_orchestrator.py  handle_message()
  → app/knowledge/neo4j_client.py  (term resolution + profile facts)
  → app/knowledge/context_builder.py  (RAG if route=rag)
  → app/lead_memory/  (rh_leads_v2, rh_lead_facts_v2 in Postgres)
  → app/chatwoot_note_sync.py  → Chatwoot public reply + private note + labels
```

**Priority rule:** current turn message > lead_memory facts > Neo4j knowledge graph > RAG/ChromaDB > LLM generation.

### Profile fact extraction (single source of truth)

```
Neo4j GeoArea/VehicleType nodes  →  extract_profile_facts_from_neo4j()
  ↓ (covers city, state, vehicle_type)
app/lead_memory/profile_extractor.py  extract_profile_facts()
  ↓ (covers license, apto, experience, documents, age — regex fallback for geo)
Merged in knowledge_orchestrator._store_lead_memory_updates()
  ↓
rh_lead_facts_v2 (Postgres)
```

`current_turn.extract_current_turn_facts()` is a thin wrapper over
`profile_extractor.extract_profile_facts_as_dict()` used only by the debounce
guard in `tasks_chatwoot.py`.

### Key modules

| Module | Role |
|---|---|
| `app/app.py` | FastAPI entry point; webhook handler with Redis rate limiting |
| `app/graphs/hr_graph.py` | Thin entry point (27 lines) — calls knowledge_orchestrator directly |
| `app/orchestrators/knowledge_orchestrator.py` | Active brain: routing, reply, memory, funnel nudge |
| `app/knowledge/neo4j_client.py` | Neo4j term resolution + profile fact extraction (GeoArea/VehicleType) |
| `app/knowledge/context_builder.py` | ChromaDB RAG retrieval + LLM prompt assembly |
| `app/knowledge/current_turn.py` | Debounce guard helper — thin wrapper over profile_extractor |
| `app/knowledge/text_normalizer.py` | Normalization + alias matching (used by Neo4j client) |
| `app/lead_memory/profile_extractor.py` | Single regex extractor for license/apto/experience/docs/age |
| `app/lead_memory/repository.py` | PostgreSQL persistence: identity, facts, events, summary |
| `app/chatwoot_note_sync.py` | Builds and posts private notes + labels to Chatwoot |
| `app/indexer.py` | ChromaDB indexing; `call_llm()` for Groq/Cohere (timeout: 8s) |
| `app/db.py` | PostgreSQL context manager; conversation + candidate CRUD |
| `app/persona_config.py` | System prompt for Mundo |
| `app/settings.py` | All env-var config read at import time |
| `app/tasks_chatwoot.py` | Celery tasks: inbound debounce + Chatwoot send |
| `app/followup/` | Celery Beat follow-up scheduler (rh_seguimiento_tareas) |

### Infrastructure services

| Service | Port | Purpose |
|---|---|---|
| FastAPI (`hr_rag_api`) | 8000 | Main API |
| PostgreSQL (`hr_postgres`) | 5432 | Conversations, candidates, lead memory |
| Chatwoot Rails | 3000 | Agent inbox |
| Celery worker (`hr_worker`) | — | Debounce inbound (queue: `inbound`) |
| Celery Beat (`hr_beat`) | — | Follow-up scheduler (every 5/15 min) |
| Neo4j (`hr_neo4j`) | 7474/7687 | Knowledge graph — orphan container via `docker-compose.neo4j.yml` |
| Nginx (`public-gateway`) | 80 | Reverse-proxy + rate limiting (10 req/s per IP) |
| ngrok | 4040 | Public HTTPS tunnel |
| Redis (`chatwoot_redis`) | 6379 | Celery broker (db 1) + rate limit counters (db 2) |

### Nginx routing (critical)

`proxy_pass` must use `$request_uri` to preserve full paths (Chatwoot breaks otherwise).
Rate limiting: `limit_req_zone` at 10 req/s per IP, burst 20, in `deploy/nginx/public-gateway.conf`.

### Neo4j schema

`GeoArea` nodes (29): city and state-level with `aliases`, `profile_fact_group/key/value`, `confidence`.
`VehicleType` nodes (2): `vehicle_quinta_rueda`, `vehicle_full` with unambiguous aliases only.
`Term` nodes: HR concepts (routes, pay, documents) linked to `Intent → Route`.

Seed file: `db/neo4j_seed_geo_vehicle.cypher` (idempotent MERGE — safe to re-run).

## Environment variables

```
# LLM
LLM_PROVIDER=groq
GROQ_API_KEY / GROQ_MODEL=llama-3.3-70b-versatile / GROQ_MAX_TOKENS=350
GROQ_TIMEOUT_SECONDS=8        # prevents stuck workers under flood

# Databases
POSTGRES_HOST=postgres / POSTGRES_DB=hrdb
NEO4J_URI=bolt://neo4j:7687 / NEO4J_ENABLED=true

# Chatwoot
CHATWOOT_BASE_URL=http://chatwoot_rails:3000
CHATWOOT_API_TOKEN / CHATWOOT_WEBHOOK_TOKEN
NGROK_DOMAIN=unhazardous-carie-nonfeatured.ngrok-free.dev

# Celery debounce
INBOUND_DEBOUNCE_ENABLED=true / INBOUND_DEBOUNCE_SECONDS=6
CELERY_BROKER_URL=redis://chatwoot_redis:6379/1

# Rate limiting
WEBHOOK_RATE_LIMIT_ENABLED=true
WEBHOOK_RATE_LIMIT_MAX_PER_MINUTE=30    # Redis db 2, per channel_user_id

# RAG
KNOWLEDGE_RAG_GENERATION_ENABLED=true / RAG_MIN_SCORE=0.25
EMBEDDING_MODEL=BAAI/bge-m3
```

## Key architectural constraints

1. **`app/graphs/hr_graph.py` is 27 lines.** No mode switching, no legacy path.
2. **Single profile extractor**: `app/lead_memory/profile_extractor.py`. Neo4j handles geo/vehicle. Regex handles the rest. No extraction logic scattered elsewhere.
3. **RAG must not decide candidate facts** — facts come from Neo4j + profile_extractor. RAG answers HR policy questions only.
4. **The Chatwoot private note is display-only**, never a source of truth.
5. **`app/orchestrator.py` was deleted.** New logic goes in `app/orchestrators/knowledge_orchestrator.py` or `app/knowledge/`.
6. **Do not ask the candidate something already answered** in the current conversation.
7. **`.cache/` must not be deleted** — Docker volume mount containing BAAI/bge-m3 (2.4 GB). Deleting forces a slow re-download.

## Lead memory tables (PostgreSQL)

| Table | Purpose |
|---|---|
| `rh_leads_v2` | One row per lead (channel + channel_user_id) |
| `rh_lead_facts_v2` | Key-value facts extracted per lead |
| `rh_lead_messages_v2` | Raw message log |
| `rh_lead_events_v2` | Lifecycle events |
| `rh_seguimiento_tareas` | Follow-up tasks created by Celery Beat |
| `v_rh_work_queue` | View: labels, priority, recommended action per lead |

## Recruiting stages

`new → interested → vacancy_info_shared → profile_hint_collected → profile_in_progress → documents_pending → documents_received → apto_pending_update → safety_review → followup_pending → human_review → closed`

## What was cleaned up (2026-06-02)

Deleted in audit session:
- 23 `hr_nodes_*.py` (LangGraph experimental, never reached)
- 7 dead graph helpers (`hr_hybrid_rules`, `hr_output_guard`, `hr_rag_optimized`, `hr_routes`, `hr_state`, `hr_timing`, `hr_trace`)
- `app/orchestrator.py` (legacy) + `app/orchestrator_guard.py`
- Dead env vars: `USE_LANGGRAPH_ORCHESTRATOR`, `HR_GRAPH_MODE`, `MESSAGE_CLASSIFIER_ENABLED`, all `WEB_SEARCH_*`, all `UNKNOWN_TERM_*`, all `TAVILY_*`
- Root-level trash: `node_modules/` (486 MB), `.venv/` (1.6 GB), `docs/`, `_backup_langgraph_step1/`, `shared/`, test files

Profile extractors consolidated: base + hotfix merged into one clean `extract_profile_facts()`. `current_turn.py` is now a thin wrapper.

## Pending priorities

1. **Friendly LLM verbosity**: still too chatty. Fix: add few-shot examples to `_answer_friendly_message()` prompt in `knowledge_orchestrator.py`.

2. **"Cuando tenga la licencia llámenme"**: intent detection for `solicitud_llamada` is missing. Infrastructure (`rh_seguimiento_tareas`) exists but orchestrator doesn't detect this conversational intent.

3. **Neo4j geo hierarchy**: when candidate says a state name ("soy de nuevo leon"), bot should ask which city. `candidate.state` is already saved but the funnel nudge copy doesn't reference it.

4. **Telegram bot token expired**: regenerate via @BotFather, update `TELEGRAM_BOT_TOKEN` in `.env`, restart containers.

5. **sql/ migrations (006–012)**: city catalog and location fields — not yet applied to hrdb. Apply when geo hierarchy feature is ready.
