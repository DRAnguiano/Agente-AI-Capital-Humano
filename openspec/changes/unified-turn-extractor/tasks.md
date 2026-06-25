> Convención: RED-first (test que falla → implementación → GREEN). Tests Groq-free donde sea posible.
> Migración en SHADOW (log-only) antes de cortar; verificación 1×1 en producción por rama.
> El path actual NO se elimina hasta que el shadow demuestre paridad o mejora.

## 1. Contrato y extractor (sin wirear)

- [x] 1.1 RED+impl: dataclasses `FieldValue {value, explicit_marker, answered_direct_question}` y `TurnExtraction {fields, embedded_question, signals}` en `app/knowledge/turn_extractor.py`
- [x] 1.2 RED+impl: prompt `_TURN_EXTRACTOR_SYSTEM` — una pasada, devuelve JSON con campos crudos + evidencia + embedded_question + señales; NO devuelve confianza ni decisiones de negocio
- [x] 1.3 RED+impl: `extract_turn(message, last_bot_question, known_facts) -> TurnExtraction` — 1 llamada LLM, parseo robusto, degradación segura (JSON inválido → TurnExtraction vacío, sin regex-fallback)
- [x] 1.4 Contratos del extractor verificados: multi-dato no se pisa (exp 10 años vs licencia 2 años ✓), dato+pregunta ("ramon, ¿a cómo pagan?" ✓), referencia cruda capturada para resolver en Capa 2 (la resolución de igualdad "igual que mi licencia"→valor licencia es determinista, vive en 2.1, NO en el prompt)

## 2. Capa 2 — validación determinista

- [x] 2.1 RED+impl: `validate_extraction(TurnExtraction, known_facts) -> facts_validados` — unidad vía `domain_catalog`, edad rango 18-70, licencia A/B/E; valor fuera de catálogo/rango se descarta; resolución determinista de igualdad apto→licencia
- [x] 2.2 RED+impl: campo de texto libre (name, expiration) sin `explicit_marker` ni `answered_direct_question` → no se promueve a fact (mata "Nombre: Hola")
- [x] 2.3 RED+impl: confianza derivada en código `conf = base + catálogo(0.3) + marcador(0.2) + respondió(0.2)`; corrección explícita (is_ya_reclamo) → flag `is_explicit_correction`

## 3. Capa 3 — política de negocio (reusar existente)

- [x] 3.1 Verificado: política (B→sencillo, NON_TARGET→escuelita, local→IMSS) sigue en código (knowledge_orchestrator, chatwoot_note_sync) y consume facts validados; validate_extraction NO toma decisiones de negocio
- [x] 3.2 RED+impl: el extractor reporta `vehicle_type_raw` (torton/quinta rueda) sin fijar `vehicle_type`; `domain_catalog` en Capa 2 decide; Capa 3 (downstream) consume el raw

## 4. Escritura gobernada por confianza (BREAKING)

- [x] 4.1 RED+impl: `upsert_lead_fact` — SQL CASE gobernado por flag `CONFIDENCE_GOVERNED_WRITES`; valor se pisa solo si `conf_nueva ≥ conf_guardada` o `is_explicit_correction`; confianza sigue al valor ganador (no GREATEST ciego)
- [x] 4.2 Contratos verificados: dato débil no pisa fuerte ✓; corrección explícita pisa con conf menor ✓; conf igual pisa ✓
- [x] 4.3 Migración aditiva: flag default OFF preserva comportamiento histórico (siempre pisa + GREATEST); param `is_explicit_correction` con default False (back-compat de firma); sin DDL

## 5. Shadow mode (log-only)

- [x] 5.1 Feature flag `UNIFIED_EXTRACTOR_SHADOW` en `settings.py`
- [x] 5.2 En el worker, `_run_unified_extractor_shadow` llama `extract_turn`+`validate_extraction` log-only, gateado por flag, aislado en try/except
- [x] 5.3 Loggea divergencias de extracción fact-por-fact (actual vs unificado); verificado que captura los 3 facts que el path actual pierde/confunde
- [x] 5.4 Loggea divergencias de ESCRITURA (valor guardado vs candidato + confianza) sin persistir
- [ ] 5.5 Verificación en producción: prender `UNIFIED_EXTRACTOR_SHADOW=true` en .env, recolectar N turnos reales, medir paridad/mejora y costo/latencia (8b vs 70b) — REQUIERE OBSERVACIÓN EN PROD

## 6. Corte al path único

- [ ] 6.1 Computar `TurnExtraction` una sola vez al inicio del turno (worker), antes de bifurcar guard/orquestador
- [ ] 6.2 `handle_message` y `_build_funnel_nudge` consumen `TurnExtraction` en vez de re-extraer
- [ ] 6.3 Reconciliar guard/orquestador: un solo escritor, reply decidido sobre el objeto único (no "quién corre último")
- [ ] 6.4 Absorber TIPC: `turn_intent_classifier` deja de ser llamada aparte; sus señales salen del extractor unificado
- [ ] 6.5 Eliminar `_AGE_SYSTEM`/`_NAME_SYSTEM`/`_EXPERIENCE_YEARS_SYSTEM`/`_EXPIRATION_SYSTEM` (current_turn) y `_PROFILE_*`/`_CITY_FALLBACK`/`_CALL_WINDOW`/`_EXPERIENCE_CONTEXT`/`_RENEWAL_PROOF` (profile_extractor) y sus gates regex
- [ ] 6.6 Conservar validadores deterministas (rango edad, `_renewal_proof_state`, catálogos)

## 7. Verificación y cierre

- [ ] 7.1 Suite Groq-free verde (sin regresión en funnel/labels/note)
- [ ] 7.2 Rebuild + recreate; verificación 1×1 en producción de los 3 bugs de raíz (multi-dato, nombre mezclado, apto "igual que")
- [ ] 7.3 `openspec validate unified-turn-extractor --strict` + `openspec validate --specs --strict`
- [ ] 7.4 Medir reducción real de llamadas LLM/turno (objetivo ~8-10 → ~2-3)
- [ ] 7.5 Sincronizar deltas a specs principales y archivar el change
