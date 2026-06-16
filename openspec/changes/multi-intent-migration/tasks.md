> Convención: cada tarea `[x]` cita evidencia como `archivo · función/símbolo · verificación`.
> Verificación disponible hoy: endpoint `POST /classify` (app/app.py:343), log
> `[MULTI_INTENT_SHADOW]`, y suite pytest en `tests/` (corre en `api-test`).
>
> ESTADO DE FASES (2026-06-04):
> - Fase 0 (F6/F26/F30): **desplegada y validada en producción**.
> - Fase 1A (domain_catalog + normalize/disambiguate/contextual + intents roleplay): **en repo/test** (commit `8262c7d`); aislada, no en el flujo vivo (activa en cutover).
> - Fase 1B (F8 en camino vivo: `profile_extractor` consume `domain_catalog`): **desplegada y validada en producción** (commit `c6e345d`).
> - Evidencia: pytest **29 passed** (api-test) · `openspec validate --specs` 7 passed · `multi-intent-migration` valid · producción verificada (`normalize_vehicle` presente en el contenedor; `vehicle_type=quinta_rueda` ya no se escribe).

## 1. Fase 1 — Clasificador (hecho)

- [x] 1.1 Catálogo de intents (answer/question/signal/handoff) — `docs/esquema_perfilamiento_v1.md` §8; `app/knowledge/intent_classifier.py` · `ALL_INTENTS`/`ANSWER_FIELDS` · revisión doc
- [x] 1.2 `classify_message` con `GROQ_CLASSIFIER_MODEL` (8b-instant, temp 0.0) — `app/knowledge/intent_classifier.py` · `classify_message`/`CLASSIFIER_MODEL` · `POST /classify`
- [x] 1.3 Few-shot de mensajes compuestos reales — `app/knowledge/intent_classifier.py` · `CLASSIFIER_SYSTEM` · revisión prompt
- [x] 1.4 `last_bot_question` como contexto elíptico — `app/knowledge/intent_classifier.py` · `classify_message(last_bot_question=...)` · `POST /classify`
- [x] 1.5 Fallback seguro ante JSON inválido/error — `app/knowledge/intent_classifier.py` · `_empty_classification` · `POST /classify`

## 2. Fase 2 — Enricher / validación (hecho)

- [x] 2.1 `evidence_ok` (evidencia literal en el mensaje) — `app/knowledge/intent_classifier.py` · `_evidence_in_message`/`validate_classification` · `POST /classify`
- [x] 2.2 Filtrar `answers_to_persist` por `evidence_ok AND confidence ≥ 0.85` — `app/knowledge/intent_enricher.py` · `enrich_classification`/`CONFIDENCE_THRESHOLD` · `POST /classify`
- [x] 2.3 Resolver conflictos de campo — `app/knowledge/intent_enricher.py` · `_resolve_answer_conflicts` · `POST /classify`
- [x] 2.4 Mapa `INTENT_POLICIES` + bifurcación `safety_intent` por `is_admission` — `app/knowledge/intent_enricher.py` · `INTENT_POLICIES`/`_enrich_question` · `POST /classify`
- [x] 2.5 Agregar `requires_human` y `max_risk_level` — `app/knowledge/intent_enricher.py` · `enrich_classification` (agregados) · `POST /classify`

## 3. Fase 3 — Orchestrator / funnel base (hecho)

- [x] 3.1 Funnel de 6 preguntas en una fuente — `app/knowledge/intent_orchestrator.py` · `FUNNEL_STEPS` · revisión vs esquema v1 §1
- [x] 3.2 `next_funnel_question` + `core_completeness` — `app/knowledge/intent_orchestrator.py` · `next_funnel_question`/`core_completeness` · `POST /classify`
- [x] 3.3 `plan_and_respond`: orden handoff→RAG→señal→funnel, sin efectos colaterales — `app/knowledge/intent_orchestrator.py` · `plan_and_respond` · `POST /classify`
- [x] 3.4 Respuestas de señal con voz de equipo; multi-pregunta ofrece secundaria — `app/knowledge/intent_orchestrator.py` · `_SIGNAL_REPLIES`/`plan_and_respond` · `POST /classify`

## 4. Fase 4 — Shadow + endpoint (hecho)

- [x] 4.1 `run_shadow` bajo flag `MULTI_INTENT_SHADOW`, no propaga excepción — `app/knowledge/intent_shadow.py` · `run_shadow` · log `[MULTI_INTENT_SHADOW]`
- [x] 4.2 Hook de shadow en el orquestador — `app/orchestrators/knowledge_orchestrator.py:1180` · `handle_message` (bloque `MULTI_INTENT_SHADOW`) · log
- [x] 4.3 Log comparativo `[MULTI_INTENT_SHADOW]` (shadow vs actual, ms) — `app/knowledge/intent_shadow.py` · `run_shadow` (print JSON) · log
- [x] 4.4 Endpoint `POST /classify` — `app/app.py:343` · handler `/classify` · curl

## 5. Política de `pay_question`

Estado parcial: clasificación y política base implementadas en Fase 0/F30.

- [x] 5.1 Configurar `pay_question` con política `medium/rag/conditional`.
  - Evidencia: `INTENT_POLICIES["pay_question"]` en
    `app/knowledge/intent_enricher.py` y
    `test_f30_pay_question_policy`.
