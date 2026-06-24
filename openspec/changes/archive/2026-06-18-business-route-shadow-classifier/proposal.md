## Why

El harness QA (`response-qa-intent-classification`) confirmó que el clasificador LLM
existente devuelve intents **conversacionales** correctos, pero las rutas de negocio del
sistema (vacante, escuelita, CECATI, B1, reingreso) no están capturadas como contrato
verificable ni enlazadas con los hechos de perfil que deben derivar de ellas.

Ejemplos concretos del harness (`qa_alta_v3.csv`, 13 casos Alta):

- `qa_0016`: "Me interesa para sencillo" → `candidate_interest` (correcto conversacional),
  pero el negocio requiere `experience.vehicle_type = sencillo` y ruta
  `objetivo_full_sencillo`. El intent solo es suficiente con un fact explícito.
- `qa_0030`: "Tengo carta de torton + apto" → `document_submission` (correcto), pero el
  negocio requiere señal `considerar_escuelita_transmontes` porque el tipo de unidad es
  no-objetivo. El intent no capture este hecho.
- `qa_0032`: "Ok" (seguimiento) → `out_of_scope` (incorrecto), sin señal de negocio.

**Gap raíz**: el LLM entiende el lenguaje; el negocio requiere hechos estructurados
(`explicit_facts`), señales de ruta (`business_signals`) y flags de ambigüedad
(`ambiguity_flags`). Hoy eso vive implícitamente en RAG y prompts ad-hoc, sin contrato.

**Objetivo**: definir y versionar un contrato explícito de output estructurado para una
capa de clasificación de ruta de negocio, que corra en **shadow mode** (sin mutar estado
ni decidir routing productivo) y sea verificable con el harness QA.

## What Changes

- **Nueva capability** `recruiting-business-route-classification`: capa shadow que enriquece
  la clasificación conversacional con hechos explícitos de negocio, señales de ruta y flags
  de ambigüedad. No reemplaza el intent classifier existente; lo complementa.
- **Output estructurado**: `explicit_facts`, `business_signals`, `ambiguity_flags`,
  `requires_human`, `evidence` — contrato Pydantic/dataclass versionado.
- **Reglas de negocio en el contrato**, no solo en RAG: tipo de unidad, jerga ambigua,
  experiencia no-objetivo, sin experiencia, B1/EUA, reingreso, documentos, vigencia.
- **Policy router determinístico**: valida que el LLM no invente facts ni contradiga
  reglas de negocio; solo emite lo que tiene evidencia.
- **Shadow mode estricto**: no escribe a DB, no actualiza Chatwoot, no cambia routing vivo.
- **QA harness integrado**: `scripts/qa_response_matrix.py` valida el shadow classifier
  antes de cualquier activación productiva. Prerrequisito: ≥ 80% PASS_STRONG.

## Capabilities

### New Capabilities
- `recruiting-business-route-classification`: clasifica el mensaje en una ruta de negocio
  explícita con hechos, señales, ambigüedad y requisito de humano — en shadow mode.

### Modified Capabilities
- `profile-extraction`: actualizar spec para reflejar que el catálogo de dominio
  (`normalize_domain_values`, `domain_catalog`) es la fuente de verdad para vehicle_type,
  no regex ad-hoc; y que esta capa alimenta al shadow classifier de ruta.

## Impact

- **Archivos a crear (shadow, no productivos todavía):**
  `app/knowledge/business_route_classifier.py` (shadow, read-only).
- **Schema/contrato:** `app/knowledge/business_route_schema.py` (Pydantic/dataclass).
- **Reutiliza sin modificar:**
  `app/knowledge/normalize_domain_values.py` (normalize_vehicle, applies_objetivo_full_sencillo),
  `app/knowledge/domain_catalog.py` (VEHICLE_TERMS, VehicleResolution),
  `app/knowledge/intent_classifier.py` (sin tocar),
  `app/knowledge/text_normalizer.py` (sin tocar).
- **Scripts:** `scripts/qa_response_matrix.py` (integración shadow output).
- **Tests:** `tests/test_business_route_classifier.py` (nuevo).
- **No tocar:** `app/app.py`, `app/tasks_chatwoot.py`, `app/orchestrators/`, `app/db.py`,
  prompts productivos vivos, Chatwoot, DB, migraciones, route1.
- **Prerequisito de activación productiva:** ≥ 80% PASS_STRONG en harness QA (224 casos).
