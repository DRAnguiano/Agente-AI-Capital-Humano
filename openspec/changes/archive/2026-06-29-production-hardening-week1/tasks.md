## 1. Idempotencia y durabilidad de la ingesta

- [x] 1.1 Confirmar el esquema de `rh_messages`: identificar si hay un identificador externo único por mensaje o definir la clave natural (`conversation_key + role + message + created_at`) para el `ON CONFLICT`
- [x] 1.2 Crear el índice/constraint UNIQUE que respalde el `ON CONFLICT` si no existe (migración SQL)
- [x] 1.3 Modificar `save_message` en `app/db.py` para usar `ON CONFLICT DO NOTHING` sobre esa clave
- [x] 1.4 Cambiar `task_acks_late=True` y añadir `task_reject_on_worker_lost=True` en `app/celery_app.py`
- [x] 1.5 Cambiar el default de `INBOUND_DEBOUNCE_ENABLED` a `true` en `app/app.py`

## 2. Autenticación fail-closed y validación de arranque

- [x] 2.1 Invertir el guard de auth en `/ask`, `/orchestrate/message`, `/classify`, `/admin/release-human-review` para denegar (`401`) también cuando `INTERNAL_API_KEY` esté vacía (`app/app.py`)
- [x] 2.2 Invertir el guard de `/reindex` para denegar cuando `REINDEX_API_KEY` esté vacía (`app/app.py`)
- [x] 2.3 Ajustar los defaults de las API keys en `app/settings.py` a semántica fail-closed (vacío ≠ "sin auth")
- [x] 2.4 Añadir validación en el lifespan de FastAPI: en producción, fallar el arranque si `INTERNAL_API_KEY`, `REINDEX_API_KEY` o `CHATWOOT_WEBHOOK_TOKEN` están vacíos o si el token de webhook es el valor de desarrollo conocido (warning en no-producción)
- [x] 2.5 Resolver cómo se detecta "producción" (var `ENV`/`APP_ENV` existente o nueva) e implementar el check

## 3. Gestión de secretos y plantilla de entorno

- [x] 3.1 Crear `.env.example` con todas las variables y placeholders (sin valores reales), marcando cuáles son críticas para producción
- [x] 3.2 Reemplazar `POSTGRES_PASSWORD=lapass` y `NEO4J_PASSWORD=neo4j_password` por valores fuertes generados en el `.env` de producción
- [x] 3.3 Generar `CHATWOOT_WEBHOOK_TOKEN` aleatorio (≥32 bytes) y actualizarlo en `.env` y `.env.chatwoot` — pendiente actualizar en Chatwoot UI
- [x] 3.4 Asignar `INTERNAL_API_KEY` y `REINDEX_API_KEY` fuertes en el `.env` de producción
- [ ] 3.5 [Operativo externo] Rotar y revocar los secretos comprometidos: GROQ (x2), token de Chatwoot, token de ngrok, token de Telegram, `SECRET_KEY_BASE`
- [ ] 3.6 Verificar con `git log --all --full-history -- .env backups/` que ningún secreto/PII esté en el historial; si lo está, reescribir historia

## 4. Endurecimiento del compose de producción

- [x] 4.1 Quitar la sección `ports:` del servicio `postgres` (5432) en `docker-compose.yml`
- [x] 4.2 Quitar la sección `ports:` del servicio `neo4j` (7474/7687) en `docker-compose.yml` y `docker-compose.neo4j.yml`
- [x] 4.3 Poner `ENABLE_ACCOUNT_SIGNUP=false` en `docker-compose.yml` y `.env.chatwoot`
- [x] 4.4 Crear volumen `beat_schedule` y cambiar `-s /tmp/celerybeat-schedule` a `/var/lib/beat/celerybeat-schedule`

## 5. Pruebas

- [ ] 5.1 Test unitario de `save_message` idempotente: insertar el mismo mensaje dos veces produce una sola fila (requiere BD — pendiente staging)
- [x] 5.2 Test de `_dedupe_messages`: mismo `message_id` → una ejecución; fallback sin `message_id`; payload con campos ausentes no crashea
- [x] 5.3 Test de autenticación fail-closed: endpoint con API key vacía o incorrecta responde `401`; con key correcta responde OK (TestClient)
- [x] 5.4 Test de la validación de arranque en producción con secreto vacío (falla/bloquea)
- [ ] 5.5 Ejecutar `pytest tests/` sin GROQ y confirmar que el suite determinista sigue verde (requiere imagen construida)

## 6. Validación en staging y despliegue

- [ ] 6.1 En staging con debounce activo: verificar respuesta rápida del webhook, procesamiento del worker y ausencia de duplicados
- [ ] 6.2 En staging: matar el worker a media tarea y verificar que el mensaje se reencola y se procesa (durabilidad)
- [ ] 6.3 Verificar que postgres/neo4j ya no son alcanzables desde el host y sí desde la red interna (`docker compose exec`)
- [ ] 6.4 Confirmar checklist de "antes de producción" de la auditoría para este lote antes de desplegar