- [x] 5.2 Implementar "sin fuente autorizada suficiente → no inventar → derivar a Capital Humano" — `app/knowledge/intent_orchestrator.py` · `_generate_rag_answer`/`plan_and_respond` (fail-closed: 0 chunks del filtro `preferred_sources` o LLM vacío → `_HANDOFF_REPLY` + `handoff_reason="no_authorized_source"`, sin invocar LLM cuando no hay fuente; corta como handoff sin encimar funnel; demás intents RAG conservan fallback telefónico) · Docker 461 passed (2026-06-11)
- [x] 5.3 Caso de prueba: pay sin contexto RAG → handoff (sin cifras inventadas) — `tests/test_intent_orchestrator_pay.py` (7 tests deterministas, sin Groq/Chroma/DB; incluye end-to-end enricher→orquestador y no-regresión de logistics) · Docker 461 passed (2026-06-11). `/classify` con clasificación LLM real queda cubierto al activar 9.x.

## 6. Conversation memory guard

- [x] 6.1 Etapa `memory_guard`: leer `lead_memory` y derivar `forbidden_questions` por fact con
  evidence válido — `app/knowledge/memory_guard.py` · `apply_memory_guard`/`derive_forbidden_questions`
  (etapa PURA: recibe `known_facts`, el snapshot de `lead_memory`; la Fase 4 los leerá de Postgres) ·
  `tests/test_memory_guard.py`
- [x] 6.2 No emitir pregunta de un campo ya respondido — `app/knowledge/intent_orchestrator.py` ·
  `next_funnel_question(facts, forbidden_questions)` salta los campos prohibidos; `plan_and_respond`
  los inyecta desde el memory_guard. (`funnel_state_planner.compute_funnel_state` ya derivaba
  `forbidden_questions` desde facts canónicos SAFE; aquí se conecta al funnel del path multi-intent
  `/classify`.) · `tests/test_memory_guard.py::test_plan_does_not_repeat_answered_questions`
- [x] 6.3 Detectar reclamo de memoria ("ya te había dicho que full") y resolverlo según el
  fact canónico, NO como mensaje normal — `memory_guard._is_memory_claim` + `apply_memory_guard`
  (resolution `reaffirm`/`process_as_fact`/`conflict`); `intent_orchestrator` reafirma sin
  reescribir/repreguntar, procesa como fact normal, o pide confirmación neutral sin encimar funnel:
  (1) fact canónico coincidente → reafirmar, no reescribir, no repetir la pregunta;
  (2) fact canónico ausente → procesar el valor explícito del turno por el pipeline
  normal de facts (no perder el dato);
  (3) fact canónico diferente → registrar conflicto, no sobrescribir, pedir
  confirmación neutral.
  Distinto de la corrección explícita (7.4), que sí sobrescribe con auditoría.
- [x] 6.4 Casos: "ya te habia dicho que full"; "si tengo cartas" (no repreguntar) —
  `tests/test_memory_guard.py` (deterministas vía `plan_and_respond`, sin Groq/Chroma/DB). La
  cobertura por `/classify` con clasificación LLM real queda cubierta al activar 9.x.

## 7. Desambiguación y corrección de facts + estados

- [x] 7.1a **(PARCIAL — solo unidad/vehicle)** Etapa `normalize_domain_values` + `domain_catalog`: full/sencillo→confirmed; quinta rueda/tráiler/tractocamión→needs_clarification; camión→ambiguo; torton/rabón/reparto/local/camioneta→no objetivo — `app/knowledge/normalize_domain_values.py`·`domain_catalog.py` · tests Fase 1A · commit `8262c7d`. **PENDIENTE:** normalización de licencia/B/E/apto/vigente/documentos (siguen como regex en `profile_extractor`).
- [x] 7.1b Etapa `disambiguate_numeric_units`: números según `last_bot_question`; sin contexto → aclarar — `app/knowledge/disambiguate_numeric_units.py` · tests deterministas · commit `8262c7d`
- [x] 7.1c Etapa `contextual_answer_classifier`: sí/no/elípticas con `last_bot_question` + estado del funnel (sin regex global; persiste solo si sabe el campo) — `app/knowledge/contextual_answer_classifier.py` · tests · commit `8262c7d`
- [x] 7.2 Etapa `detect_fact_corrections`: dato nuevo | corrección | contradicción —
  `app/knowledge/fact_corrections.py` · `resolve_facts`/`_resolve_one` clasifican el acto a
  partir de la **señal estructurada del clasificador** (`is_correction`/`certainty`) + estado
  previo, NO de regex/frases. (El caso "incompleto" lo resuelve el funnel planner como
  `missing`/`needs_confirmation`, no esta etapa.) · `tests/test_fact_corrections.py`
- [x] 7.3 Etapa `resolve_fact_conflicts`: contradicción sin confirmación → `conflict`/`needs_confirmation`
  (no sobrescribe) — `fact_corrections._resolve_one`; antes de declarar conflicto NORMALIZA ambos
  valores dentro del dominio F (`normalize_fact_value`: caja/acentos/dígitos↔palabras/unidad), así
  un mismo valor en distinta forma NO genera conflicto; sin valor canónico resoluble NO genera
  conflicto estructurado · `tests/test_fact_corrections.py`
