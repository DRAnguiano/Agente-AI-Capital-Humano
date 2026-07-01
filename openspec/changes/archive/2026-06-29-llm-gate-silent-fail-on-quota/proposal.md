## Why

Cuando el extractor LLM (`call_groq_json`) falla por cuota agotada (429 TPD) o cualquier
error de API irrecuperable, el sistema actualmente continúa el turno: envía una respuesta
friendly al candidato y a veces persiste facts parciales. Esto crea una ilusión de registro
—el candidato cree que su dato quedó guardado, pero no fue así— y deja el perfil en estado
inconsistente. El problema se observó en producción (conv 136, 2026-06-29): el candidato
dijo "tipo E y vence en 3 años" varias veces; el bot respondió pero `license.category`
nunca se persistió porque `call_groq_json` devolvió 429 en todos los intentos.

## What Changes

- El turno Celery se cancela silenciosamente (sin enviar nada a Chatwoot, sin persistir
  facts) cuando el extractor LLM no está disponible por quota o error irrecuperable.
- Solo se registra el fallo en los logs (con nivel WARNING y motivo detallado).
- La tarea Celery termina con `status: 'skipped_llm_unavailable'` en lugar de `'ok'`,
  sin reintentar automáticamente (el candidato puede reenviar cuando la cuota se restaure).
- Se introduce una función `llm_available()` como gate temprano en el worker, que prueba
  disponibilidad antes de comenzar el procesamiento costoso del turno.
- El gate se aplica al inicio del turno, antes de cualquier llamada LLM, persistencia
  o envío a Chatwoot.

## Capabilities

### New Capabilities

- `llm-turn-gate`: Gate de disponibilidad LLM al inicio del turno worker. Si el LLM
  no está disponible (quota agotada en primaria y backup, o error irrecuperable), el turno
  se aborta limpiamente: sin respuesta al candidato, sin persistencia, solo log.

### Modified Capabilities

- `message-orchestration`: El requirement de disponibilidad LLM durante el turno
  (actualmente: "si falla, usa backup") se fortalece: si ambas claves fallan, el turno
  completo se cancela en lugar de continuar con respuesta parcial.

## Impact

- `app/tasks_chatwoot.py` — lógica principal del worker Celery: agregar gate LLM temprano.
- `app/knowledge/groq_client.py` (o equivalente) — función `llm_available()` o sonda
  liviana de disponibilidad.
- `app/orchestrators/knowledge_orchestrator.py` — debe propagar la excepción/señal de
  LLM no disponible en lugar de envolverla en una respuesta de fallback.
- Logs: nuevo nivel de log `[LLM_GATE]` con motivo (quota/timeout/error).
- Tests: unitario de gate + integración del worker que verifica silencio total ante 429.
