## Context

El turno Celery (`process_debounced_message`) procesa cada mensaje del candidato en varias
etapas LLM secuenciales:

1. **Extracción** (`turn_extractor.extract_turn`) → `call_groq_json` (modelo 8b-instant)
2. **Clasificación** (`intent_classifier`, `business_route_classifier`) → `call_groq_json`
3. **Generación de respuesta** (`call_groq_llm`, modelo 70B)

El problema observado: `turn_extractor.py` línea 169 tiene un `except Exception: return
TurnExtraction()` que captura silenciosamente cualquier error de `call_groq_json`,
incluyendo `GroqRateLimitError` (429 TPD). Devuelve una extracción vacía → el orquestador
continúa → se genera y envía una respuesta via `call_groq_llm` (que puede usar una clave
de distinta quota) → el candidato recibe texto pero sus datos NO quedaron registrados.

Claves de Groq: ambas (`GROQ_API_KEY` y `GROQ_API_KEY_BACKUP`) pueden pertenecer a la
misma org Groq y compartir el límite TPD de 100k tokens/día. Cuando se agota la org, ambas
devuelven 429 simultáneamente.

## Goals / Non-Goals

**Goals:**
- Cuando el extractor LLM falla irrecuperablemente (ambas claves agotadas o error de API),
  el turno se aborta antes de enviar nada a Chatwoot.
- El candidato no recibe respuesta en ese turno — silencio total desde su perspectiva.
- Nada se persiste en Postgres/lead_memory para ese turno.
- El fallo queda registrado en logs con nivel WARNING y motivo detallado.
- La tarea Celery retorna `status: 'skipped_llm_unavailable'` (no lanza excepción
  descontrolada) para evitar retries infinitos de Celery.

**Non-Goals:**
- No se implementa retry automático con espera (el candidato simplemente reenvía cuando
  quiera; la cuota se restaura diariamente).
- No se alerta al candidato ("el sistema está ocupado, intenta más tarde") — silencio total
  es preferible a una respuesta rota que implique registro falso.
- No se cambia la lógica de fallback entre claves (eso ya existe y funciona para RPM).
- No se bloquea ante errores de timeout breves (solo ante 429 TPD irrecuperable o error
  irrecuperable de ambas claves).

## Decisions

### D1 — Gate en `turn_extractor`, no en `tasks_chatwoot`

**Opción A:** Gate en `tasks_chatwoot.py` al inicio del turno (sonda liviana).
**Opción B (elegida):** Propagar la excepción desde `turn_extractor` al worker y
manejarla allí.

Rationale: El gate en `tasks_chatwoot` requeriría una llamada extra de sonda ("¿estás
vivo?") que consume tokens y puede ser también 429. La opción B es más directa: si el
extractor falla por quota, se lanza una excepción específica `LLMUnavailableError`
(subclase de `Exception`) que el worker captura ANTES de llamar a `call_groq_llm` ni
enviar nada. No se añade llamada de sonda extra.

### D2 — `LLMUnavailableError` como señal de abort

Se introduce `app/knowledge/llm_errors.py` con:
```python
class LLMUnavailableError(RuntimeError):
    """El LLM no está disponible (quota agotada o error irrecuperable en ambas claves)."""
```

`turn_extractor.extract_turn` deja de absorber `GroqRateLimitError` silenciosamente:
- Si `call_groq_json` lanza `GroqRateLimitError` (ya propagada desde `_groq_with_fallback`
  cuando ambas claves fallan) → re-raise como `LLMUnavailableError`.
- Otros errores de parsing/JSON siguen siendo absorbidos con `TurnExtraction()` vacía
  (esos no son fallo de disponibilidad, son fallo de extracción por input malformado).

### D3 — Worker captura `LLMUnavailableError` antes de Chatwoot

En `tasks_chatwoot.process_debounced_message`, inmediatamente después de llamar a
`extract_turn` (que es la primera llamada LLM del turno):

```python
try:
    turn = extract_turn(...)
except LLMUnavailableError as exc:
    logger.warning("[LLM_GATE] turno abortado — LLM no disponible: %s", exc)
    return {
        "status": "skipped_llm_unavailable",
        "processed": False,
        "sent_to_chatwoot": False,
        "reason": str(exc),
    }
```

Nada posterior al gate se ejecuta: sin persistencia, sin Chatwoot, sin labels.

### D4 — `call_groq_json` propaga `GroqRateLimitError` cuando ambas claves fallan

Actualmente `_groq_with_fallback` ya relanza `exc2` cuando el backup también falla
(línea 773 de `indexer.py`). El cambio necesario es solo en `turn_extractor`:
dejar de envolver ese error en el `except Exception: return TurnExtraction()`.

Los clasificadores (`intent_classifier`, `business_route_classifier`) son llamados
DESPUÉS del extractor, así que si el gate aborta en extracción, nunca llegan a ejecutarse.
No necesitan cambio.

### D5 — `call_groq_llm` conserva su fallback actual

`call_groq_llm` (para generación de respuesta) tiene su propio manejo y retorna un
string de error. Como el gate aborta antes de llegar a `call_groq_llm`, este path
no cambia. El requirement D-4 del spec de groq-key-fallback (si ambas claves agotadas,
la tarea falla) se cumple ahora de forma más precisa: falla limpiamente.

## Risks / Trade-offs

[Riesgo] Candidato envía mensaje y no recibe respuesta → puede pensar que el bot está
roto → Mitigación: es preferible silencio total a una respuesta que implique registro
falso; el candidato simplemente reenvía el mismo mensaje cuando la cuota se restaura
(100k TPD se resetea cada 24h en Groq free tier).

[Riesgo] Quota se agota a mitad del día en producción intensa → Mitigación: a futuro,
configurar alertas de uso TPD vía Groq dashboard; considerar Dev Tier o segunda org.

[Riesgo] Otros errores transitorios (timeout de red, error 500 Groq) también disparan
el gate → Mitigación: `LLMUnavailableError` se lanza solo ante `GroqRateLimitError`;
errores 500/timeout siguen el camino actual (absorción → extracción vacía). Se puede
ampliar en el futuro si se identifican más clases de error irrecuperable.

## Migration Plan

1. Agregar `app/knowledge/llm_errors.py` con `LLMUnavailableError`.
2. Modificar `turn_extractor.extract_turn`: re-raise `GroqRateLimitError` como
   `LLMUnavailableError` en lugar de absorberlo.
3. Modificar `tasks_chatwoot.process_debounced_message`: capturar `LLMUnavailableError`
   al inicio y retornar `skipped_llm_unavailable`.
4. Tests unitarios: mock `call_groq_json` con `GroqRateLimitError` → verificar que el
   worker retorna `skipped` y no llama a Chatwoot ni persiste.
5. `docker compose restart worker` (el api usa bind-mount; worker necesita restart).
6. Monitorear logs en producción: buscar `[LLM_GATE]` para confirmar el gate activo.

## Open Questions

- ¿Conviene notificar al agente humano en Chatwoot via nota privada cuando el turno
  se aborta? (Fuera del alcance de este change; candidato puede reenviar.)
- ¿Aplica el gate también a `call_groq_llm` failures? (No por ahora: el caso
  problemático es el extractor; si el LLM amistoso falla, el dato ya se extrajo y
  persistió, que es lo crítico.)