- [x] 7.4 Corrección explícita ("me equivoqué, son 10 años") → `corrected` + auditoría
  (`previous_value`/`new_value`/`correction_evidence`/`source_turn_id`) que sobrescribe —
  `fact_corrections` (estado `corrected` + lista `corrections`) · `tests/test_fact_corrections.py::test_explicit_correction_overwrites_with_audit`
- [x] 7.5 Estados de fact `confirmed | inferred_from_context | needs_confirmation | conflict | corrected` —
  `fact_corrections.FACT_STATES` + `ResolvedFact.state`. **Persistencia:** el estado viaja en el
  fact resuelto y la Fase 4 (cutover) lo escribe en una columna `state` de `rh_lead_facts_v2`;
  las correcciones persisten una fila de auditoría. La etapa es pura y no escribe BD todavía
  (design.md · Migration Plan: construir etapas → cutover) · `tests/test_fact_corrections.py::test_all_emitted_states_are_in_catalog`
- [x] 7.6 Casos: "10" sin contexto (no guarda); "10" tras años (=10); "no se creo que 10"
  (no sobrescribe 9) — cubiertos deterministas vía `resolve_facts` (sin contexto → no llega answer
  núcleo → no persiste; corrección dudosa `certainty=low` → `needs_confirmation`) en
  `tests/test_fact_corrections.py`. Cobertura por `/classify` con LLM real al activar 9.x.

## 8. Funnel state planner + auditoría

- [x] 8.1 Calcular por turno `completed_fields`, `missing_fields`, `forbidden_questions`,
  `next_question`, `facts_before`, `facts_after` — `app/knowledge/turn_planner.py` · `plan_turn`
  (integra memory_guard + fact_corrections + funnel de 6) · `tests/test_turn_planner.py`
- [x] 8.2 El sistema fija `next_question`; el LLM (70B) solo la redacta (no elige campo) —
  `turn_planner` produce `next_question`/`next_question_field` deterministas desde el funnel; la
  redacción cordial sigue en el 70B (sin elegir campo) · `tests/test_turn_planner.py::test_next_question_emits_asked_field_keys`
- [x] 8.3 Traza de auditoría: `facts_before`, `candidate_corrections`, `facts_pending_confirmation`,
  `facts_after`, `missing_fields`, `forbidden_questions`, `next_question`, `confirmation_question` —
  `plan_turn` devuelve la traza completa · `tests/test_turn_planner.py::test_trace_has_all_audit_keys`
- [x] 8.4a Intents meta `roleplay_instruction`/`prompt_injection_like` añadidos al clasificador + reglas de prompt (ortografía / roleplay no obedecido) — `app/knowledge/intent_classifier.py` (`META_INTENTS`) · commit `8262c7d`
- [x] 8.4b Formalizar fields/intents pendientes: `availability`, `general_vacancy_info_request`,
  reclamo de memoria — `candidate.availability_status` (nombre canónico vivo, el que ya consume
  `calculate_candidate_labels`) añadido a `ANSWER_FIELDS` y marcado no-núcleo
  (`turn_planner.NON_CORE_FIELDS`: se captura, no gatea — consistente con 2C.1, que solo excluye del
  gate al legacy `availability_to_attend`); reclamo de memoria formalizado como etapa
  (`memory_guard`, sección 6); info general de vacante cubierta por el intent `vacancy_question`. La
  enumeración en el prompt del clasificador se activa con la clasificación LLM (9.x).
- [x] 8.5 Caso "10 años de full estoy disponible" → years=10, vehicle_type=full,
  `candidate.availability_status=available` (no-núcleo, no gatea), sin repreguntar unidad —
  `tests/test_turn_planner.py::test_compound_extracts_all_and_does_not_reask_unit`
  (determinista vía `plan_turn`; `/classify` con LLM real al activar 9.x)
- [x] 8.6 Caso "¿que mas le falta?" → responde `missing_fields` del planner —
  `plan_turn` calcula `missing_fields` desde Postgres/known_facts (no lista inventada por el LLM) ·
  `tests/test_turn_planner.py::test_missing_fields_reflect_known_facts`. La redacción de la respuesta
  con esos `missing_fields` en `/classify` con LLM real se activa en 9.x.
- [x] 8.7 REUSO de la captura de `asked_field_keys` del camino vivo —
  `turn_planner` emite `asked_field_keys` en el MISMO espacio canónico que consume
  `app/lead_memory/last_asked_field.py` (sin duplicar el reader): la Fase 4 las persiste en
  `external_metadata.asked_field_keys` por el mecanismo existente. Doble propósito (apoyo al parser
  contextual + métrica de embudo) intacto · `tests/test_turn_planner.py::test_asked_field_keys_match_next_field`

## 9. Validación con tráfico real (en curso)

- [ ] 9.1 Activar `MULTI_INTENT_SHADOW=true` en entorno con tráfico real y recolectar logs
- [ ] 9.2 Comparar `shadow_reply` vs `actual_reply` y medir `shadow_ms`
- [ ] 9.3 Construir suite de regresión de mensajes reales para `/classify` (casos abajo)

