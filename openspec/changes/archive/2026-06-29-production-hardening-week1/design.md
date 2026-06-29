## Context

La auditoría de pre-producción encontró que el sistema tiene buena ingeniería de dominio
pero quedó configurado en modo "demo": el debounce asíncrono está apagado por defecto, las
API keys vacías abren los endpoints, Celery descarta mensajes ante caídas del worker, y el
`.env` contiene secretos reales con contraseñas triviales y puertos de BD expuestos al host.
Todos estos puntos fueron confirmados de forma independiente por varios sub-auditores
(arquitectura, backend, DevOps, seguridad).

Este change agrupa las correcciones de **bajo riesgo y alto impacto** que se pueden aplicar
sin reescribir la capa de dominio. Es el primer lote ("Semana 1") de un roadmap de
endurecimiento más amplio; los refactors estructurales (extraer `chatwoot_client.py`,
separar Redis, TLS propio, etc.) quedan fuera de este lote.

## Goals / Non-Goals

**Goals:**
- Eliminar las respuestas duplicadas activando el path asíncrono por defecto.
- Garantizar que ningún mensaje de candidato se pierda ante una caída del worker.
- Cerrar los endpoints internos/admin/reindex con autenticación fail-closed.
- Sacar los secretos del modo inseguro: rotación, contraseñas fuertes, `.env.example`,
  puertos de BD cerrados, registro de Chatwoot deshabilitado.
- Persistir el schedule de Celery Beat.

**Non-Goals:**
- Refactor de `handle_message` ni extracción de `chatwoot_client.py` (lote posterior).
- Separar Redis de la app vs Chatwoot, límites de recursos, healthchecks (lote posterior).
- Migrar ngrok → IP fija + TLS (lote posterior).
- Cambios en la lógica de extracción de perfil, RAG o funnel.

## Decisions

**D1 — `INBOUND_DEBOUNCE_ENABLED` por defecto `true`, no eliminar el path síncrono.**
Se cambia el default en `app/settings.py` en vez de borrar el código síncrono. Razón: el
path síncrono sigue siendo útil para diagnóstico local y la idempotencia (D3) lo cubre
mientras tanto. Alternativa descartada: eliminar el path síncrono ahora — más riesgo, menos
reversibilidad.

**D2 — Durabilidad vía `task_acks_late=True` + `task_reject_on_worker_lost=True`.**
Cambio de 2 líneas en `app/celery_app.py`. Requiere que las tareas sean idempotentes (D3),
por eso ambos van en el mismo lote. Alternativa descartada: backend de resultados persistente
con reintentos manuales — sobre-ingeniería para este alcance.

**D3 — Idempotencia con `ON CONFLICT DO NOTHING` en `save_message`.**
Se apoya en una clave natural del mensaje (identificador externo si existe, o la tupla
`conversation_key + role + message + created_at`). Razón: es la red de seguridad que hace
seguros tanto los reintentos de Chatwoot (path síncrono) como el reencolado de D2. El worker
ya tiene `_dedupe_messages` por `message_id`; esto cubre la capa de persistencia.

**D4 — Fail-closed cambiando la semántica del guard, no el call site.**
Hoy el patrón es `if KEY and x_api_key != KEY: 401`. Se invierte a denegar también cuando
`KEY` está vacía. Para no romper desarrollo local, la validación dura ("falla el arranque")
se condiciona a entorno de producción (D5); en no-producción se permite arrancar pero el
endpoint sigue denegando si la key no está. Alternativa descartada: middleware global de
auth — cambia demasiado de golpe; se prefiere el guard por endpoint que ya existe.

**D5 — Validación de arranque en el lifespan de FastAPI.**
Un check al iniciar que, en producción, rechaza secretos vacíos o el token de webhook de
desarrollo conocido. Razón: convierte un error silencioso de configuración en un fallo
ruidoso y temprano. En no-producción solo emite warning.

**D6 — Secretos: rotación + `.env.example`, gestión fuera de alcance de código.**
La rotación de credenciales en Groq/Chatwoot/ngrok/Telegram es una acción operativa externa
(documentada en tasks). El código solo deja de depender de valores triviales y aporta la
plantilla. Un gestor de secretos (Vault/Secrets Manager) se deja para un lote posterior.

**D7 — Compose de producción: quitar `ports:` de postgres/neo4j, `ENABLE_ACCOUNT_SIGNUP=false`,
volumen para el beat schedule.** Cambios declarativos en `docker-compose.yml`. El beat pasa
de `-s /tmp/celerybeat-schedule` a un path bajo un volumen nombrado.

## Risks / Trade-offs

- **[Activar debounce cambia el timing de las respuestas]** → El reply deja de ser síncrono
  al webhook; se valida en staging que el worker procesa y responde correctamente antes de
  producción. Mitigación adicional: la idempotencia (D3) evita duplicados durante la
  transición.
- **[`task_acks_late` puede reprocesar una tarea que sí terminó si el ack se pierde]** →
  Mitigado por la idempotencia de `save_message` y el dedupe por `message_id`.
- **[Fail-closed puede tumbar entornos que hoy corren con keys vacías]** → Por eso se entrega
  `.env.example` y la validación dura solo aplica en producción; en local arranca con warning.
- **[Rotar `CHATWOOT_WEBHOOK_TOKEN` requiere actualizar la config del webhook en Chatwoot]** →
  Coordinar el cambio de token en ambos lados en la misma ventana de mantenimiento.
- **[Quitar `ports:` rompe el acceso directo a la BD desde el host]** → Documentar que el
  acceso de debug se hace vía `docker compose exec`; es el comportamiento deseado en prod.
- **[`ON CONFLICT` necesita una clave/constraint adecuada]** → Verificar que exista (o crear)
  el índice/constraint que respalda el `ON CONFLICT`; si no, el cambio no tiene efecto.

## Migration Plan

1. Aplicar cambios de código (settings, celery_app, app guards + lifespan, db.save_message) y
   de compose en una rama; correr el suite determinista (`pytest tests/` sin GROQ).
2. En staging: configurar `.env` con secretos rotados, `INBOUND_DEBOUNCE_ENABLED=true`,
   API keys fuertes; validar que el webhook responde rápido, el worker procesa, no hay
   duplicados, y un kill del worker reencola el mensaje.
3. Rotar credenciales reales (Groq/Chatwoot/ngrok/Telegram) y actualizar `CHATWOOT_WEBHOOK_TOKEN`
   en Chatwoot y en el `.env` de producción en la misma ventana.
4. Desplegar compose de producción sin `ports:` de BD y con `ENABLE_ACCOUNT_SIGNUP=false`.
5. **Rollback**: revertir `INBOUND_DEBOUNCE_ENABLED` a `false` y `task_acks_late` a `false`
   restablece el comportamiento previo sin migración de datos; el `ON CONFLICT` y los guards
   fail-closed son seguros de mantener.

## Open Questions

- ¿Existe ya un identificador externo único por mensaje persistido (p. ej. `message_id` de
  Chatwoot en una columna), o el `ON CONFLICT` debe apoyarse en la tupla natural? Confirmar
  el esquema de `rh_messages` durante `/opsx:apply`.
- ¿La detección de "entorno de producción" para la validación de arranque (D5) usa una var
  existente (`ENV`/`APP_ENV`) o hay que introducirla?
