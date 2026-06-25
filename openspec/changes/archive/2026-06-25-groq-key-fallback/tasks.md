## 1. Implementación del helper y fallback en `app/indexer.py`

- [x] 1.1 Importar `groq.RateLimitError` (o el equivalente en la versión instalada) al inicio de `app/indexer.py`
- [x] 1.2 Extraer helper privado `_groq_call(api_key, messages, model, *, json_mode, temperature, max_tokens)` que construye el cliente y ejecuta `chat.completions.create`; devuelve el string de contenido
- [x] 1.3 Reescribir `call_groq_llm` para usar `_groq_call` con su system prompt; capturar `RateLimitError` y reintentar con `GROQ_API_KEY_BACKUP` antes de re-lanzar
- [x] 1.4 Reescribir `call_groq_json` para usar `_groq_call` (json_mode=True); mismo patrón de fallback
- [x] 1.5 Reescribir `call_groq_with_system` para usar `_groq_call`; mismo patrón de fallback
- [x] 1.6 Añadir log `[groq-fallback] cuota primaria agotada, usando BACKUP — <fn>` antes de cada reintento

## 2. Variables de entorno

- [x] 2.1 Descomentar `GROQ_API_KEY_BACKUP` en `.env` (ya tiene valor; solo quitar `# `)
- [x] 2.2 Verificar que `docker-compose.yml` pasa `GROQ_API_KEY_BACKUP` al worker (añadir si falta)

## 3. Tests y verificación

- [x] 3.1 Verificar que `_groq_call` no rompe imports (`python3 -c "import app.indexer"`)
- [x] 3.2 Rebuild y restart del worker: `docker compose build worker && docker compose up -d worker`
- [x] 3.3 Confirmar en logs que el worker arranca sin errores (`celery@... ready`)

## 4. Sync OpenSpec

- [x] 4.1 Marcar spec `groq-key-fallback` en `openspec/specs/groq-key-fallback/spec.md` (archive copia desde changes/)
- [x] 4.2 Actualizar `openspec/specs/message-orchestration/spec.md` con el Requirement modificado de disponibilidad de LLM
