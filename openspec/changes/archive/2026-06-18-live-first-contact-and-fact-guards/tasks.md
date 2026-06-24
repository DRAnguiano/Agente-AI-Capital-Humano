# Tasks: live-first-contact-and-fact-guards

## Fase 1 — Tests primero (RED)

- [x] G1.1 `tests/test_first_contact_and_fact_guards.py`: 18 tests (entrada de
  campaña, interés-no-señal, geo desde preguntas, ciudad acotada).
- [x] G1.2 Implementación entregada junto con los tests (RED verificable con
  `git stash` de los 4 módulos de app si se requiere evidencia roja formal).

## Fase 2 — Implementación (GREEN)

- [x] G2.1 `current_turn.py`: `is_campaign_or_interest_entry` (interés/campaña,
  no-pregunta) + `_NON_PROFILE_SIGNAL_KEYS` excluye `candidate.vacancy_accepted`
  de `has_current_turn_profile_signal`.
- [x] G2.2 `tasks_chatwoot.py`: primer contacto (sin `last_bot_message`) con
  entrada de campaña/interés → `GREETING_REPLY` + log
  `[FIRST_CONTACT_GREETING_APPLIED]`; el guard no aplica en ese turno.
- [x] G2.3 `knowledge_orchestrator.py`: `_drop_geo_facts_from_questions`
  (pregunta sin marcador de residencia → sin candidate.city/state) aplicado a
  los facts de Neo4j+regex antes de persistir.
- [x] G2.4 `profile_extractor.py` · `_extract_city`: stops ampliados
  (ahí/a/donde/que/para/pero/...) + tope de 4 tokens.

## Fase 2b — Hallazgos del smoke 12:12 (typos/jerga + intro), decisión "hazlo así"

- [x] G2.5 `text_normalizer.py`: canonicalización de typos/jerga inequívocos en
  el punto único de normalización — `_TYPO_CANON`
  (licensia/lisencia→licencia, vijente/bijente→vigente, palasio→palacio,
  sensillo→sencillo, voleto→boleto) + `_PHRASE_CANON` ("soy d "→"soy de ").
  "d" suelta NO se sustituye (tipo D es categoría de licencia válida).
- [x] G2.6 `_extract_city`: el regex de residencia opera sobre texto
  normalizado (las sustituciones aplican al marcador y al nombre capturado).
- [x] G2.7 Intro de primera respuesta: `_maybe_prepend_first_reply_intro`
  dependía del evento `conversation_memory_built` que NADIE emite (nunca
  funcionó). Ahora recibe `is_first_reply` explícito desde el task
  (`last_bot_message is None`); fallback legacy conservado.
- [x] G2.8 Tests añadidos: typo-canonicalización (incl. el compuesto jergoso
  real del smoke 12:15) + intro de primera respuesta (28 tests en total en el
  archivo).
- [x] G2.9 Corpus: respuesta oficial "NO se firma pagaré en blanco" en
  `02_documentos_requisitos.md`; jerga "tirar/pa onde tiran" como pregunta de
  ruta en `05_jerga_rcontrol.md` (requiere reindex).

## Fase 3 — Verificación

- [x] G3.1 Suite completa en Docker: 503 passed / 8 warnings (2026-06-12);
  targeted previo 59 passed.
- [x] G3.2 `openspec validate live-first-contact-and-fact-guards --strict` — valid.
- [~] G3.3 Comportamientos del smoke **cubiertos por tests deterministas**
  (`test_first_contact_and_fact_guards.py`, 2026-06-17, dentro de los 598 passed):
  entrada de campaña FB → saludo oficial (`test_saludo_oficial_menciona_full_o_sencillo`,
  `test_helper_detecta_entrada_fb`); pregunta de rutas → sin `candidate.city`
  (`test_pregunta_de_rutas_no_fija_ciudad`); "soy de Laredo ahí de donde..." → ciudad acotada.
  Falta solo la confirmación en el **stack vivo** (demo) — acción del operador.
- [x] G3.4 Código ya en main (árbol limpio); commit autorizado al cierre para portafolio
  (2026-06-18). La confirmación en stack vivo (G3.3) queda N/A: bot caído / pivot a Meta.
