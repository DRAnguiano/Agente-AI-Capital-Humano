## Why

El bot falló en producción cuando la clave primaria de Groq alcanzó el límite diario de tokens;
la recuperación fue manual (swap en `.env` + restart del worker). El sistema no tiene mecanismo
para rotar automáticamente a la clave de respaldo (`GROQ_API_KEY_BACKUP`) al recibir un 429 por
cuota agotada, ni para restaurar la clave primaria cuando su cuota se renueve al día siguiente.

## What Changes

- `app/indexer.py` (`call_groq_json`, `call_groq_llm`, `call_groq_with_system`): al recibir un
  `429 / rate_limit_exceeded` de Groq, reintentar el mismo call con la clave de respaldo antes
  de propagar la excepción.
- Añadir variable de entorno `GROQ_API_KEY_BACKUP` como slot formal (ya existe en `.env` como
  comentario; se formaliza su uso).
- Log explícito `[groq-fallback]` cuando se activa la clave de respaldo, para observabilidad.
- No se introduce estado compartido entre workers (el fallback es stateless por call).

## Capabilities

### New Capabilities

- `groq-key-fallback`: Reintento automático con clave de respaldo cuando la clave primaria
  devuelve 429 (cuota agotada). Transparente para el resto del sistema; un solo punto de cambio
  en la capa de llamada a Groq.

### Modified Capabilities

- `message-orchestration`: el orquestador ya no puede quedar bloqueado por cuota de Groq si
  hay clave de respaldo disponible; el contrato de disponibilidad del LLM cambia de "best-effort"
  a "fallback garantizado cuando GROQ_API_KEY_BACKUP está configurada".

## Impact

- `app/indexer.py` — tres funciones de llamada a Groq (`call_groq_json`, `call_groq_llm`,
  `call_groq_with_system`); cambio mínimo: capturar 429 y reintentar con clave alternativa.
- `.env` / `docker-compose.yml` — `GROQ_API_KEY_BACKUP` pasa de comentario a variable activa.
- Sin cambios en la API pública del módulo ni en las interfaces de otros módulos.
- Sin cambios en Neo4j, Chroma, PostgreSQL ni en los flujos de Chatwoot.
