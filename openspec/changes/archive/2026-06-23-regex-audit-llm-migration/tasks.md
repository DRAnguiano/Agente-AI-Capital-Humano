## 1. llm-intent-classifiers — "ya" reclamo y memory claims

- [x] 1.1 Crear `_YA_RECLAMO_SYSTEM` en `current_turn.py`: prompt T=0 que clasifica "ya" de reclamo vs confirmación; guardia `"ya "` en `text`
- [x] 1.2 Reemplazar regex `_ya_reclamo` por el nuevo clasificador LLM; mantener la misma semántica de resultado en `extract_current_turn_facts`
- [x] 1.3 Crear `_MEMORY_CLAIM_SYSTEM` en `memory_guard.py`: prompt T=0 para los 6 patrones de `_MEMORY_CLAIM_PATTERNS`; guardia con las palabras clave de la lista actual
- [x] 1.4 Reemplazar `_MEMORY_CLAIM_PATTERNS` por el clasificador LLM; conservar el contrato de retorno de `memory_guard`
- [x] 1.5 Actualizar tests con `@pytest.mark.skipif(_NO_GROQ, ...)`; suite verde

## 2. llm-embedded-question-detector

- [x] 2.1 Crear `_EMBEDDED_QUESTION_SYSTEM` en `current_turn.py`: prompt T=0 binario (`has_business_question`)
- [x] 2.2 Añadir guardia de contexto (lista de palabras señal) antes del LLM call
- [x] 2.3 Reemplazar `_EMBEDDED_QUESTION_RE` y `has_embedded_business_question()` por el nuevo clasificador; exponer misma firma pública
- [x] 2.4 Actualizar tests (`test_embedded_business_question_*`) con skipif; suite verde

## 3. candidate-profile-extraction — renewals, calls, no-road-experience

- [x] 3.1 Crear `_RENEWAL_PROOF_SYSTEM` en `profile_extractor.py`: prompt T=0 para polaridad de comprobante; reemplazar `_has_renewal_proof()`
- [x] 3.2 Unificar `_CALL_REQUEST_RE` y `_CALL_NEG_RE` en un único `_CALL_INTENT_SYSTEM`: devuelve `{call_requested, call_window}`; actualizar caller
- [x] 3.3 Eliminar `_NO_ROAD_EXPERIENCE_RE` de `knowledge_orchestrator.py` (duplicado de `_NO_ROAD_EXP_SYSTEM` de profile_extractor)
- [x] 3.4 Actualizar tests afectados con skipif; suite verde

## 4. Limpieza de listas hardcodeadas de typos

- [x] 4.1 `"sensillo"`/`"censillo"` se mantienen en `VEHICLE_TERMS` (no hay LLM fallback en normalize_vehicle; catalog alias es necesario)
- [x] 4.2 `"bacante"`/`"vancate"`/`"bakante"` se mantienen en `CAMPAIGN_INTEREST_TERMS` (función es lookup puro, no hay LLM fallback para entrada de campaña)
- [x] 4.3 Suite verde sin skipif (estos tests son deterministas)

## 5. Verificación y cierre

- [x] 5.1 Suite completa verde — 737 passed, 0 failed
- [x] 5.2 Rebuild + recreate — hr_rag_api y hr_worker recreados con nueva imagen
- [x] 5.3 `openspec validate regex-audit-llm-migration --strict` — válido
- [x] 5.4 Sincronizar deltas a specs principales (`profile-extraction`, `message-orchestration`) y archivar el change