Casos reales de regresión (fixtures `/classify`):
- [ ] 9.3.1 "10 años de full estoy disponible" → `experience.years=10`, `vehicle_type=full`,
  `candidate.availability_status=available` — campo NO-núcleo: se captura (nombre canónico vivo)
  pero NO gatea `profile_ready` ni entra al funnel. Consistente con 2C.1 (que solo excluye del gate
  al legacy `availability_to_attend`/`disponible_acudir`, no la captura). No repreguntar unidad.
- [ ] 9.3.2 "si tengo cartas" → `documents.proof=cartas` (fact canónico, `ANSWER_FIELDS` +
  scenario del spec `multi-intent-pipeline`); no repetir preguntas no relacionadas ya respondidas
- [ ] 9.3.3 "ya te habia dicho que full" → `memory_complaint_or_correction`; resolver según
  fact canónico (contrato 6.3): coincide → reafirmar sin reescribir; ausente → procesar
  `vehicle_type=full` por el pipeline normal; difiere → conflicto + confirmación neutral,
  sin sobrescribir. En ningún caso repetir la pregunta.
- [x] 9.3.4 "full" con `last_bot_question` de unidad → `vehicle_type=full` — cobertura **determinista** (`contextual_answer_classifier`/`normalize_vehicle`, Fase 1A). `/classify` LLM pendiente.
- [x] 9.3.5 "10" sin contexto → no guarda, pide aclaración — cobertura **determinista** (`disambiguate_numeric_units`, Fase 1A). `/classify` LLM pendiente.
- [x] 9.3.6 "camión" → ambiguo, no infiere full/sencillo — cobertura **determinista** (`normalize_vehicle` + `profile_extractor`, Fase 1A/1B). `/classify` LLM pendiente.
- [x] 9.3.7 "soy operador de quinta rueda" → compatible, sin `vehicle_type` final — cobertura **determinista** (Fase 1A/1B). `/classify` LLM pendiente.
- [x] 9.3.8 "manejo tráiler" → `needs_clarification`, sin `vehicle_type` — cobertura **determinista** (Fase 1A/1B). `/classify` LLM pendiente.
- [ ] 9.3.9 "hola como esta el clima" → out_of_scope; no iniciar perfilamiento
- [ ] 9.3.10 "Hola. ¿Puedo obtener más información sobre esto?" → `general_vacancy_info_request` (intent pendiente de formalizar — 8.4b); no documentos pendientes
- [ ] 9.3.11 "no se crea creo que tengo en realidad 10 años" → categoría `contradicción`
  (contrato 7.2/7.3) → `needs_confirmation`; no sobrescribir el valor previo; pedir
  confirmación neutral. Sin estados fuera del catálogo 7.5.

## 10. Candidate profile label planner (pendiente)

- [ ] 10a.1 Label planner determinista: facts confirmados + estado de perfil → `labels_to_add`/`labels_to_remove` (el LLM no decide labels)
- [ ] 10a.2 `objetivo_full_sencillo` SOLO con `vehicle_type` confirmado full/sencillo; quinta rueda/tráiler/tractocamión = compatible pero `needs_clarification` → `falta_unidad` (+ `aclaracion_pendiente`), NO `objetivo_full_sencillo`; no objetivo → `cecati_sugerido` (sin experiencia) / `considerar_escuelita_transmontes` (torton/rabón/local). No emitir las deprecadas `cecati` ni `escuelita`.
- [ ] 10a.3 Unidad ambigua ("camión", "tráiler", "caja seca") → no actualizar `vehicle_type`, pedir aclaración
- [ ] 10a.4 Número aislado sin contexto → no persistir (edad/días/meses/años); pedir aclaración; con `last_bot_question` de años → `experience_years` + `unit=years`
- [ ] 10a.5 Clasificación local/foráneo vía catálogo de ciudades → `local_laguna` / `foraneo` (+ `validar_traslado`). PRIORIDAD ALTA: el agente requiere local/foráneo como información core junto a `perfil_listo` para continuar la contratación; hoy `perfil_listo` llega sin esa señal (emisión de `local_laguna`/`foraneo` diferida en `calculate_candidate_labels`). Es determinista (catálogo de ciudades): bajo riesgo, alto valor; subir en la cola tras el cierre de la Nota IA.
- [ ] 10a.6 Disponibilidad para acudir: preguntar si falta `availability_to_attend`; al confirmar → `disponible_acudir`. DIFERIDO — `disponible_acudir` es legacy/deprecada; ver futura fase call_scheduling/callback.
- [ ] 10a.7 Pipeline de faltantes hasta `perfil_listo`: labels de faltantes + `perfil_listo` (elimina `bot_activo`, detiene preguntas)
- [ ] 10a.8 Reingreso → `reingreso_verificar`, elimina `bot_activo`, deriva a humano, detiene funnel
- [ ] 10a.9 No modificar facts/labels sin evidencia suficiente
- [ ] 10a.10 Logs del planner: `facts_before`, `facts_after`, `completed_fields`, `missing_fields`, `labels_to_add`, `labels_to_remove`, `next_question`, `reason`
- [ ] 10a.11 Definir dónde se aplican las labels: extender `app/chatwoot_note_sync.py` (hoy emite labels desde lead_memory) o módulo nuevo del pipeline

## 10b. Postgres truth + Chatwoot label sync (parcial — vista ya deriva)

