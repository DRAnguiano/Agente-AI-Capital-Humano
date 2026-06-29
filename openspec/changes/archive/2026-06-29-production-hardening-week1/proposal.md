## Why

Una auditoría completa (arquitectura, backend, RAG, DevOps, seguridad, QA) detectó que el sistema tiene la ingeniería de dominio madura pero **no es apto para producción** por riesgos operacionales y de seguridad. El patrón recurrente y más peligroso es **funcionalidad de robustez/seguridad ya construida pero desactivada por defecto**, sumado a secretos reales en disco con contraseñas triviales. Antes de manejar datos reales de candidatos hay que cerrar estos huecos; todos son cambios de configuración o de un guard mínimo, sin reescritura de dominio.

## What Changes

- **Activar el path asíncrono del webhook por defecto** (`INBOUND_DEBOUNCE_ENABLED=true`). Hoy el webhook ejecuta todo el pipeline (LLM + 2 HTTP a Chatwoot, 4-14s) antes del 200, y los reintentos de Chatwoot por timeout producen **respuestas duplicadas**.
- **Durabilidad de mensajes en Celery**: `task_acks_late=True` + `task_reject_on_worker_lost=True`. Hoy un worker que muere a media tarea **pierde el mensaje** sin reintento ni registro.
- **Ingesta idempotente**: `save_message` con `ON CONFLICT DO NOTHING` para que un reintento del mismo mensaje no duplique filas en `rh_messages` ni reenvíe el reply (cubre el path síncrono mientras el debounce se asienta).
- **Autenticación fail-closed** en endpoints de escritura/admin. **BREAKING**: con `INTERNAL_API_KEY`/`REINDEX_API_KEY` vacías hoy los endpoints quedan **abiertos**; pasarán a **denegar** (`401`) y a fallar el arranque si no están configuradas en producción. Afecta `/ask`, `/orchestrate/message`, `/classify`, `/admin/release-human-review`, `/reindex`.
- **Rotar todos los secretos del `.env`** (GROQ x2, Chatwoot, ngrok, Telegram, `SECRET_KEY_BASE`) y reemplazar contraseñas triviales (`POSTGRES_PASSWORD=lapass`, `NEO4J_PASSWORD=neo4j_password`) por valores fuertes. Generar `CHATWOOT_WEBHOOK_TOKEN` aleatorio. Añadir `.env.example`.
- **Cerrar exposición de puertos de BD al host**: quitar `ports:` de `postgres` (5432) y `neo4j` (7474/7687) en el compose de producción.
- **Deshabilitar registro abierto de Chatwoot** (`ENABLE_ACCOUNT_SIGNUP=false`).
- **Persistir el schedule de Celery Beat** en un volumen en vez de `/tmp` efímero.

## Capabilities

### New Capabilities
- `production-security-baseline`: línea base de seguridad para despliegue — autenticación fail-closed de endpoints internos/admin/reindex, gestión y rotación de secretos (sin valores en disco versionado), puertos de BD no expuestos al host, registro de Chatwoot deshabilitado, y validación de arranque que rechaza configuración insegura en producción.

### Modified Capabilities
- `webhook-ingestion`: el procesamiento asíncrono (debounce) pasa a ser el comportamiento por defecto; la ingesta de mensajes se vuelve idempotente (un mismo mensaje no se procesa ni persiste dos veces) y durable (un worker caído reencola el mensaje en vez de perderlo).

## Impact

- **Config / `.env`**: `INBOUND_DEBOUNCE_ENABLED`, `INTERNAL_API_KEY`, `REINDEX_API_KEY`, `CHATWOOT_WEBHOOK_TOKEN`, `POSTGRES_PASSWORD`, `NEO4J_PASSWORD`, secretos GROQ/Telegram/ngrok; nuevo `.env.example`.
- **Código**:
  - `app/celery_app.py` — `task_acks_late`, `task_reject_on_worker_lost`.
  - `app/app.py` — guards de autenticación fail-closed (`/ask`, `/orchestrate/message`, `/classify`, `/admin/release-human-review`, `/reindex`); validación de arranque (lifespan).
  - `app/settings.py` — defaults fail-closed para las API keys.
  - `app/db.py` — `save_message` con `ON CONFLICT DO NOTHING`.
- **Infraestructura**: `docker-compose.yml` (quitar `ports:` de postgres/neo4j, `ENABLE_ACCOUNT_SIGNUP=false`, volumen persistente para Beat schedule), `.env.chatwoot`.
- **Dependencias / sistemas**: requiere rotación de credenciales en Groq, Chatwoot, ngrok y Telegram (acción externa). Sin nuevas dependencias de software.
- **Tests**: nuevos tests de idempotencia/dedupe y de autenticación fail-closed; verificación de que el suite determinista sigue verde.
