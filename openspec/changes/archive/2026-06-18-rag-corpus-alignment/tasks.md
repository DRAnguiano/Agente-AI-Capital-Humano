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
- [~] K3.6 Smoke en canal demo (conv. 81, 2026-06-12): saludo ✓ ("tracto full o
  sencillo"); pago con cifras documentadas ✓ (Bajío/Bocar/Clarios, sin fallback
  telefónico). Falló: `vehicle_type=quinta_rueda` persistido otra vez → causa
  raíz K2.8; pregunta de ruta ignorada/derivada (faltaba contenido → K1.6);
  ciudad glotona (regex, fuera de este change). Re-smoke pendiente tras K3.7.

## Fase 4 — Hallazgos del smoke 81 (mismo change)

- [x] K1.6 Contenido de rutas/modo de trabajo en `04_bases_rutas.md` (decisiones
  de negocio 2026-06-12): zona del corredor para RUTAS = Monterrey, Nuevo
  Laredo/Laredo, Torreón y ZM de La Laguna (Durango y Coahuila) → rutas
  habituales del corredor Torreón ↔ Monterrey ↔ Nuevo Laredo ida y vuelta, con
  pedidos ocasionales al sur (cajas/pedidos de clientes, referencia Bocar
  $2.90/km). Fuera de esas ciudades → prioridad Bocar y Clarios sobre la ruta
  del Bajío (mencionando igualmente las rutas habituales). Misma respuesta para
  todas las vacantes. NOTA: esta clasificación de zona para rutas es DISTINTA a
  la de apoyo de traslado/boleto (local = solo ZM Laguna). Jerga
  tramo/corrida/vuelta/salida documentada en `05` y `01`.
- [x] K2.8 **Causa raíz del quinta_rueda persistido**: nodo
  `VehicleType vehicle_quinta_rueda` en `db/neo4j_seed_geo_vehicle.cypher`
  escribía `experience.vehicle_type=quinta_rueda` vía
  `extract_profile_facts_from_neo4j` (knowledge_orchestrator:712-735),
  brincándose `normalize_vehicle` y suprimiendo el manejo limpio de
  `profile_extractor` por el dedup. Nodo eliminado del seed + `DETACH DELETE`
  autocurativo al re-correrlo.
- [ ] K3.7 Re-aplicar `db/neo4j_seed_geo_vehicle.cypher` + reindexar Chroma +
  re-smoke (quinta rueda NO debe fijar unidad; pregunta de rutas debe responder
  con el corredor).
- [x] K2.9 Humor ligero determinista (decisión 2026-06-12, smoke 13:34): Term
  `smalltalk_joke` + ReplyTemplate `static_joke` en el seed hr_rules — chiste
  benigno responde una línea simpática y el nudge agrega la siguiente pregunta
  del funnel; guía de humor/small talk en `05_jerga_rcontrol.md` (sin humor en
  temas sensibles). Evita el misfire "te digo que licencia tengo" → listado de
  documentos. Requiere re-seed + reindex.
