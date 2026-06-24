# Project — Agente AI Capital Humano Transmontes ("Mundo")

> Contexto vivo para trabajo spec-driven. Complementa (no reemplaza) `CONTEXTO.md`
> de la raíz, que mantiene el detalle operativo (comandos, env vars, troubleshooting).

## Qué es

Sistema de operaciones de reclutamiento para operadores de camión (quinta rueda /
full). El bot se llama **Mundo** y conversa con candidatos por WhatsApp/Telegram a
través de **Chatwoot**. El valor está en lo que el reclutador ve, no en la charla: al
abrir una conversación en Chatwoot debe encontrar un **perfil completo y accionable**
(ciudad, tipo de vehículo, licencia, apto médico, experiencia, documentos, flag de
foráneo, campos faltantes y siguiente acción) sin leer el chat. (La "temperatura" del lead
queda **deprecada**: subjetiva si no está estrictamente calculada; no se muestra en la nota.)

- Repo: `DRAnguiano/Agente-AI-Capital-Humano` · branch `migration/langgraph-step1`
- Diseño del perfilamiento (fuente de verdad): `docs/esquema_perfilamiento_v1.md`

## Stack

| Capa | Tecnología |
|---|---|
| API | FastAPI (`hr_rag_api`, puerto 8000) |
| Jobs | Celery worker (queue `inbound`, debounce) + Celery Beat (seguimientos) |
| Datos | PostgreSQL 16 (`hrdb`: conversaciones, lead memory) |
| Grafo | Neo4j 5 (`GeoArea`, `VehicleType`, `Term/Intent/Route`) |
| RAG | ChromaDB + embeddings `BAAI/bge-m3` |
| LLM | Groq — `llama-3.3-70b-versatile` (generación), `llama-3.1-8b-instant` (clasificación) |
| Mensajería | Chatwoot (Rails + Sidekiq) |
| Infra | Redis (broker db1 + rate limit db2), Nginx gateway, ngrok |

## Flujo de un mensaje (ruta activa)

```
Telegram/WhatsApp → Chatwoot
  → POST /chatwoot/webhook (app/app.py): auth fail-closed + filtros + rate limit
  → enqueue Celery (queue=inbound, debounce ~6s)        [tasks_chatwoot.py]
  → current_turn guard (puede sobreescribir la respuesta)
  → graphs/hr_graph.py (entry delgado) → orchestrators/knowledge_orchestrator.py
  → knowledge/neo4j_client.py (términos + facts geo/vehículo)
  → knowledge/context_builder.py (RAG si route=rag)
  → lead_memory/ (Postgres) → chatwoot_note_sync.py (respuesta pública + nota + labels)
```

**Prioridad de fuentes de verdad:** `turno actual > lead_memory > Neo4j > RAG/Chroma > LLM`.

## Estado del proyecto (2026-06)

El sistema **en producción** usa el `knowledge_orchestrator` monolítico (routing +
generación + memoria en una función de ~240 líneas). En paralelo se está construyendo,
**aislado y en modo shadow**, un **pipeline multi-intent** (clasificador → enricher →
orchestrator) que será la nueva forma de decidir respuesta y extraer perfil. Ver el
change `multi-intent-migration`.

## Constraints arquitectónicos (no romper)

1. `app/graphs/hr_graph.py` es un entry delgado (~27 líneas). Sin mode-switching ni
   path legacy.
2. **Un solo extractor de perfil**: Neo4j cubre geo/vehículo; `lead_memory/profile_extractor.py`
   cubre licencia/apto/experiencia/documentos/edad por regex. No dispersar lógica.
3. **RAG no decide facts del candidato** — solo responde políticas/HR.
4. La **nota privada de Chatwoot es display-only**, nunca fuente de verdad.
5. **El LLM no pregunta** datos de perfil: las preguntas del funnel las emite el sistema.
   El LLM informa, comenta o anima.
6. No volver a preguntar algo ya respondido en la conversación.
7. `.cache/` no se borra (volumen con `BAAI/bge-m3`, ~2.4 GB).

## Convenciones de spec

- Capabilities en kebab-case inglés; texto de negocio en español.
- Requisitos normativos con SHALL/MUST. Cada `### Requirement:` lleva ≥1 `#### Scenario:`
  con `WHEN/THEN` (exactamente 4 hashtags en Scenario).
- Baseline = lo que el sistema hace HOY (carpeta `specs/`). Cambios en curso = `changes/`.

## Capabilities (baseline)

| Capability | Cubre |
|---|---|
| `webhook-ingestion` | Webhook Chatwoot: auth, filtros, rate limit, debounce |
| `message-orchestration` | El "cerebro" actual: routing + reply + funnel nudge |
| `profile-extraction` | Extracción de facts (Neo4j + regex) con prioridad de fuentes |
| `lead-memory` | Persistencia en Postgres (leads, facts, mensajes, eventos, stages) |
| `chatwoot-sync` | Respuesta pública + nota privada (display-only, simplificada) + labels en Chatwoot |
| `chatwoot-label-taxonomy` | Catálogo oficial de labels activas + reglas invariantes (derivadas de Postgres) |
| `followup-scheduler` | Detección de leads fríos y tareas de seguimiento (Beat) |

> Postgres/lead_memory es la **fuente de verdad operativa**; Chatwoot es canal/visualización.
> La nota privada es display-only y NO repite las labels (Chatwoot ya las muestra). Las
> labels las calcula solo `label_planner`/`chatwoot_sync` desde Postgres, nunca el LLM.
