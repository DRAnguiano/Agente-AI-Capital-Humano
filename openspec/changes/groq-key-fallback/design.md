## Context

El sistema hace 2-3 llamadas a Groq por turno (unified extractor 70b + generación 70b +
clasificación opcional 8b). Con un solo API key, al agotarse la cuota diaria (~500k tokens/día
en el plan free) todas las llamadas fallan y el worker devuelve errores hasta que se rota la
clave manualmente. En producción se observó este fallo el 2026-06-25: el penúltimo turno de
una conversación fallió silenciosamente hasta que se hizo el swap manual + restart.

El `.env` ya tenía `GROQ_API_KEY_BACKUP` como comentario. El patrón "clave de respaldo" es
la solución de menor costo y menor riesgo operativo, dado que el proyecto ya gestiona dos
cuentas Groq.

## Goals / Non-Goals

**Goals:**
- Reintentar automáticamente con `GROQ_API_KEY_BACKUP` cuando la clave primaria devuelve
  `groq.RateLimitError` (HTTP 429 con `error.type = rate_limit_exceeded` o `tokens_exceeded`).
- Log explícito `[groq-fallback]` al activar la clave de respaldo.
- Cambio mínimo: un solo punto en `app/indexer.py` cubre las 3 funciones de llamada.

**Non-Goals:**
- Rotación proactiva (no se conmuta antes de que falle).
- Persistencia de estado de la clave activa entre llamadas (stateless por diseño).
- Circuit-breaker completo con cooldown y restauración automática.
- Manejo de otros errores HTTP (timeouts, 500s) — esos se propagan como antes.

## Decisions

### D1 — Capturar `groq.RateLimitError`, no `Exception`

La SDK de Groq levanta `groq.RateLimitError` para 429. Capturar solo esa excepción garantiza
que el fallback se activa únicamente por cuota y no enmascara errores reales (timeouts, 5xx).

**Alternativa descartada**: regex sobre el mensaje de `Exception` — frágil si la SDK cambia
el formato del string.

### D2 — Refactorizar en un helper privado `_groq_call`

Las tres funciones (`call_groq_llm`, `call_groq_json`, `call_groq_with_system`) comparten la
misma lógica de construcción de cliente + call. Extraer un helper interno evita duplicar la
lógica de fallback en tres lugares.

```
_groq_call(api_key, messages, model, *, json_mode, temperature, max_tokens) → str
```

Cada función pública construye sus `messages` y delega en `_groq_call`. Si `_groq_call` lanza
`groq.RateLimitError` con la clave primaria, la función pública intenta `GROQ_API_KEY_BACKUP`
antes de propagar.

**Alternativa descartada**: decorador genérico — añade indirección sin beneficio claro dado
que los tres callsites son los únicos consumidores internos.

### D3 — Fallback stateless (sin Redis, sin archivo de estado)

Si el backup también falla, se propaga la excepción (el caller ve el mismo error que antes).
No se persiste "clave activa" porque el volumen de llamadas es bajo y la cuota diaria se
renueva cada 24h; la clave primaria volverá a funcionar sola.

**Riesgo aceptado**: si ambas claves están agotadas, el bot falla igual que antes — no peor.

## Risks / Trade-offs

- [Si `GROQ_API_KEY_BACKUP` no está configurada] el comportamiento es idéntico al actual
  (sin fallback). → No hay regresión; se documenta en `.env.example`.
- [Log de fallback visible en Celery] revela que se usó la clave de respaldo, lo cual podría
  exponer información operativa en logs. → Aceptable; los logs no salen fuera del servidor.
- [El helper privado `_groq_call` no tiene contrato público] → su signature puede cambiar
  libremente sin afectar consumidores externos.

## Migration Plan

1. Implementar `_groq_call` + lógica de fallback en `app/indexer.py`.
2. Descomentar `GROQ_API_KEY_BACKUP` en `.env` (ya tiene valor; solo quitar `# `).
3. `docker compose build worker && docker compose up -d worker`.
4. Rollback: eliminar la lectura de `GROQ_API_KEY_BACKUP`; el comportamiento revierte al
   actual sin cambios de estado externos.

## Open Questions

- ¿Conviene extender el fallback a `call_llm` / `call_cohere_llm`? Por ahora no: esas
  funciones ya tienen su propio fallback (Cohere → Groq) y el cambio estaría fuera de scope.
