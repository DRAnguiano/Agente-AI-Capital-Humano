## 1. Crear turn-intent-classifier

- [x] 1.1 Crear `app/knowledge/turn_intent_classifier.py` con `TurnIntentSignals` dataclass (8 campos, todos con valor neutro por defecto)
- [x] 1.2 Escribir `_TURN_INTENT_SYSTEM` prompt con ejemplos exhaustivos del gremio para los 8 signals
- [x] 1.3 Implementar `classify_turn_intent(message: str) -> TurnIntentSignals`: 1 LLM call T=0, fail-safe completo
- [x] 1.4 Tests unitarios en `tests/test_turn_intent_classifier.py`: happy path con GROQ + fail-safe sin GROQ

## 2. Cablear turn_signals al pipeline de extracción

- [x] 2.1 Añadir `turn_signals: TurnIntentSignals | None = None` a `extract_profile_facts()` y `extract_current_turn_facts()`; si None → llamar `classify_turn_intent` internamente (compat tests)
- [x] 2.2 Añadir `turn_signals` a `_is_memory_claim()` en `memory_guard.py`
- [x] 2.3 Añadir `turn_signals` a `has_embedded_business_question()` en `current_turn.py`
- [x] 2.4 En `knowledge_orchestrator.py`: llamar `classify_turn_intent(message)` una vez y pasar `turn_signals` a todos los extractores

## 3. Eliminar guards semánticos de keyword

- [x] 3.1 `current_turn.py`: eliminar `_EMBEDDED_Q_HINTS`, `_EMBEDDED_Q_SIGNAL`; leer `turn_signals.has_embedded_question`
- [x] 3.2 `current_turn.py`: eliminar gate `t.startswith("ya ")`; leer `turn_signals.is_ya_reclamo`
- [x] 3.3 `memory_guard.py`: eliminar `_MEMORY_CLAIM_HINTS`; leer `turn_signals.is_memory_claim`
- [x] 3.4 `profile_extractor.py`: eliminar `_CALL_INTENT_HINTS`; leer `turn_signals.call_requested`
- [x] 3.5 `profile_extractor.py`: eliminar `_RENEWAL_PROOF_HINTS`; leer `turn_signals.renewal_proof`
- [x] 3.6 `profile_extractor.py`: eliminar `_no_road_hints`; leer `turn_signals.no_road_experience`
- [x] 3.7 `profile_extractor.py`: eliminar `_expiry_hints`; leer `turn_signals.has_expiry_context`
- [x] 3.8 `profile_extractor.py`: eliminar `DRIVING_TERMS` como gate de experience years; leer `turn_signals.experience_context`

## 4. Actualizar tests

- [x] 4.1 Marcar `@pytest.mark.skipif(_NO_GROQ, ...)` donde corresponda (tests que ahora dependen del TIPC)
- [x] 4.2 Añadir casos que prueban vocabulario no listado previamente: "soy principiante", "ponerse en contacto", "se me acaba", "eso ya lo había comentado"
- [ ] 4.3 Suite completa verde (`docker compose run --rm api-test python -m pytest`)

## 5. Verificación y cierre

- [ ] 5.1 Rebuild + recreate contenedores
- [ ] 5.2 Verificación en producción: probar mensajes con vocabulario variado del gremio en Chatwoot
- [ ] 5.3 `openspec validate remove-guard-hints --strict`
- [ ] 5.4 Sync deltas a specs principales y archivar
