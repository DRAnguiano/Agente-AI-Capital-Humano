# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Agente AI Capital Humano Transmontes** — not just a chatbot, but a near-autonomous recruiting operations system for fifth-wheel/full truck operators. The bot's name is **Mundo**. The goal: a recruiter opens Chatwoot and sees a complete, actionable candidate profile (name, phone, city, age, license, medical fitness, experience, documents, foráneo flag, travel need, missing fields, next action, candidate temperature) — without having to read the full chat. The AI captures, classifies, and prepares; the human validates, decides, and closes.

GitHub repo: `DRAnguiano/Agente-AI-Capital-Humano`  
Active branch: `migration/langgraph-step1`

## Commands

### Run locally (Docker — primary workflow)

Always use `docker compose` (no hyphen — `docker-compose` is the old v1 CLI, not installed here).

```bash
# Start all services (FastAPI, Postgres, Chatwoot, Redis, Nginx, ngrok)
docker compose up -d --build

# Neo4j runs as an orphan container from its own compose file
docker compose -f docker-compose.neo4j.yml up -d neo4j

# Rebuild API + worker only (faster iteration)
docker compose build api && docker compose up -d api worker

# Start n8n (lab profile, optional)
docker compose --profile lab up -d n8n
```

### Validate syntax before rebuilding
```bash
python3 -m py_compile \
  app/app.py \
  app/tasks_chatwoot.py \
  app/chatwoot_note_sync.py \
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
# Health check
curl http://localhost:8000/health

# Reindex documents in data/
curl -X POST http://localhost:8000/reindex \
  -H "X-API-Key: ${REINDEX_API_KEY}"

# Test the main orchestrator
curl -X POST http://localhost:8000/orchestrate/message \
  -H "Content-Type: application/json" \
  -d '{"channel":"test_input_nodes","channel_user_id":"test1","message":"Hola, quiero aplicar"}'

# Smoke-test the knowledge orchestrator
bash scripts/test_knowledge_smoke_10.sh
bash scripts/demo_knowledge_5.sh
```

### Apply DB patches (run inside postgres container or via psql)
```bash
# Migrations live in db/ — apply in numeric order
psql $DATABASE_URL -f db/init_hr_memory.sql
psql $DATABASE_URL -f db/003_lead_memory_v2.sql
# ... etc
```

### Logs
```bash
docker logs hr_rag_api -f
docker logs hr_worker -f   # Celery debounce worker

# Filter for key demo/sync events in the worker
docker logs --tail=300 hr_worker 2>&1 | \
  grep -Ei "DEMO_7_QUESTIONS_OVERRIDE|DEMO_DIRECT_LEAD_PERSISTED|DEMO_DIRECT_LEAD_PERSIST_ERROR|CHATWOOT_NOTE_SYNC_OK|CHATWOOT_NOTE_SYNC_ERROR"
```

## Architecture

### Active message path (`HR_GRAPH_MODE=knowledge`)

When `INBOUND_DEBOUNCE_ENABLED=true` (production/demo default), the real entry point is the **Celery worker**, not the webhook handler directly:

```
Telegram / WhatsApp → Chatwoot
  → POST /chatwoot/webhook (app/app.py)
  → app/tasks_chatwoot.py  [Celery worker, queue=inbound, debounce=6s]
  → app/graphs/hr_graph.py  run_hr_graph_message()
  → app/orchestrators/knowledge_orchestrator.py  handle_message()
  → app/knowledge/  (Neo4j term lookup + RAG context)
  → app/lead_memory/  (rh_leads_v2, rh_lead_facts_v2 in Postgres)
  → app/chatwoot_note_sync.py  → Chatwoot private note + labels
```

When debounce is off, the webhook calls `run_hr_graph_message()` directly.

**Priority rule:** current turn message > lead_memory facts > Neo4j knowledge graph > RAG/ChromaDB > LLM generation.

### Legacy path (`HR_GRAPH_MODE=legacy`, default for now)

