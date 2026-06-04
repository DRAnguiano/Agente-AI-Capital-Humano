## Context

El sistema en producción usa `knowledge_orchestrator.handle_message` para todo: routing
vía Neo4j, guardas deterministas, generación (RAG / LLM amistoso / plantilla), extracción
de facts y persistencia. La lógica del funnel está triplicada (`_FUNNEL_STEPS`,
`next_question_from_missing_facts`, `SYSTEM_PROMPT`). Los mensajes reales de WhatsApp son
frecuentemente compuestos (respuesta + pregunta en un mismo turno), y separarlos de forma
confiable dentro del monolito es difícil. Además, hoy el bot repite preguntas ya
respondidas, no distingue una corrección de un dato nuevo y guarda respuestas cortas
ambiguas fuera de contexto.

`docs/esquema_perfilamiento_v1.md` (acordado 2026-06-03) define la fuente única de
verdad: 6 preguntas núcleo, reglas de validación licencia↔unidad, estados especiales,
status por completitud, mapeo a labels de Chatwoot, y el contrato de intención
multi-intent (§8). Este change implementa ese esquema como pipeline y lo extiende con
memoria conversacional, estado del funnel, corrección/contradicción de facts y
desambiguación de respuestas cortas.

## Goals / Non-Goals

**Goals:**
- Separar la clasificación del lenguaje (LLM) de las políticas de negocio (deterministas).
- Detectar y manejar mensajes compuestos: persistir el answer en silencio y priorizar
  contestar la pregunta.
- Guardrail anti-alucinación: un answer se persiste como `confirmed` solo si su `evidence`
  aparece literal en el mensaje y `confidence ≥ 0.85`.
- Nunca repetir una pregunta ya respondida con evidence válido (memory guard).
- Distinguir dato nuevo / incompleto / corrección / contradicción / respuesta elíptica, y
  no sobrescribir por contradicción sin confirmación.
- Que el sistema (no el LLM) calcule la siguiente pregunta del funnel; el LLM solo redacta.
- Auditar cada turno (facts antes/después, correcciones, pendientes de confirmación).
- Validar contra tráfico real en shadow antes de activar, con cero riesgo para el candidato.

**Non-Goals:**
- No se cambia el contrato HTTP externo (`/chatwoot/webhook`, `/orchestrate/message`).
- No se elimina todavía el `knowledge_orchestrator`; el cutover es un paso posterior.
- No se migra aún `INTENT_POLICIES` a Neo4j (queda como deuda explícita).

## Pipeline (orden de etapas)

```
normalize_text                 # normalización textual básica (no negocio)
  → classify                   # LLM 8b → JSON multi-intent (lenguaje, no políticas)
  → resolve_concepts           # catálogo/grafo: alias → conceptos (licencia, unidad, etc.)
  → validate_evidence          # evidence literal + umbral de confianza
  → read/write state (Postgres)# leer estado; escribir facts si procede
  → normalize_domain_values    # full/sencillo/licencia/apto/...; quinta rueda/tráiler → needs_clarification
  → disambiguate_numeric_units # 10/3/27/2028 según last_bot_question; sin contexto → aclarar
  → contextual_answer_classifier # sí/no/elípticas con intención + last_bot_question (sin regex global)
  → detect_fact_corrections    # dato nuevo | incompleto | corrección | contradicción
  → resolve_fact_conflicts     # contradicción sin confirmación → needs_confirmation (no sobrescribe)
  → compute missing/completed/forbidden  # desde Postgres
  → funnel_state_planner       # next_question, completed/missing/forbidden, facts_before/after
  → label_planner              # labels_to_add/remove desde Postgres (consume v_rh_work_queue)
  → private_note_builder       # nota simplificada desde estado calculado (DESPUÉS de label_planner)
  → response_planner           # contrato cerrado de respuesta (orden de acciones + texto base)
  → LLM solo redacta           # 70B redacta cordialmente; nunca elige campo/label/pregunta
  → final_validator            # verifica que la respuesta no contradiga el estado/contrato
  → persist + chatwoot_sync + audit  # Postgres → publica nota + sincroniza labels → auditoría
```