- [x] K2.10 Humor LLM con barda (decisión 2026-06-12, "el mismo chiste dos
  veces"): la detección sigue determinista (Term), pero la respuesta la genera
  el LLM con `_JOKE_PROMPT` (blanco, 2 frases, sin temas vetados); validación
  de longitud + lista de vetados sobre texto normalizado; el template del seed
  queda como FALLBACK ante error/vacío/violación; puente al funnel fijo en
  código (`_JOKE_BRIDGE`). 7 tests con monkeypatch de call_llm.

## Fuera de este change — bugs de código detectados en smoke 81 (tests rojos primero)

- [x] Regex de ciudad glotona en `profile_extractor`: RESUELTO por
  `live-first-contact-and-fact-guards` G2.4 (`_extract_city`: split en
  conectores/interrogativos + tope de 4 tokens). La desambiguación "laredo solo"
  (TX vs NLD) se atiende aparte en `live-business-rule-enforcement`
  (`detect_laredo_ambiguity` + handoff Laredo Texas).
- [ ] Pregunta tomada como respuesta: el turno con "?" se procesó como respuesta
  de ciudad y la pregunta de rutas se ignoró tres veces (ack "Laredo, anotado" +
  pregunta de licencia). `should_prioritize_current_turn` ya excluye preguntas —
  rastrear por qué el camino vivo no respetó `is_question`.
- [x] Extractor geo de Neo4j extrae ciudad desde PREGUNTAS: RESUELTO por
  `live-first-contact-and-fact-guards` G2.3 (`_drop_geo_facts_from_questions` +
  `_drop_unanchored_neo4j_geo` en knowledge_orchestrator: pregunta sin marcador
  de residencia → sin `candidate.city/state`, aplicado a facts de Neo4j+regex).
- [x] Mensaje de campaña FB "Me interesa la vacante de operador de quinta rueda"
  como APERTURA: RESUELTO por `live-first-contact-and-fact-guards` G2.1/G2.2
  (`is_campaign_or_interest_entry` + `GREETING_REPLY` en primer contacto, sin
  acuse "lo dejo registrado" ni fijar unidad).
- [ ] Fallback de horario sigue saliendo sin importar la hora actual ("llámenos
  de 8:00 a 17:30" estando en horario): inyectar hora actual al contrato de
  generación (frente grounding).
- [ ] CONFLICTO media guard vs flujo de documentos — RESUELTO por decisión de
  negocio (2026-06-12): media esperada (tras pedir documentos) → acuse +
  revisión humana sin OCR; canned de rechazo solo para multimedia no esperada.
  Contrato registrado en multi-intent-migration (sección 14, "acuse de
  documentos esperados") y flujo de llamada en FUTURO call_scheduling.
  Implementación pendiente con tests rojos.
- [x] Copy: respuestas con comillas literales ("Laredo, anotado."): `_clean_reply`
  quita un nivel de comillas envolventes (`_strip_wrapping_quotes`: `"`, `“”`, `«»`, `'`)
  sin tocar comillas internas ni apóstrofes. Tests en `test_friendly_grounding.py`.
- [x] Prefijo "Nuestro equipo valida el avance." — causa raíz: el LLM parroteaba
  el `public_guidance` de la Policy `no_hiring_promise` (seed hr_rules:135).
  Guidance reformulada como regla interna explícita "NO copiar esta frase"
  (2026-06-12; requiere re-seed).
- [x] Machaca en "¿cuánto paga esa ruta?" — causa raíz: intent de pago filtra
  retrieval a `01_pago_prestaciones.md` y el pago del corredor vivía solo en
  `04_bases_rutas.md`. Pago del corredor cross-listado en `01` con respuesta
  sugerida propia (2026-06-12; requiere reindex).
- [x] BUG LATENTE filtros RAG (RESUELTO 2026-06-18): cada `InternalSource` rag_document del
  seed ahora declara `filename` = `data/*.md` real (`payment_policy`→`01_pago_prestaciones.md`,
  etc.) y `neo4j_client` devuelve `collect(DISTINCT coalesce(s.filename, s.id))` →
  `preferred_sources` casa con el `source` (= filename) que filtra `_source_where`. Ya no
  depende de nodos legacy del grafo vivo; un grafo reconstruido desde el seed mantiene los
  filtros RAG. Test estático `tests/test_rag_source_alignment.py` (3, seed↔data, sin DB/Chroma).
  Se conserva el `id` de política para las referencias internas (ReplyTemplate/Topic).
- [ ] Grounding ante contexto vacío en preguntas de ruta: "Laredo es una ciudad
  importante en el norte de México" pasó el guard de grounding (smoke 10:06).
  Conectar con el change `live-reply-grounding-and-quality`.

## Fuera de este change (próximos, con tests rojos primero)

- [ ] Gate `perfil_listo`: documento laboral confirmado según residencia
  (foráneo: cartas; local: cartas o IMSS) — decisión de negocio 2026-06-11.
- [ ] Vigencia <3 meses **bloquea** `perfil_listo` + `aclaracion_pendiente` +
  comprobante de renovación (endurece 2C.0d; requiere parseo de fechas).
- [ ] Edad como pregunta del funnel; RFC a expediente (planner).
- [x] `is_local_laguna` solo con ciudad en el turno: hecho en
  `current_turn.extract_current_turn_facts` — `city_norm` sale de `candidate.city`
  del turno y queda vacío (False) si no hay ciudad; se excluye de la señal de perfil.
- [x] Renderer: `has_vehicle_type` con `VALID_VEHICLE_TYPES`: hecho en
  `chatwoot_note_sync.py` (`vehicle_confirmed = experience.vehicle_type in
  VALID_VEHICLE_TYPES`; jerga ambigua "quinta rueda"/"tráiler" no confirma unidad).
- [ ] Rastreo del escritor LLM que persistió `vehicle_type=quinta_rueda` en vivo
  (verificar si el corpus/seed era la única fuente o hay normalización faltante
  en el grafo).
- [ ] Contenido nuevo de rutas/tabuladores (vuelta diaria Torreón–Nuevo Laredo,
  tabulador sur/bocar) — pendiente de información oficial de negocio.

## Cierre para portafolio (2026-06-18)

Corpus, copy, seed limpio y reindex implementados (461 passed en su día; 710 passed hoy). El
**bug latente de filtros RAG** (ids InternalSource ≠ filename) quedó **resuelto** con test
estático. Las 10 tasks abiertas restantes son: deploy/live (K3.7 re-seed+reindex+smoke — moot por
bot caído / pivot a Meta), **diferidas a changes separados** (pregunta-como-respuesta, fallback
horario, media-guard, gate perfil_listo, vigencia <3m, edad funnel/RFC), **stale** (rastreo
quinta_rueda — causa raíz ya en K2.8) o **bloqueadas en info de negocio** (tabuladores nuevos).
Fuera de alcance. Archivado por portafolio.
