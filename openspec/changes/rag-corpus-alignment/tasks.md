# Tasks: rag-corpus-alignment

> Solo contenido y copy. Cambios de comportamiento (gate perfil_listo por
> residencia/cartas, vigencia <3 meses bloqueante, pregunta documental
> condicionada, parseo de fechas) van en changes separados con tests rojos.

## Fase 1 — Corpus data/

- [x] K1.1 `00_politicas_generales.md`: propósito = operadores de tracto full o
  sencillo (quinta rueda solo jerga); flujo de precalificación único (ciudad →
  unidad → licencia → apto → años → documento laboral por residencia → edad; RFC
  a expediente); regla de fallback telefónico restringido; apertura sugerida.
- [x] K1.2 `01_pago_prestaciones.md`: respuestas sugeridas no repreguntan ciudad
  conocida; regla explícita de usar referencias documentadas antes del teléfono.
- [x] K1.3 `02_documentos_requisitos.md`: vigencia >3 meses (6 lugares);
  documento laboral por residencia; precalificación sin RFC y con pregunta de
  unidad full/sencillo; CECATI enseña a manejar tractocamión (no "quinta rueda").
- [x] K1.4 `04_bases_rutas.md`: boleto/hospedaje condicionados a foráneo; regla
  para locales ZM Laguna (solo información de patios/proceso).
- [x] K1.5 `05_jerga_rcontrol.md`: "quinta rueda" redefinida como jerga del
  oficio/tractocamión que exige confirmar full o sencillo; nunca tipo de unidad.

## Fase 2 — Copy de código (sin lógica nueva)

- [x] K2.1 `app/orchestrators/knowledge_orchestrator.py` · `GREETING_REPLY` →
  "vacante de operador de tracto full o sencillo".
- [x] K2.2 `app/knowledge/intent_orchestrator.py` · `_SIGNAL_REPLIES["greeting"]`
  → mismo vocabulario.
- [x] K2.3 `app/followup/templates.py` · plantilla "new" → mismo vocabulario.
- [x] K2.4 `app/persona_config.py`: vigencia >3 meses; requisitos sin RFC inicial
  y con documento laboral por residencia (resuelve la DEUDA copy de
  multi-intent-migration).
- [x] K2.5 `app/knowledge/current_turn.py` · `build_current_turn_ack`: el ack de
  vehículo solo afirma "tracto full" con `vt == "full"` (elimina el mapeo
  quinta_rueda→full).
- [x] K2.6 `app/knowledge/neo4j_seed_hr_rules.cypher`: `static_greeting` con
  vocabulario canónico; nodo `fifth_wheel_full` separado — `full` sin aliases de
  jerga; `quinta rueda`/`quinta`/`tracto`/`tractocamión` en nodo
  `fifth_wheel_jargon` que no fija unidad.
- [x] K2.7 Seed Neo4j: Term legacy `escuelita` (vivía solo en el grafo, no en el
  seed) incorporado al archivo con aliases limpios — la familia quinta rueda
  (`quinta rueda`/`quinta`/`5ta rueda`/`kinta rueda`/`op 5ta`) removida de
  escuelita y movida a `fifth_wheel_jargon`; Intent `driving_school` formalizado
  en el seed. Hallazgo del smoke de re-seed 2026-06-12: "manejo quinta rueda"
  podía matchear escuelita → pitch de curso a un trailero con experiencia.

## Fase 3 — Verificación y despliegue

- [x] K3.1 `python -m py_compile` de los módulos tocados + `git diff --check` — OK (2026-06-12).
- [x] K3.2 Suite Docker completa sin regresión — 461 passed / 8 warnings (2026-06-12).
- [x] K3.3 `openspec validate rag-corpus-alignment --strict` — valid (2026-06-12).
- [x] K3.4 Chroma reindexado con el corpus nuevo — `POST /reindex`: 6 files / 87 chunks / colección `rh_rag_docs_bge_m3` (2026-06-12).
- [x] K3.5 Re-seed de Neo4j aplicado y verificado — query de aliases familia quinta rueda devuelve SOLO `fifth_wheel_jargon`; `escuelita` limpia (2026-06-12).
- [ ] K3.6 Smoke en canal demo: saludo, "manejo quinta rueda", requisitos, pago
  con ciudad conocida, boleto (local vs foráneo).

## Fuera de este change (próximos, con tests rojos primero)

- [ ] Gate `perfil_listo`: documento laboral confirmado según residencia
  (foráneo: cartas; local: cartas o IMSS) — decisión de negocio 2026-06-11.
- [ ] Vigencia <3 meses **bloquea** `perfil_listo` + `aclaracion_pendiente` +
  comprobante de renovación (endurece 2C.0d; requiere parseo de fechas).
- [ ] Edad como pregunta del funnel; RFC a expediente (planner).
- [ ] `is_local_laguna` solo con ciudad en el turno (`current_turn.py`).
- [ ] Renderer: `has_vehicle_type` con `VALID_VEHICLE_TYPES` (blocker/⚠️
  consistentes con `falta_unidad`).
- [ ] Rastreo del escritor LLM que persistió `vehicle_type=quinta_rueda` en vivo
  (verificar si el corpus/seed era la única fuente o hay normalización faltante
  en el grafo).
- [ ] Contenido nuevo de rutas/tabuladores (vuelta diaria Torreón–Nuevo Laredo,
  tabulador sur/bocar) — pendiente de información oficial de negocio.
