## Context

El bot usa `call_llm` (en `app/indexer.py`) para generación conversacional en rutas `friendly_smalltalk` y `rag`. La temperatura controla la aleatoriedad del modelo; valores mayores a `0.0` permiten que el LLM "rellene" con datos no presentes en el prompt — la fuente principal de alucinaciones observadas (cifras de sueldo inventadas, años de experiencia asumidos, condiciones laborales no mencionadas).

Estado actual:
- `.env`: `TEMPERATURE=0.10`
- `app/settings.py`: `_env_float("TEMPERATURE", 0.1)` — lee de `.env` correctamente.
- `app/indexer.py`: `TEMPERATURE = float(getattr(settings, "TEMPERATURE", os.getenv("TEMPERATURE", "0.15")))` — el fallback `"0.15"` nunca se activa porque `settings.TEMPERATURE` siempre existe, pero es un valor incorrecto que puede confundir.

Además, en `knowledge_orchestrator.py` existe un conjunto de `_NO_ANSWER_HINTS` con respuesta neutral fija — esos son anti-alucinación y se mantienen. Los regex de política de negocio (`_B1_US_RE`, `_REINGRESO_RE`, `_NON_TARGET_RE`, `_PAID_SENSITIVE_RE`) son guardias deterministas y tampoco se tocan.

## Goals / Non-Goals

**Goals:**
- Temperatura `0.0` en todos los paths de generación conversacional (friendly, rag, clarification).
- Eliminar el fallback hardcodeado `0.15` en `indexer.py`.
- Confirmar que `call_groq_json` (clasificador) ya usa `temperature=0.0` explícito — no modificar.
- Las preguntas del funnel permanecen como strings deterministas sin cambio.

**Non-Goals:**
- No cambiar la lógica de ruteo ni el clasificador.
- No modificar los regex de política de negocio (B1, reingreso, escuelita, fraude).
- No alterar el schema de BD ni Neo4j.
- No eliminar `_NO_ANSWER_HINTS` (esos son anti-alucinación correctos).

## Decisions

**D1: `TEMPERATURE=0.0` como único valor, sin fallback diferente**
`call_llm` en `indexer.py` debe usar `settings.TEMPERATURE` directamente (que lee de `.env`). El fallback se cambia de `"0.15"` a `"0.0"` para que incluso si settings falla, el comportamiento sea conservador.

Alternativa considerada: temperatura diferente por ruta (0.0 para rag, 0.2 para friendly). Descartada — el friendly LLM también alucina con temperatura > 0 porque interpola datos del contexto del lead.

**D2: No eliminar los regex de política de negocio**
`_B1_US_RE`, `_REINGRESO_RE`, `_NON_TARGET_RE`, `_PAID_SENSITIVE_RE` son políticas operativas deterministas. Eliminarlos requeriría que el LLM clasificara estos casos, introduciendo variabilidad donde no se quiere. Se mantienen como están.

**D3: Auditoría de canned responses fuera de política**
Revisar si existe algún banco de respuestas regex→texto_fijo fuera de las políticas de negocio documentadas. Si se encuentran, eliminar y dejar que el LLM con temperatura 0 maneje esos casos con el prompt existente.

## Risks / Trade-offs

- [Riesgo] `temperature=0.0` hace que el LLM sea totalmente determinista: el mismo prompt produce siempre la misma respuesta. → Mitigación: el prompt ya incluye contexto del lead y el mensaje del candidato como variables; la respuesta varía naturalmente con el contexto de cada conversación.
- [Riesgo] Respuestas pueden sentirse más secas sin la variabilidad de temperatura. → Mitigación: el prompt del friendly ya está diseñado para ser cálido; la variación proviene del contexto del candidato, no de la temperatura.

## Migration Plan

1. Cambiar `.env`: `TEMPERATURE=0.0`.
2. Cambiar `app/settings.py` default: `_env_float("TEMPERATURE", 0.0)`.
3. Cambiar fallback en `app/indexer.py`: `os.getenv("TEMPERATURE", "0.0")`.
4. Auditar `knowledge_orchestrator.py` en busca de bancos canned fuera de política; eliminar si existen.
5. Reiniciar `api` y `worker` (`docker compose restart api worker`).
6. Rollback: revertir `.env` y reiniciar — sin cambio de esquema, rollback es inmediato.
