## Why

El grafo de conocimiento contiene ~12 patrones regex que intentan extraer significado del lenguaje natural de los candidatos (polaridad de respuesta, temporalidad, intención condicional, typos) — trabajo que ya hace mejor el LLM T=0. Al mismo tiempo, hay listas hardcodeadas de typos/sinónimos (`"bacante"`, `"vancate"`, `"sensillo"`) dispersas en código y catálogos que acumulan deuda silenciosa cada vez que aparece una nueva variante en producción. El objetivo es consolidar la estrategia LLM-first ya iniciada en `llm-first-extraction` y eliminar la deuda antes de que crezca.

## What Changes

- **Migrar extractores MIGRABLE a LLM T=0**: Los ~12 patrones identificados en el audit (ver Design) se reemplazan por llamadas `call_groq_json` con prompts T=0 equivalentes. No se tocan patrones LEGÍTIMO (guardas estructurales, enums de dominio).
- **Eliminar listas hardcodeadas de typos de código operativo**: `"bacante"`/`"vancate"` en `CAMPAIGN_INTEREST_TERMS`, `"sensillo"`/`"censillo"` en `VEHICLE_TERMS` del catálogo, y cualquier equivalente en `memory_guard.py` y `knowledge_orchestrator.py`. El LLM normaliza los typos desde el mensaje original.
- **Centralizar sinónimos de dominio en catálogo canónico**: Los alias que sean semántica de dominio (no errores tipográficos) permanecen en `domain_catalog.py`; los que sean errores de escritura se eliminan y el LLM los absorbe.
- **Contratos de test actualizados**: Las suites dejan de asertar comportamiento regex sobre typos y pasan a asertar el hecho de negocio resultante (ciudad extraída, vehículo identificado), con `skipif(_NO_GROQ)` donde aplica.

## Capabilities

### New Capabilities

- `llm-intent-classifiers`: Clasificadores LLM T=0 para intención/polaridad que hoy hace regex: "ya reclamo" vs confirmación, "si condicional" vs afirmativo, "no-experiencia" vs experiencia, solicitud de llamada, claims de memoria pasada.
- `llm-embedded-question-detector`: Clasificador LLM T=0 para detectar preguntas de negocio embebidas (hoy `_EMBEDDED_QUESTION_RE`, el patrón más frágil del sistema).

### Modified Capabilities

- `city-extraction`: El flujo cambia de "catálogo primero, LLM fallback" a "LLM primero cuando hay marcador de residencia, catálogo para respuestas directas sin marcador". El contrato de hecho de negocio no cambia (sigue devolviendo `candidate.city`).
- `candidate-profile-extraction`: Nuevos extractores LLM para `_has_renewal_proof`, `_CALL_REQUEST_RE`, `_CALL_NEG_RE` que hoy son regex de polaridad.

## Impact

**Archivos principales afectados:**
- `app/knowledge/current_turn.py` — migrar `_expiry_within_three_months`, `_conditional_si` guard, `_ya_reclamo` guard, `_EMBEDDED_QUESTION_RE`
- `app/lead_memory/profile_extractor.py` — migrar `_has_renewal_proof`, `_CALL_REQUEST_RE`, `_CALL_NEG_RE`
- `app/knowledge/memory_guard.py` — migrar `_MEMORY_CLAIM_PATTERNS` (6 patrones)
- `app/orchestrators/knowledge_orchestrator.py` — migrar `_NO_ROAD_EXPERIENCE_RE`, `_PAID_SENSITIVE_RE`
- `app/knowledge/domain_catalog.py` — eliminar aliases que son typos (`"sensillo"`, `"censillo"`) una vez que el LLM T=0 los absorba
- `app/knowledge/current_turn.py` — eliminar `"bacante"`/`"vancate"` de `CAMPAIGN_INTEREST_TERMS` (idem)

**Tests afectados:**
- `tests/test_first_contact_and_fact_guards.py` — `TestTypoVacante`, `TestSiCondicional`, `TestCiudadAncladaAResidencia`
- `tests/test_call_scheduling.py`, `tests/test_funnel_vigencia_edad.py`

**Dependencias:**
- Requiere `GROQ_API_KEY` en entorno (ya presente en producción)
- Sin cambios a esquema de datos, Chatwoot, Neo4j ni API externa