```
app/app.py → app/graphs/hr_graph.py → app/orchestrator.py
```

`app/orchestrator.py` is the old imperative orchestrator — kept for compatibility. New logic must NOT go here.

### Key modules

| Module | Role |
|---|---|
| `app/graphs/hr_graph.py` | Entry point; routes to knowledge or legacy mode via `HR_GRAPH_MODE` env var |
| `app/graphs/hr_state.py` | `HRState` TypedDict — shared state for all LangGraph nodes |
| `app/orchestrators/knowledge_orchestrator.py` | Active brain in knowledge mode |
| `app/knowledge/neo4j_client.py` | Read-only Neo4j client; resolves slang/terms to routing contracts |
| `app/knowledge/context_builder.py` | ChromaDB RAG retrieval + LLM prompt assembly |
| `app/knowledge/current_turn.py` | Deterministic extraction of candidate facts from the current message |
| `app/lead_memory/repository.py` | PostgreSQL persistence: identity, facts, events, summary |
| `app/lead_memory/profile_extractor.py` | LLM-assisted field extraction from conversation history |
| `app/chatwoot_note_sync.py` | Builds and posts private notes + labels to Chatwoot after each reply |
| `app/indexer.py` | ChromaDB indexing; `call_llm()` for Groq/Cohere; embedding via BAAI/bge-m3 |
| `app/db.py` | PostgreSQL context manager; conversation + candidate CRUD |
| `app/persona_config.py` | System prompt for Mundo |
| `app/settings.py` | All env-var config read at import time |
| `app/tasks_chatwoot.py` | Celery tasks for inbound message debounce |
| `app/graphs/hr_nodes_*.py` | Individual LangGraph nodes (classifier, RAG, profile, handoff, etc.) |
| `app/graphs/hr_routes.py` | LangGraph conditional edge functions |

### Infrastructure services

| Service | Port | Purpose |
|---|---|---|
| FastAPI (`hr_rag_api`) | 8000 | Main API |
| PostgreSQL (`hr_postgres`) | 5432 | Conversations, candidates, lead memory |
| Chatwoot Rails | 3000 | Agent inbox; receives webhook, displays notes |
| Chatwoot Postgres (pgvector) | — | Chatwoot's own data |
| Chatwoot Redis | — | Chatwoot Sidekiq + Celery broker (shared) |
| Celery worker (`hr_worker`) | — | Debounce inbound messages (queue: `inbound`) |
| Neo4j | 7474/7687 | Knowledge graph — **orphan container**, started via `docker-compose.neo4j.yml` separately |
| Nginx (`public-gateway`) | 80 | Reverse-proxy: ngrok → Chatwoot or API |
| ngrok | 4040 | Public HTTPS tunnel |
| n8n (lab) | 5678 | Optional automation / channel experiments |

#### Nginx routing fix (critical)
Chatwoot breaks if Nginx strips the URI path. The `proxy_pass` directives in `deploy/nginx/public-gateway.conf` **must** use `$request_uri` to preserve full paths:

```nginx
proxy_pass $chatwoot$request_uri;
proxy_pass $hr_api$request_uri;
```

Validate with:
```bash
docker exec public-gateway grep -n "proxy_pass" /etc/nginx/conf.d/default.conf
# Must show $request_uri on both lines

# Sanity check — expect HTTP 401, not a routing error
curl -i "https://${NGROK_DOMAIN}/api/v1/accounts/1/cache_keys"
```

### Recruiting stages

`START → NEW_LEAD → ASK_CITY → ASK_LICENSE → ASK_EXPERIENCE → ASK_APTO → ASK_AVAILABILITY → PROFILE_READY`

Special stages: `CLARIFY_AMBIGUOUS_SLANG`, `HUMAN_REVIEW_REQUIRED`.

## Environment variables

Critical vars (see `.env`):