> Nota: `normalize_domain_values`, `disambiguate_numeric_units` y
> `contextual_answer_classifier` son etapas **separadas** (no una sola `disambiguate_units`):
> no se mezclan valores claros del dominio, números ambiguos y respuestas sí/no.

### `private_note_builder` (contrato)

- Corre **después de** `label_planner` y recibe ya calculados: facts (confirmados y
  pendientes), `stage`, `missing_fields`, `completed_fields`, `conflicts`, `risk_level`,
  `requires_human` y `next_action`.
- NO decide labels. NO decide facts. NO llama al LLM para generar contenido factual.
- Si usa LLM para tono, recibe un **contrato cerrado** y no puede cambiar valores, campos,
  etapa ni siguiente acción.
- Produce la **nota simplificada** (sin `Temperatura`, sin `Interés en pago/compensación`,
  sin lista de `Labels`).
- `chatwoot_sync` publica la nota privada y sincroniza labels desde el resultado del planner.

## Data layer (verificado en `hr_postgres` / `hrdb`)

Postgres es la **fuente de verdad operativa**; Chatwoot es display/canal. Tablas y vista
verificadas (existen hoy):

| Objeto | Tipo | Rol |
|---|---|---|
| `rh_leads_v2` | tabla | 1 fila/lead: `lead_status`, `funnel_stage`, `next_best_action`, `facts_summary`, `risk_level`, `requires_human` |
| `rh_lead_facts_v2` | tabla | facts key-value: `fact_group`/`fact_key`/`fact_value`(+`_json`), `confidence`, `source`, `source_text` (evidencia), `is_active` |
| `rh_lead_messages_v2` | tabla | log crudo de mensajes |
| `rh_lead_events_v2` | tabla | eventos de ciclo de vida + `metadata jsonb` (vehículo de auditoría hoy) |
| `rh_seguimiento_tareas` | tabla | tareas de seguimiento (Celery Beat) |
| `v_rh_work_queue` | vista | deriva desde facts: `suggested_chatwoot_labels`, `is_profile_ready`, `perfil_status`, `is_local_laguna`, `is_foraneo_mx`, flags de validación de ubicación, faltantes |

**Hallazgo clave:** `v_rh_work_queue.suggested_chatwoot_labels` e `is_profile_ready` **ya
derivan labels y "perfil listo" desde Postgres de forma determinista**. El
`candidate-profile-label-planner` y `chatwoot_sync` deberían **consumir esta vista** como
base, no reinventar la lógica.

**Gaps verificados:**
- `rh_lead_facts_v2` NO tiene columna de **estado de fact** (`confirmed`/`needs_confirmation`/
  `conflict`/`corrected`/`inferred_from_context`). Hay `confidence` + `source_text` +
  `is_active`, pero los estados del pipeline requieren una columna nueva o una tabla aparte.
- No hay tabla dedicada de **auditoría de sincronización de labels**; hoy cabría en
  `rh_lead_events_v2.metadata`. Decidir si se formaliza una tabla propia.
- Inconsistencia de naming a reconciliar: el contrato multi-intent usa `license.type`
  mientras Postgres usa `license.category`; el funnel usa `documents.proof` mientras
  Postgres tiene `documents.labor_letters_status`/`documents.general_status`.

## Mapa canónico de nombres de facts

**Decisión (fijada 2026-06):** el nombre canónico se define **por campo** (tabla abajo) y
es el que escribe el pipeline. Postgres es la fuente de verdad operativa, pero donde la
clave actual de Postgres diverge del canónico elegido, **se migra Postgres** al nombre
canónico (no se mantiene un alias permanente). El clasificador y la nota privada usan el
nombre canónico.

