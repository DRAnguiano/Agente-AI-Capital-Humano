## Why

Las respuestas generadas por el LLM en las rutas `friendly_smalltalk` y `rag` están produciendo alucinaciones: datos de perfil, cifras, condiciones laborales o características de la empresa que el candidato no mencionó ni el RAG recuperó. La temperatura actual (`TEMPERATURE=0.10` en `.env`, con fallback `0.15` hardcodeado en `indexer.py`) introduce variabilidad innecesaria en un contexto donde la fidelidad al mensaje y al contexto recuperado es crítica. Adicionalmente, los regex de palabras clave que disparan respuestas canned fuera de las políticas de negocio deterministas generan respuestas robóticas e inconsistentes. Las preguntas del funnel (greeting, farewell, document_ack, stage transitions) son strings fijos y deben permanecer como están — esas no son el problema.

## What Changes

- Bajar `TEMPERATURE` a `0.0` en `.env` y eliminar el default hardcodeado en `indexer.py` (reemplazar por `0.0` directo o leer siempre desde settings sin fallback distinto).
- Eliminar el banco de respuestas canned (regex de palabras clave) que intercepta mensajes antes del LLM generador fuera de las rutas de política de negocio deterministas. Los únicos regex que permanecen son los de política (`_B1_US_RE`, `_REINGRESO_RE`, `_NON_TARGET_RE`, `_PAID_SENSITIVE_RE`, `_CADUCIDAD*`) porque son handoffs y guardias de seguridad deterministas, no generación.
- Las preguntas del funnel (`GREETING_REPLY`, `FAREWELL_REPLY`, `DOCUMENT_ACK_REPLY`, stage questions) son deterministas y **no se tocan**.

## Capabilities

### New Capabilities

_(ninguna — es una corrección de comportamiento del generador existente)_

### Modified Capabilities

- `message-orchestration`: El generador `call_llm` usa temperatura `0.0` en todos los paths conversacionales (friendly, rag, clarification). Requisito: temperatura configurable vía `.env`; default `0.0`; sin fallback hardcodeado diferente.
- `llm-intent-classifiers`: El clasificador shadow ya usa `call_groq_json` con `temperature=0.0` explícito — verificar que siga igual (no se modifica, solo se confirma).

## Impact

- `app/indexer.py` — eliminar default hardcodeado `0.15`; leer `TEMPERATURE` de settings con default `0.0`.
- `app/settings.py` — cambiar `TEMPERATURE` default de `0.1` a `0.0`.
- `.env` — actualizar `TEMPERATURE=0.0`.
- `app/orchestrators/knowledge_orchestrator.py` — auditar y eliminar cualquier banco de respuestas canned (regex de keywords → texto fijo) que NO sea política de negocio determinista (B1, reingreso, escuelita, fraude). Los `_NO_ANSWER_HINTS` con su respuesta neutral se mantienen (son anti-alucinación, no generación).
- No hay cambios en API, esquema de BD, Neo4j ni Chatwoot.
