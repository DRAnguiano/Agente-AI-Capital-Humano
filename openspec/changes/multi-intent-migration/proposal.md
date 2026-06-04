## Why

El ruteo y la extracción de perfil viven hoy en un `knowledge_orchestrator` monolítico
(~240 líneas, 6 responsabilidades) con la lógica del funnel dispersa en tres lugares
(`_FUNNEL_STEPS`, `next_question_from_missing_facts`, el `SYSTEM_PROMPT`). Eso hace
frágil un requisito central del negocio: los mensajes de WhatsApp suelen ser
**compuestos** ("sí me interesa, pero ¿cuánto pagan?") — traen una respuesta de perfil y
una pregunta a la vez, y el sistema actual no los separa de forma confiable. Además, hoy
el bot **repite preguntas ya respondidas**, no distingue una **corrección** de un dato
nuevo, y guarda **respuestas cortas ambiguas** ("10") fuera de contexto. Queremos un
pipeline explícito que, además de clasificar, **controle la memoria conversacional, el
estado del funnel, la prevención de preguntas repetidas, la corrección/contradicción de
facts y la desambiguación de respuestas cortas**, con el funnel unificado en una sola
fuente de verdad (`docs/esquema_perfilamiento_v1.md`).

## What Changes

- Introducir un **pipeline multi-intent** que no solo clasifica, sino que gobierna el
  turno completo de extremo a extremo:
  - **Clasificador** (`intent_classifier.py`): LLM pequeño (`8b-instant`) devuelve JSON con
    `message_type`, `primary_intent`, `secondary_intents`, `answers[]` (con `evidence`
    literal + `confidence`) y `questions[]`.
  - **Enricher** (`intent_enricher.py`): resuelve conflictos de campo, filtra answers
    persistibles (`evidence_ok AND confidence ≥ 0.85`) y enriquece cada question con
    políticas deterministas. **BREAKING (política):** `pay_question` pasa a
    `risk_level=medium`, `requires_rag=true`, `requires_human=conditional`; si no hay
    fuente autorizada suficiente, el sistema NO inventa y deriva a Capital Humano.
  - **Memory guard** (`conversation-memory-guard`): consulta `lead_memory` antes de emitir
    cualquier pregunta del funnel; no repite preguntas ya respondidas con evidence válido;
    reconoce reclamos de memoria ("ya te había dicho que full") como corrección, no como
    mensaje normal.
  - **Desambiguación y corrección de facts** (`fact-disambiguation-and-correction`):
    distingue dato nuevo / incompleto / corrección / contradicción / respuesta elíptica
    dependiente de `last_bot_question`. Las contradicciones sin confirmación no
    sobrescriben; las correcciones explícitas sí, con auditoría.
  - **Funnel state planner** (`funnel-state-planner`): por turno calcula
    `completed_fields`, `missing_fields`, `forbidden_questions`, `next_question`,
    `facts_before` y `facts_after`. El LLM nunca decide qué preguntar: el sistema calcula
    la pregunta y el LLM solo la **redacta** cordialmente.
  - **Estados de fact**: `confirmed`, `inferred_from_context`, `needs_confirmation`,
    `conflict`, `corrected`.
  - **Auditoría por turno**: `facts_before`, `candidate_corrections`,
    `facts_pending_confirmation`, `facts_after`, `missing_fields`, `forbidden_questions`,
    `next_question`, `confirmation_question`.
  - **Shadow** (`intent_shadow.py`): corre el pipeline en paralelo bajo `MULTI_INTENT_SHADOW`,
    sin afectar al candidato.
- Exponer el pipeline para pruebas aisladas vía `POST /classify`.
- **Funnel unificado**: las 6 preguntas del núcleo viven solo en el funnel planner,
  reemplazando las tres fuentes dispersas.
- **Cutover (pendiente, behind flag)**: el orquestador delega el turno al pipeline.
  **BREAKING** para la lógica interna de `message-orchestration`, no para el contrato HTTP.

## Capabilities

### New Capabilities
- `multi-intent-pipeline`: clasificación → enriquecimiento → memory guard → desambiguación
  → corrección/contradicción → planeación del estado del funnel → redacción por LLM →
  persistencia/auditoría de un mensaje de candidato. Incluye guardrail anti-alucinación,
  políticas deterministas, estados de fact y funnel unificado.
- `candidate-profile-label-planner`: conversión determinista de facts confirmados a labels
  de Chatwoot (objetivo full/sencillo vs. no objetivo, local/foráneo, disponibilidad,
  faltantes hasta `perfil_listo`, reingreso). El LLM no decide labels, no marca perfil
  listo, no elimina `bot_activo` ni afirma datos sin evidencia.
- `postgres-truth-and-label-sync`: Postgres como fuente de verdad operativa; labels de
  Chatwoot derivados del estado persistido (no del LLM ni de la nota privada), con
  verificación de completitud antes de `perfil_listo`, no-sobrescritura de conflictos y
  auditoría de cada cambio de label. Solo `label_planner`/`chatwoot_sync` modifican labels.

### Modified Capabilities
- `message-orchestration`: la selección de ruta y la emisión de la pregunta de perfil
  pasan a derivarse del pipeline multi-intent cuando el flag de cutover esté activo
  (hoy: shadow, sin cambiar la respuesta real).

## Impact

- **Código existente (clasificación/shadow):** `app/knowledge/intent_classifier.py`,
  `intent_enricher.py`, `intent_orchestrator.py`, `intent_shadow.py`,
  `extraction_schema.json`, `graph_schema.json`, `schema_validator.py`.
- **Código nuevo a construir:** etapas `memory_guard`, `normalize_domain_values`,
  `disambiguate_numeric_units`, `contextual_answer_classifier`, `detect_fact_corrections`,
  `resolve_fact_conflicts`, `funnel_state_planner`, `label_planner`, `private_note_builder`,
  `response_planner`, `final_validator`; estados de fact y campos de auditoría (ver `tasks.md`).
- **Tocado:** `app/orchestrators/knowledge_orchestrator.py` (hook de shadow / cutover),
  `app/app.py` (endpoint `/classify`), `app/lead_memory/repository.py` (lectura de
  evidence por fact + auditoría de correcciones).
- **Diseño fuente:** `docs/esquema_perfilamiento_v1.md`, `app/policies/conversation_policy.md`.
- **LLM:** `GROQ_CLASSIFIER_MODEL=llama-3.1-8b-instant` para clasificar; el 70B solo redacta.
- **Pendiente:** mover `INTENT_POLICIES` del enricher a Neo4j sin cambiar la interfaz de
  `enrich_classification`.