Origen de la columna "Postgres hoy": verificado en `rh_lead_facts_v2` (facts activos
reales, 2026-06). "Vista": columna en `v_rh_work_queue`. "Clasificador": `ANSWER_FIELDS`
en `intent_classifier.py`.

### Campos núcleo (funnel)

| Campo lógico | **Canónico (fijado)** | Postgres hoy | Clasificador | Columna `v_rh_work_queue` | Labels | Valores canónicos |
|---|---|---|---|---|---|---|
| Ciudad | `candidate.city` | `candidate.city` ✓ | `candidate.city` ✓ | `ciudad` / `ciudad_raw` | `falta_ciudad`, `local_laguna`/`foraneo`, `validar_traslado` | texto + catálogo |
| Tipo de unidad | `experience.vehicle_type` | `experience.vehicle_type` ✓ | `experience.vehicle_type` ✓ | `experiencia_quinta_rueda` | `falta_unidad`, `objetivo_full_sencillo`/`cecati`/`escuelita` | `full`\|`sencillo`\|`ambos`\|`ninguno` |
| Años experiencia | `experience.years` | `experience.years` ✓ | `experience.years` ✓ | (en experiencia) | `falta_experiencia` | entero |
| Licencia (tipo) | `license.type` | `license.category` → **MIGRAR** | `license.type` ✓ | `tipo_licencia` | `falta_licencia` | `B`\|`E`\|`A`\|`C` |
| Licencia (estado) | `license.status` | `license.status` ✓ | `license.status` ✓ | `licencia_federal` | `falta_licencia` | `vigente`\|`vencida`\|`tramite` |
| Apto médico | `medical.apto_status` | `medical.apto_status` ✓ | `medical.apto_status` ✓ | `apto_medico` | `falta_apto` | `vigente`\|`vencido`\|`tramite` |
| Documentos/cartas | `documents.proof` | `documents.labor_letters_status` (+4 más) → **MIGRAR/CONSOLIDAR** | `documents.proof` ✓ | — | `documentos`, falta cartas | `cartas`\|`semanas_imss`\|`ninguno` |
| Disponibilidad acudir | `candidate.availability_to_attend` | (no existe) → **CREAR** | `availability` (nuevo) | `disponibilidad_viajar` (≠ acudir) | `disponible_acudir` | fecha/disponibilidad |

Leyenda: ✓ coincide con el canónico · **MIGRAR/CREAR** acción en Postgres requerida.

### Decisiones fijadas

1. **Licencia (tipo): canónico `license.type`.** Migrar la clave de Postgres
   `license.category` → `license.type` (renombrado de `fact_key`, conservando valores).
2. **Documentos: canónico `documents.proof`** con valores `cartas`\|`semanas_imss`\|`ninguno`.
   Migrar/consolidar hacia `documents.proof` las dispersas: `documents.labor_letters_status`,
   `documents.labor_letters`, `documents.general_status`, `documents.submission_status`,
   `documents.availability_claim`.
3. **Disponibilidad para acudir: fact nuevo `candidate.availability_to_attend`** (separado
   de la disponibilidad para viajar foráneo). Label `disponible_acudir`.
4. **`vehicle_type`: valores `full`\|`sencillo`\|`ambos`\|`ninguno`.** `quinta_rueda` NO es
   un valor: es el rol/tractocamión (la vacante). "Sencillo"/"full" describen la
   configuración de remolque. "Quinta rueda"/"tráiler"/"tractocamión" indican experiencia
   **potencialmente compatible** pero dejan `vehicle_type=needs_clarification`; en ese
   estado se aplica `falta_unidad` (+ `aclaracion_pendiente`) y **NO** `objetivo_full_sencillo`.
   `objetivo_full_sencillo` solo se aplica cuando `vehicle_type` se confirma en full o sencillo.

### Claves legacy/duplicadas en Postgres (consolidar, no ampliar)

