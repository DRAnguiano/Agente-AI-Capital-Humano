## 1. llm-intent-classifiers — "ya" reclamo y memory claims

- [ ] 1.1 Crear `_YA_RECLAMO_SYSTEM` en `current_turn.py`: prompt T=0 que clasifica "ya" de reclamo vs confirmación; guardia `"ya "` en `text`
- [ ] 1.2 Reemplazar regex `_ya_reclamo` por el nuevo clasificador LLM; mantener la misma semántica de resultado en `extract_current_turn_facts`
- [ ] 1.3 Crear `_MEMORY_CLAIM_SYSTEM` en `memory_guard.py`: prompt T=0 para los 6 patrones de `_MEMORY_CLAIM_PATTERNS`; guardia con las palabras clave de la lista actual
- [ ] 1.4 Reemplazar `_MEMORY_CLAIM_PATTERNS` por el clasificador LLM; conservar el contrato de retorno de `memory_guard`
- [ ] 1.5 Actualizar tests con `@pytest.mark.skipif(_NO_GROQ, ...)`; suite verde

## 2. llm-embedded-question-detector

- [ ] 2.1 Crear `_EMBEDDED_QUESTION_SYSTEM` en `current_turn.py`: prompt T=0 binario (`has_business_question`)
- [ ] 2.2 Añadir guardia de contexto (lista de palabras señal) antes del LLM call
- [ ] 2.3 Reemplazar `_EMBEDDED_QUESTION_RE` y `has_embedded_business_question()` por el nuevo clasificador; exponer misma firma pública
- [ ] 2.4 Actualizar tests (`test_embedded_business_question_*`) con skipif; suite verde

## 3. candidate-profile-extraction — renewals, calls, no-road-experience

- [ ] 3.1 Crear `_RENEWAL_PROOF_SYSTEM` en `profile_extractor.py`: prompt T=0 para polaridad de comprobante; reemplazar `_has_renewal_proof()`
- [ ] 3.2 Unificar `_CALL_REQUEST_RE` y `_CALL_NEG_RE` en un único `_CALL_INTENT_SYSTEM`: devuelve `{call_requested, call_window}`; actualizar caller
- [ ] 3.3 Eliminar `_NO_ROAD_EXPERIENCE_RE` de `knowledge_orchestrator.py` (duplicado de `_NO_ROAD_EXP_SYSTEM` de profile_extractor)
- [ ] 3.4 Actualizar tests afectados con skipif; suite verde

## 4. Limpieza de listas hardcodeadas de typos

- [ ] 4.1 Eliminar `"sensillo"` y `"censillo"` de `VEHICLE_TERMS` en `domain_catalog.py` (el LLM ya normaliza desde el mensaje original)
- [ ] 4.2 Eliminar `"bacante"`, `"vancate"`, `"bakante"` de `CAMPAIGN_INTEREST_TERMS` en `current_turn.py`
- [ ] 4.3 Suite verde sin skipif (estos tests son deterministas)

## 5. Verificación y cierre

- [ ] 5.1 Suite completa verde (`docker compose run --rm api-test python -m pytest`)
- [ ] 5.2 Rebuild + recreate; verificación en producción (mensajes con typos reales en Chatwoot)
- [ ] 5.3 `openspec validate regex-audit-llm-migration --strict`
- [ ] 5.4 Sincronizar deltas a specs principales (`profile-extraction`, `message-orchestration`) y archivar el change