- [x] 10b.1 Verificar existencia de tablas/vista núcleo en `hrdb` — `hr_postgres` · `rh_leads_v2`/`rh_lead_facts_v2`/`rh_lead_messages_v2`/`rh_lead_events_v2`/`rh_seguimiento_tareas`/`v_rh_work_queue` · `psql information_schema` (las 6 existen)
- [x] 10b.2 Verificar que la vista ya deriva labels/estado desde Postgres — `v_rh_work_queue` · `suggested_chatwoot_labels`/`is_profile_ready`/`perfil_status` · `psql` (columnas presentes)
- [ ] 10b.3 `label_planner`/`chatwoot_sync` consumen `v_rh_work_queue` como base de labels (no reinventar) — `app/chatwoot_note_sync.py`
- [ ] 10b.4 Flujo del turno: extraer→validar→actualizar Postgres→recalcular desde Postgres→labels→sync Chatwoot→auditar
- [ ] 10b.5 Agregar estado de fact a `rh_lead_facts_v2` (columna nueva) o tabla aparte — hoy no existe
- [ ] 10b.6 Verificación de completitud núcleo + sin conflicto en Postgres antes de `perfil_listo` (remueve `bot_activo`)
- [ ] 10b.7 No-sobrescritura silenciosa de conflictos: fact pendiente / evento de corrección
- [ ] 10b.8 Tabla/registro de auditoría de label sync: `conversation_id`, `lead_id`, `labels_before/after`, `labels_to_add/remove`, `reason`, `facts_source`, `event_id` (¿`rh_lead_events_v2.metadata` o tabla nueva?)
- [x] 10b.9 Mapa canónico de nombres de facts + 4 decisiones fijadas — `design.md` · "Mapa canónico de nombres de facts"/"Decisiones fijadas" · verificado vs `rh_lead_facts_v2`
- [ ] 10b.10 Migración SQL: renombrar `fact_key` `license.category` → `license.type` en `rh_lead_facts_v2` (conservar valores B/E/A/C) — `db/` nueva migración
- [ ] 10b.11 Migración SQL: consolidar `documents.labor_letters_status`/`labor_letters`/`general_status`/`submission_status`/`availability_claim` → `documents.proof` (cartas|semanas_imss|ninguno) — `db/` nueva migración
- [ ] 10b.12 Crear fact `candidate.availability_to_attend` (≠ viajar) + label `disponible_acudir` en el planner. DIFERIDO — `disponible_acudir` es legacy/deprecada; ver futura fase call_scheduling/callback.
- [x] 10b.13 Vocabulario `vehicle_type` = full|sencillo|ambos|ninguno (sin `quinta_rueda`); "quinta rueda"/tráiler/tractocamión = experiencia compatible, NO valor — `app/knowledge/domain_catalog.py` + `app/lead_memory/profile_extractor.py` (camino vivo) · Fase 1B commit `c6e345d` · verificado en producción
- [ ] 10b.14 Actualizar `v_rh_work_queue` y vistas dependientes tras los renombres de `fact_key` — `db/`/`sql/`
- [ ] 10b.15 **Fase 2A** — Vista de compatibilidad de LECTURA `v_rh_lead_facts_canonical` (no destructiva; expone `canonical_group/key/value/state` + raw). Diseñada read-only; pendiente de aplicar/probar manual. NO toca datos, NO toca `v_rh_work_queue`, NO toca flujo vivo.
- [x] 10b.16a **Fase 2B.1** — `funnel_state_planner` PURO (sin DB/LLM): `completed_fields` (dict auditable), `missing_fields`, `forbidden_questions`, `needs_confirmation_fields`, `conflict_fields`, `next_question_{field,text,reason}`, `profile_ready`. Prioridad conflict > needs_confirmation > missing. Estados seguros: ok/mapped_to_proof/mapped_from_document_group — `app/knowledge/funnel_state_planner.py` · `tests/test_phase2b_funnel_state_planner.py` (8 fixtures fabricados).
- [x] 10b.16b **Fase 2B.2** — `canonical_profile_reader` (I/O mínimo, shadow-safe): lee `v_rh_lead_facts_canonical` → `list[CanonicalFact]` (reutiliza la dataclass del planner). SELECT read-only parametrizado + `ORDER BY observed_at DESC NULLS LAST`. Si la vista no existe o hay error → `[]` + warning, NUNCA rompe el flujo vivo — `app/lead_memory/canonical_profile_reader.py` · `tests/test_phase2b2_canonical_reader.py` (mapeo + degradación sin DB). Integración real = manual en 2B.3.
- [x] 10b.16c **Fase 2B.3** — vista `v_rh_lead_facts_canonical` aplicada y validada contra datos reales (paridad 317/317; reader+planner OK; conflictos apto chatwoot:53/64/75; quinta_rueda legacy NULL). Vista queda activa para 2B.4. Verificado manual.
- [x] 10b.16e **Fase 2B.4 (Opción B)** — shadow OFFLINE/REPLAY del planner canónico: mide planner (read_canonical_facts→compute_funnel_state) vs estado vivo (heurístico), solo lectura, en `api-test` vía stdin. Detecta repreguntas evitables / conflictos / needs_confirmation. NO wiring, NO decisiones vivas — `scripts/shadow_canonical_funnel.py`. (A = shadow in-process con rebuild: diferido.)
- [x] 10b.16f **Fase 2C.0 (decisión documentada)** — (1A) `profile_ready` = 6 núcleo (license.type, medical.apto_status, documents.proof, candidate.city, experience.vehicle_type, experience.years); `availability_to_attend` fuera del gate (paso de agenda, evidencia candidata no se promueve). (2-review) backlog `vehicle_type` legacy no se reclasifica; queda needs_clarification + label `falta_unidad`; revisión de las 5 filas quinta_rueda solo diagnóstico manual. — spec `multi-intent-pipeline` ("Gate de profile_ready = 6 campos núcleo") + `design.md`.
- [x] 10b.16g **Fase 2C.1** — `funnel_state_planner.CORE_FIELDS` = 6 núcleo; `availability_to_attend`/`_candidate` **eliminados del profile planner** (ignorados; sin `EVIDENCE_KEY`, sin `availability_state`, sin `post_profile_next`). `profile_ready` = 6 núcleo. Tests actualizados (`test_availability_is_ignored_by_profile_planner`). NO wiring — `app/knowledge/funnel_state_planner.py` · `tests/test_phase2b_funnel_state_planner.py`.
- [x] 10b.16i **Fase 2C.0c (decisión documentada)** — compatibilidad licencia/unidad (sencillo: B|E; full: E; full+B incompatible/needs_review; la licencia NO infiere unidad, validar solo si existen ambos) + vigencia (license/apto vigentes y >3 meses; ≤3 meses → comprobante renovación; sin fecha → no inferir). Implementación = validador futuro, NO 2C.1 — spec `multi-intent-pipeline` ("Compatibilidad licencia/unidad y vigencia") + `design.md`.
- [x] **Fase 2C.0d (decisión documentada con diagnóstico read-only de cobertura y muestras reales de vencimiento)** — vigencia >3m = **advisory / NO gate** (datos observados: `expires_at`/`apto_expires_at` = 0 filas; `license.status`=13 con 0 fechas; `apto_status`=26 con solo 1 texto de vencimiento; cobertura casi nula). Compat licencia/unidad **NO se activa**: universo con ambos facts canónicos (`license.type`+`experience.vehicle_type`) = **0** (solo licencia=27, solo unidad=2); `full+B` = aclaración futura, no bloqueo. Parser contextual requiere `last_asked_field`/`current_question_field` estructurado (`last_bot_message` textual = apoyo, no fuente fuerte; assistant=436/user=413 mensajes con timestamp) — `design.md` ("Decisión 2C.0d") + spec `multi-intent-pipeline` (nota 2C.0c). NO código, NO gate, NO 7º campo.
- [ ] FUTURO **validador compatibilidad/vigencia** — matriz licencia/unidad (full+B incompatible) + política de vigencia (>3 meses; ≤3 meses → comprobante; vencido+trámite → aclaración; vencido sin trámite → no continúa; sin fecha → no inferir). **Reusar** `needs_confirmation_fields`+`reason` + label `aclaracion_pendiente`/`falta_*` + status `tramite`; NO inventar estados/labels; NO revivir `revisar_licencia`/`*_por_vencer`. NO en 2C.1.
- [ ] DEUDA copy: `app/persona_config.py` "más de 6 meses de vigencia" → actualizar a ">3 meses" (regla oficial 2C.0c). Fase aparte.
- [x] DEUDA (post-diagnóstico 2C.0b): **RESUELTA** — eliminada la cadena legacy de disponibilidad
  (`documents.availability_claim` → `availability_to_attend_candidate`): borrado el writer en
  `app/lead_memory/profile_extractor.py`, quitada la **regla E** (group/key/state) de
  `db/010_v_rh_lead_facts_canonical.sql` y las 2 líneas de display en `db/007`. Las filas viejas de
  `availability_claim` caen al ELSE (`state='ok'`, no-núcleo → ignoradas por el planner). El nombre
  de disponibilidad **vivo** `candidate.availability_status` se conserva (lo usa
  `calculate_candidate_labels`) y el pipeline multi-intent se asimiló a él. Guards intactos
  (`test_phase2b::test_availability_is_ignored_by_profile_planner`, `test_candidate_labels` de
  `disponible_acudir`). **DEPLOY manual requerido en `hrdb`** (las vistas no se auto-aplican):
  `psql $DATABASE_URL -f db/010_v_rh_lead_facts_canonical.sql` y `-f db/007_lead_profile_display_and_stages.sql`.
