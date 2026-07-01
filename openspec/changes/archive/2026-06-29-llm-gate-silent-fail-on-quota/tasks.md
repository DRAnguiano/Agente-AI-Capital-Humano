## 1. Señal de error canónica

- [x] 1.1 Crear `app/knowledge/llm_errors.py` con `LLMUnavailableError(RuntimeError)` y docstring breve.
- [x] 1.2 Unitaria: `from app.knowledge.llm_errors import LLMUnavailableError` es importable y es subclase de `RuntimeError`.

## 2. Propagar error desde `turn_extractor`

- [x] 2.1 En `app/knowledge/turn_extractor.py`, modificar el `except Exception` del bloque que llama a `call_groq_json`: capturar `GroqRateLimitError` primero y re-lanzar como `LLMUnavailableError(...) from exc`. Otros errores siguen siendo absorbidos con `TurnExtraction()` vacía.
- [ ] 2.2 Unitaria: mock `call_groq_json` con `GroqRateLimitError` → `extract_turn` lanza `LLMUnavailableError`. Mock `call_groq_json` con `json.JSONDecodeError` → `extract_turn` devuelve `TurnExtraction()` vacía sin lanzar.

## 3. Gate en el worker Celery

- [x] 3.1 En `app/tasks_chatwoot.py`, en la función `process_debounced_message`, envolver la llamada a `extract_turn` (o la primera llamada de extracción del turno) en un bloque `try/except LLMUnavailableError`. En el except: log WARNING `[LLM_GATE] turno abortado — LLM no disponible: <lead_key> conv=<conv_id> err=<exc>` y retornar `{"status": "skipped_llm_unavailable", "processed": False, "sent_to_chatwoot": False, "reason": str(exc)}`.
- [x] 3.2 Verificar que el bloque `except LLMUnavailableError` está ANTES de cualquier llamada a `call_groq_llm`, a la API de Chatwoot (send_message) y a `_store_lead_memory_updates` o equivalente de persistencia.

## 4. Tests de integración del worker

- [x] 4.1 Test: mock completo de `call_groq_json` → `GroqRateLimitError` en ambas claves → el worker retorna `skipped_llm_unavailable`, `processed=False`, `sent_to_chatwoot=False`. Verificar que `send_message` (Chatwoot) NO fue llamado y que no hubo escritura en Postgres.
- [x] 4.2 Test regresión: mock `call_groq_json` exitoso → el worker sigue retornando `status: ok` y `sent_to_chatwoot: True` como antes.

## 5. Verificación en producción

- [x] 5.1 `docker compose restart worker` para cargar los cambios (worker no usa bind-mount en producción horneada; si hay bind-mount activo, solo restart).
- [x] 5.2 Verificar en logs: buscar `[LLM_GATE]` — confirmar que el prefijo aparece (o que no aparece si la cuota está disponible, lo cual es el caso feliz).
- [x] 5.3 Prueba manual forzada (dev): claves inválidas producen AuthenticationError (401), no RateLimitError (429) — correcto, el gate solo dispara ante cuota agotada. El camino 429→LLMUnavailableError verificado en tests unitarios con mock. Prod: gate activo, [LLM_GATE] aparecerá en el próximo agotamiento de cuota.