```
# LLM
LLM_PROVIDER=groq|cohere
GROQ_API_KEY / GROQ_MODEL=llama-3.3-70b-versatile / GROQ_MAX_TOKENS=350
COHERE_API_KEY / COHERE_MODEL
TEMPERATURE=0.10

# Routing
HR_GRAPH_MODE=knowledge|legacy
EMBEDDING_MODEL=BAAI/bge-m3

# Databases
POSTGRES_HOST=postgres / POSTGRES_DB=hrdb / POSTGRES_USER=hr_david / POSTGRES_PASSWORD
NEO4J_ENABLED=true / NEO4J_URI=bolt://neo4j:7687 / NEO4J_USER / NEO4J_PASSWORD / NEO4J_DATABASE=neo4j

# Chatwoot
CHATWOOT_BASE_URL=http://chatwoot_rails:3000   # internal Docker URL
CHATWOOT_API_TOKEN / CHATWOOT_WEBHOOK_TOKEN
TELEGRAM_CHATWOOT_BASE_URL=https://${NGROK_DOMAIN}  # public URL for Telegram

# Public exposure
NGROK_AUTHTOKEN / NGROK_DOMAIN

# Celery debounce
INBOUND_DEBOUNCE_ENABLED=true
INBOUND_DEBOUNCE_SECONDS=6
INBOUND_DEBOUNCE_TTL_SECONDS=900
CELERY_BROKER_URL=redis://chatwoot_redis:6379/1
CELERY_RESULT_BACKEND=redis://chatwoot_redis:6379/1

# RAG
KNOWLEDGE_RAG_GENERATION_ENABLED=true
RAG_MIN_SCORE=0.25
RERANK_ENABLED=false
WEB_SEARCH_ENABLED=false
UNKNOWN_TERM_WEB_SEARCH_ENABLED=true
UNKNOWN_TERM_WEB_USE_FOR_PUBLIC_ANSWER=false  # web result informs routing only

# Bot identity
FIRST_REPLY_INTRO_ENABLED=true
ASSISTANT_PUBLIC_INTRO=Hola, soy Mundo, asistente de Capital Humano.

# Security / debug
REINDEX_API_KEY
INCLUDE_ERROR_DETAILS=false
```

## Key architectural constraints

1. **Do not add new logic to `app/orchestrator.py`** — legacy only. New features go in `app/orchestrators/knowledge_orchestrator.py` or the `app/knowledge/` layer.
2. **Deterministic extraction belongs in `app/knowledge/current_turn.py` or `app/lead_memory/profile_extractor.py`** — not scattered across multiple nodes.
3. **RAG must not decide candidate facts** — facts come from `current_turn.py` and `lead_memory`. RAG is for answering HR policy/document questions.
4. **The Chatwoot private note is display-only output**, never a source of truth.
5. **LangGraph nodes in `app/graphs/hr_nodes_*.py`** are being migrated piecemeal — only touch them if they are on the active `knowledge` path.
6. **Do not ask the candidate something already answered** in the current conversation.
7. **Do not send follow-ups outside 08:30–21:00** (Mexico City time) — not implemented yet, keep in mind for Celery Beat jobs.

## Lead memory tables (PostgreSQL)

| Table | Purpose |
|---|---|
| `rh_leads_v2` | One row per lead (channel + channel_user_id) |
| `rh_lead_facts_v2` | Key-value facts extracted per lead |
| `rh_lead_messages_v2` | Raw message log |
| `rh_lead_events_v2` | Lifecycle events |
| `v_rh_work_queue` | View used by Chatwoot webhook to pull labels, priority, recommended action |

## Background review (future feature)

When implemented: only public sources, no automatic rejection, human review required for any match, store evidence link + date, distinguish weak vs strong matches. The system must say "possible public match requires human review", never "candidate rejected".

## Documents

HR policy documents live in `DOCUMENTOS/` and are indexed into ChromaDB from `data/`. Place new PDFs or `.txt`/`.md` files in `data/` then call `POST /reindex` to rebuild the index.