- [ ] FUTURO **call_scheduling/callback** — concepto nuevo: label operativa `llamada_pendiente` (= contactar por llamada; NO "acudir"; NO sustituye availability_to_attend; fuera del profile planner). Facts futuros opcionales `scheduling.call_window`/`scheduling.call_status=pending`. `llamada_pendiente` ya existe en el catálogo oficial (`chatwoot-label-taxonomy`, 24 activas); el planner/handoff todavía NO la emite hasta implementar esta fase. `disponible_acudir` queda legacy/diferido (10a.6/10b.12). **CONTRATO FIJADO (negocio, 2026-06-12)**: disparador = núcleo completo + documentos confirmados por el candidato → bot: "Para avanzar en su proceso, suba fotos de los documentos que nos confirmó. ¿Gusta que le agendemos una llamada?" (+ foráneo: "...y validamos su traslado a Torreón para continuar con su proceso") → emite `llamada_pendiente` para que el agente llame dentro de horario (8:00–17:30). Depende del acuse de documentos del media guard (ver sección 14).
- [ ] 10b.16h **Fase 2C.2** — surfacing por label del backlog (`falta_unidad`/`aclaracion_pendiente`) vía label_planner (cuando exista). Diagnóstico manual de las 5 filas quinta_rueda (no migración).
- [x] 10b.16d **(doc-only)** Límite explícito 2B.1 documentado — `design.md` ("Límites explícitos de Fase 2B.1") + spec `multi-intent-pipeline` (escenarios "Límite — …"). Reglas fijadas: (1) `license.type` = categoría B/E/…, NO vigencia; (2) `license.status` (vigente/vencida/tramite) por sí solo NO valida la regla >3 meses; (3) `medical.apto_status` (vigente/vencido/tramite) por sí solo NO valida la regla >3 meses; (4) vigencia suficiente requiere fecha/texto de vencimiento interpretable + regla oficial >3 meses; (5) sin fecha clara → NO inferir vigencia suficiente; (6) es **contrato del validador futuro**, NO se implementa aquí (el planner usa el valor del fact tal cual; sin umbrales temporales).