Verificadas presentes y que duplican o quedan fuera del núcleo:
`license.category` (→ migrar a `license.type`), las `documents.*` dispersas (→ migrar a
`documents.proof`), `document.apto_status` (usar `medical.apto_status`),
`experience.fifth_wheel` (usar `experience.vehicle_type`), `experience.carretera_mexicana`,
`candidate.age`, `candidate.availability_status` (≠ `availability_to_attend`),
`candidate.vacancy_accepted` (perfil_listo ya NO lo exige), `interest.payment`
(se quita de la nota), `interest.routes`, `interest.requirements_documents`,
`location.is_local_laguna` (la vista ya expone `is_local_laguna`),
`role_fit.operator_type` (derivado para `objetivo_full_sencillo`).

> Regla: el pipeline escribe SOLO las claves canónicas de la tabla núcleo; las legacy se
> leen para compatibilidad durante la migración y luego se retiran.

## Plan de migración de reglas de negocio (destino por hallazgo §13)

Decisión de dónde vive cada regla detectada en `audit-regex-if.md`. Homes:
**Grafo** (Neo4j: lenguaje→significado, conceptos/aliases) · **Catálogo** (datos de
negocio editables: ciudades, etapas, plantillas, labels) · **Policy** (reglas
condicionales declarativas: vigencia, riesgo, umbrales) · **Planner** (cálculo
determinista por turno) · **Clasificador** (lenguaje→intents/acts) · **Eliminar** ·
**Se queda** (técnico).

### → Grafo Neo4j (resolución de conceptos/lenguaje)
- Alias de ciudad (`KNOWN_CITY_ALIASES`) → nodos `GeoArea` (ya existen; deduplicar el fallback regex).
- Conceptos de licencia y sus alias ("lisensia", "licensia", "tarjeta federal", tipo B/E) → nodos `Term`/concepto `license_federal`.
- Vocabulario de unidad (full, sencillo, quinta rueda, tráiler, tractocamión, camión, torton, rabón, reparto, local) → `VehicleType` + conceptos con flags `target_experience`/`needs_clarification`. Es el backing de `normalize_domain_values`.
- `INTENT_POLICIES` (requires_rag/human, risk_level, preferred_sources por intent) → nodos `Intent/Policy/InternalSource` (task 11.2).

### → Catálogo editable (datos de negocio)
- Catálogo de ciudades/ZM Laguna → `rh_city_catalog` (sql/ ya existe) que alimenta `GeoArea`.
- Texto de las 6 preguntas del funnel (`FUNNEL_STEPS[*].question`) → catálogo de preguntas (el planner referencia ids, no strings hardcodeados).
- Mapa etapa→label español (`_stage`) → `rh_funnel_stage_catalog_v2` (ya existe en DB).
- Respuestas a señales (`_SIGNAL_REPLIES`) → catálogo de plantillas de respuesta.
- Catálogo de labels oficiales + exclusividades → spec `chatwoot-label-taxonomy` (referencia).

### → Policy declarativa (reglas condicionales)
- Vigencia licencia/apto ("vence en N años = vigente", vigente/vencido/trámite) → policy de vigencia.
- `pay_question` = `medium`/`requires_rag`/`requires_human=conditional` + "sin fuente autorizada → derivar a CH" → policy (task 5.1).
- `safety_intent` por `is_admission` → handoff (ya declarativo en enricher; conservar).
- Condiciones de `perfil_listo` (núcleo completo, confirmado, sin conflicto) + exclusividades + remoción de `bot_activo` → policy (en `chatwoot-label-taxonomy`/`postgres-truth-and-label-sync`).
- Política de uso del LLM amistoso (`_should_use_friendly_llm`) → policy de ruteo.
- Limpieza de cierres genéricos (`GENERIC_CLOSING_PATTERNS`) → policy de salida.

### → Planner determinista (cálculo por turno)
- `missing_profile_fields` / "3+ facts clave" (`_is_strong_candidate`) → `funnel_state_planner` (con claves canónicas).
- Ruteo determinista (`_apply_deterministic_overrides`, `_apply_profile_guards`) → resultado del clasificador + `response_planner` (deja de ser if/else de negocio).
- `labels_to_add/remove` → `label_planner` (consume `v_rh_work_queue`).
- Resolución de conflictos de facts (enricher) + correcciones → `resolve_fact_conflicts`/`detect_fact_corrections`.
- Nota privada → `private_note_builder` (después de `label_planner`).

### → Clasificador (lenguaje → intents/acts)
- `greeting`, `farewell`, `local_time`, `document_submission` (ack), `solicitud_llamada` (`_CALL_*_HINTS`) → intents del clasificador, no regex en el orquestador.
- Números ambiguos y sí/no/elípticas → `disambiguate_numeric_units` y `contextual_answer_classifier`.

### → Eliminar
- `_temperatura` (deprecado).
- `"no le veo el problema" → apto vigente` (frase frágil).

### → Se queda (técnico permitido)
- `_clean_reply` (`<think>`), `_is_vigente`, `_risk`, `_normalize_labels`, `_facts_map`.
- `_pending_call_request` (lectura de estado en Postgres).
- Extracción de edad por regex (ES) — vigilar choque con "años".

> Regla transversal: tras la migración, el orquestador deja de decidir negocio con
> `if/else`; consume el resultado del clasificador + grafo + policies y delega a los
> planners. El LLM solo clasifica o redacta sobre contrato cerrado.

## Decisions

- **Architectural Decision: Declarative business rules over ad-hoc code.** Las reglas de
  negocio de reclutamiento NO deben vivir como `if/else`, regex hardcodeados ni parches
  dispersos. Se migran a: catálogos editables, grafo Neo4j, políticas declarativas,
  planners deterministas y estado persistido en Postgres. Aclaración: no se busca eliminar
  todos los `if` técnicos del código, sino las **decisiones de negocio dispersas** y los
  parches ad-hoc. El LLM solo clasifica lenguaje o redacta a partir de un contrato cerrado;
  no decide labels, preguntas del funnel, etapas, ni confirma facts ambiguos.
- **Dos llamadas al LLM, modelos distintos.** Clasificar a JSON usa `llama-3.1-8b-instant`
  (temperature 0.0); redactar la respuesta sigue en el 70B. El 70B **solo redacta**: no
  elige campo ni decide políticas. Clasificar no necesita el modelo grande y cuesta ~10×
  menos tokens.
- **Las políticas NO las decide el LLM.** El enricher aplica un mapa determinista
  `INTENT_POLICIES`. `pay_question` se eleva a `risk_level=medium`, `requires_rag=true`,
  `requires_human=conditional`: sin fuente autorizada suficiente, no se inventa y se deriva
  a Capital Humano. Alternativa descartada: dejar pay en `low/rag` — riesgo de inventar
  cifras de sueldo.
- **`evidence` debe ser literal.** El validador verifica que la evidencia esté contenida en
  el mensaje (`evidence_ok`). Evita que el LLM invente datos de perfil.
- **Memory guard antes del funnel.** Se consulta `lead_memory` antes de proponer cualquier
  pregunta; los campos ya respondidos con evidence válido entran en `forbidden_questions`.
  Un reclamo de memoria ("ya te había dicho que full") se trata como corrección, no como
  mensaje nuevo.
- **Estados de fact.** `confirmed`, `inferred_from_context`, `needs_confirmation`,
  `conflict`, `corrected`. La contradicción sin confirmación NO sobrescribe (pasa a
  `needs_confirmation`); la corrección explícita SÍ sobrescribe y se audita.
- **Desambiguación de respuestas cortas.** "10" sin contexto no se guarda; "10" tras una
  pregunta de años → `experience.years=10` (`inferred_from_context`); "full" tras la
  pregunta de unidad → `vehicle_type=full`, sin activar RAG ni respuestas largas.
- **El sistema calcula la pregunta.** `funnel_state_planner` produce `next_question` a
  partir del funnel único de 6 campos menos `forbidden_questions`; el LLM solo la redacta.