## 10c. Nota privada simplificada + taxonomía de labels (pendiente)

- [x] 10c.1 Confirmar que la nota actual incluye pago/temperatura/labels — `app/chatwoot_note_sync.py` · `render_candidate_note` · grep. Nota: las líneas originales (`:345,351,355`) pertenecen al código previo a N2 de `chatwoot-ai-note-contract`; la referencia estable es `render_candidate_note`.
- [ ] 10c.2 Documentar catálogo oficial de labels (baseline) — `openspec/specs/chatwoot-label-taxonomy/spec.md` (hecho como spec; falta validar contra labels reales de Chatwoot)
- [ ] 10c.3 Quitar de la nota: `Interés en pago/compensación`, `🌡️ Temperatura`, `🏷️ Labels` — `app/chatwoot_note_sync.py` · `render_candidate_note`. SUPERSEDIDO por el change `chatwoot-ai-note-contract`: Temperatura ya eliminada en F26; pago, labels, disponibilidad y memoria narrativa pendientes de cierre mediante N2 (targeted del renderer, pruebas relacionadas, suite absoluta, OpenSpec strict y commit aislado).
- [ ] 10c.4 Formato objetivo de la nota SUPERSEDIDO por `chatwoot-ai-note-contract`: Último mensaje → Contacto → Perfil confirmado → Pendientes o conflictos (condicional) → Embudo → Siguiente acción (única). Sin `Acción` en cabecera, sin `Memoria breve`, sin `Perfil detectado`, sin `Disponibilidad para acudir`. Criterio de cierre: targeted del renderer, pruebas relacionadas, suite absoluta, OpenSpec strict y commit aislado.
- [ ] 10c.5 Implementar `private_note_builder` (corre después de `label_planner`; recibe facts/stage/missing/completed/conflicts/risk/requires_human/next_action ya calculados; no decide labels ni facts; LLM solo para tono con contrato cerrado)
- [ ] 10c.6 `Acción` y `Siguiente acción` desde el planner determinista (no LLM)
- [ ] 10c.7 Mapear campos del perfil a Pendiente/Requiere aclaración según estado en Postgres
- [ ] 10c.8 Verificar contra labels reales de Chatwoot (catálogo oficial de 24 labels activas) y exclusividades (`local_laguna`/`foraneo`; `objetivo_full_sencillo`/`cecati`/`escuelita`)
- [ ] 10c.9 Auditoría: evento de nota (`lead_id`, `conversation_id`, `note_version`, `facts_snapshot`, `missing_fields`, `completed_fields`, `conflicts`, `next_action`, `source_event_id`, `generated_at`)
- [ ] 10c.10 Auditoría: evento de label sync (`lead_id`, `conversation_id`, `labels_before/after`, `labels_to_add/remove`, `reason`, `facts_source`, `event_id`)

## 11. Reposicionamiento de Neo4j (pendiente)

- [ ] 11.1 Modelar nodos Intent/Policy/InternalSource en Neo4j
- [ ] 11.2 Migrar `INTENT_POLICIES` a Neo4j sin cambiar la interfaz de `enrich_classification`
- [ ] 11.3 Verificar `preferred_sources` alineado con el metadata `source` de Chroma

## 12. Cutover (pendiente, behind flag)

> PRIORIDAD ALTA (decisión 2026-06-12): acelerar fases 6-8 + cutover. Los choques
> regex-vs-intent del camino vivo se resuelven aquí (clasificador LLM con catálogo
> cerrado + evidencia literal), NO con más parches al camino vivo — solo bugs
> críticos se parchan mientras tanto. Decisión acompañada de: generación SIEMPRE
> en 70B (el downgrade a 8b fue causa principal de alucinaciones), chunking RAG
> redimensionado (900/150/3200/1400) y observabilidad LLM (ver FUTURO Langfuse).