- **`safety_intent` se bifurca por `is_admission`.** Pregunta → RAG; admisión → handoff,
  `risk_level=high`.
- **Nota privada simplificada.** La nota es display-only y muestra solo lo operativo
  (Acción, último mensaje, contacto, memoria breve, perfil, embudo, siguiente acción). Se
  quitan `Temperatura` (subjetiva si no está estrictamente calculada), `Interés en
  pago/compensación` (no es campo núcleo) y la lista de `Labels` (Chatwoot ya las muestra).
- **Taxonomía oficial de labels.** El catálogo y las reglas invariantes (exclusividad,
  `bot_activo`, `falta_*` desde `missing_fields`, condiciones de `perfil_listo`) viven en la
  spec baseline `chatwoot-label-taxonomy`; `label_planner` consume `v_rh_work_queue`.
- **Rollout por shadow.** Shadow corre en paralelo bajo `MULTI_INTENT_SHADOW` y nunca lanza
  excepción; el cutover real va detrás de un flag con rollback inmediato.

## Risks / Trade-offs

- [Doble costo/latencia de LLM por turno] → El clasificador usa el modelo chico y
  temperature 0.0; shadow se mide con `shadow_ms` antes de activar.
- [El LLM clasifica mal un mensaje compuesto] → Guardrail de evidencia + umbral de
  confianza descartan answers dudosos; few-shot extensos en el prompt del clasificador.
- [Sobrescribir un fact por una contradicción ambigua] → Política de no-sobrescritura sin
  confirmación (`needs_confirmation`) + auditoría de correcciones.
- [`INTENT_POLICIES` hardcodeado se desincroniza de los docs RAG] → Marcado como TEMPORAL;
  migra a Neo4j manteniendo la interfaz `enrich_classification`.
- [Repreguntar por desincronía de memoria] → `memory_guard` + `forbidden_questions`
  derivados de `lead_memory` con evidence por fact.
- [Divergencia shadow vs. real difícil de leer] → El log `[MULTI_INTENT_SHADOW]` emite
  JSON comparando `shadow_reply` vs `actual_reply`, intents, facts y acciones.

## Migration Plan

1. Mantener clasificación + shadow + `/classify` (hecho) para pruebas dirigidas.
2. Construir las etapas nuevas: `memory_guard`, `normalize_domain_values`,
   `disambiguate_numeric_units`, `contextual_answer_classifier`, `detect_fact_corrections`,
   `resolve_fact_conflicts`, `funnel_state_planner`, `label_planner`, `private_note_builder`,
   `response_planner`, `final_validator` + estados de fact + auditoría.
3. Activar `MULTI_INTENT_SHADOW=true` con tráfico real; comparar logs y corregir.
4. Migrar `INTENT_POLICIES` a Neo4j.
5. **Cutover behind flag**: `handle_message` delega el turno al pipeline.
   Rollback = apagar el flag y volver al orquestador actual (que permanece intacto).

## Open Questions

- ¿El cutover reemplaza también la extracción regex de `profile_extractor`, o el pipeline
  multi-intent y el extractor coexisten alimentando los mismos facts?
- ¿Quién emite las labels de Chatwoot tras el cutover: el pipeline o sigue
  `chatwoot_note_sync` leyendo lead_memory?
- ¿Dónde se persisten los estados de fact y la auditoría: columnas nuevas en
  `rh_lead_facts_v2` / `rh_lead_events_v2`, o una tabla de auditoría dedicada?
- Definir el mapeo exacto `field → label` (pendiente del "documento del Paso 2").
- Catálogo de intents/fields nuevos a formalizar: `availability`,
  `general_vacancy_info_request` y el reclamo de memoria.
- Naming de facts: **resuelto** — ver "Mapa canónico de nombres de facts" y "Decisiones
  fijadas". Restan las migraciones SQL (tasks 10b.10–10b.14), no decisiones.