- [ ] 12.1 Definir el flag de cutover y el punto de delegación en `handle_message`
- [ ] 12.2 Resolver Open Questions del design (coexistencia con `profile_extractor`; emisión de labels; persistencia de auditoría)
- [ ] 12.3 Definir el mapeo `field → label` de Chatwoot (documento del Paso 2)
- [ ] 12.4 Activar cutover en staging; validar paridad con baseline y rollback por flag
- [ ] 12.5 Actualizar `CONTEXTO.md` y la spec `message-orchestration` tras el cutover

- [ ] FUTURO **observabilidad LLM (Langfuse self-hosted)** — decisión 2026-06-12:
  contenedor en compose + SDK mínimo en `call_llm`: traza por turno de modelo,
  prompt, contexto recuperado (fuentes y chars), respuesta y latencia. Objetivo:
  auditar alucinaciones/truncamientos sin cazar logs (el downgrade a 8b y el
  contexto cortado habrían sido visibles en dashboard). Change OpenSpec aparte.

## 13. Auditoría de regex/if de negocio (REPORTE primero — no tocar código)

> Reporte completo: `audit-regex-if.md` (read-only, 2026-06-04). Detectó ~17 RN, ~6 PD,
> ~4 PL, ~8 NT/ES, 2 EL y 5 contradicciones código↔spec.

- [x] 13.1 Auditar `app/orchestrators/knowledge_orchestrator.py` — `audit-regex-if.md` §2 (overrides deterministas: greeting/farewell/time/ack/call → RN)
- [x] 13.2 Auditar `app/lead_memory/profile_extractor.py` — `audit-regex-if.md` §1 (foco RN; contradicción `quinta_rueda` línea 211)
- [x] 13.3 Auditar `app/knowledge/intent_enricher.py` — `audit-regex-if.md` §4 (`INTENT_POLICIES` PD; `pay_question` contradice spec)
- [x] 13.4 Auditar `app/knowledge/intent_orchestrator.py` — `audit-regex-if.md` §5 (`FUNNEL_STEPS`/`plan_and_respond` = patrón objetivo)
- [x] 13.5 Auditar `app/chatwoot_note_sync.py` — `audit-regex-if.md` §3 (`_temperatura` EL; `_stage` PD)
- [x] 13.6 Clasificar hallazgos (NT/ES/RN/PD/PL/EL) — `audit-regex-if.md` (tablas por archivo + resumen)
- [x] 13.7 Producir el reporte priorizando RN dispersas — `audit-regex-if.md` (resumen + orden recomendado + 5 contradicciones)

## 14. Media guard (G4) — implementación viva (hecho)

- [x] **G4 media_guard vivo** — corte a nivel del webhook de Chatwoot (`app/app.py` · `chatwoot_webhook` + `_chatwoot_has_media`), **agnóstico al canal** (Telegram demo / WhatsApp futuro, ambos vía Chatwoot). Si el evento entrante trae `attachments` (top-level o `message.attachments`): responde texto canned, log `[CHATWOOT_MEDIA_GUARD]`, return temprano **antes** de `empty_content`/encolar/orquestador; NO extractor, NO encolar, NO `run_hr_graph_message`, NO facts, NO labels, NO `profile_ready`. Caption bloqueado en v1 (no se parsea como fact). Sin OCR/document-understanding. Spec (doc-only): `multi-intent-pipeline` ("Manejo de media sin OCR/document-understanding") + `message-orchestration` ("Respuesta conversacional ante media sin OCR") + `design.md` (Non-Goal). Tests: `tests/test_chatwoot_media_guard.py` (suite `56 passed`) + smoke test vivo (imagen/sticker/audio/documento/imagen+caption, 200 OK). Commits `018b5e5` (código+tests) · `6c35043` (CONTEXTO.md). NO tocó `knowledge_orchestrator`/`profile_extractor`/`funnel_state_planner`/labels/BD.
- [ ] FUTURO **evento `media_blocked`** — persistir en `rh_lead_events_v2` un evento mínimo
  (lead_id, conversation_id, tipo de attachment, timestamp) cuando G4 corta multimedia.
  El evento documenta únicamente "llegó multimedia y no fue procesada porque no hay OCR":
  NO produce facts (`license.type`/`medical.apto_status`/`experience.years`), NO afirma qué
  contiene el archivo, NO OCR. Motivo: el análisis de embudo debe ver al candidato que
  intentó entregar un documento y fue redirigido a texto (hoy solo queda en el log
  `[CHATWOOT_MEDIA_GUARD]`, invisible para el record). Change OpenSpec aparte; NO en media v1.
- [ ] FUTURO **acuse de documentos esperados** (decisión negocio 2026-06-12): cuando el
  bot pidió documentos (flujo call_scheduling) y llega un attachment, el guard responde
  acuse — "Recibimos sus documentos, nuestro equipo los revisa y le confirma el siguiente
  paso" — en lugar del canned de rechazo, marca el lead para revisión humana (evento
  media + label) y sigue SIN OCR/facts. El canned de rechazo queda solo para multimedia
  NO esperada (stickers, audios, imágenes fuera de flujo). Resuelve el conflicto
  "pedimos fotos pero G4 las rebota".
- [ ] FUTURO **media v2** — captions explícitos y/o capa OCR/document-understanding validada (solo entonces la media podría producir facts). NO ahora.
