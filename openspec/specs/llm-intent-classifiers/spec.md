# llm-intent-classifiers Specification

## Purpose
TBD - created by archiving change regex-audit-llm-migration. Update Purpose after archive.
## Requirements
### Requirement: Ya-reclamo LLM classifier

El sistema SHALL reemplazar el regex `_ya_reclamo` por un clasificador LLM T=0 en `current_turn.py`.
El clasificador MUST activarse solo cuando el mensaje normalizado empieza con `"ya "`.
El prompt MUST devolver `{"is_complaint": true | false}`.
Si `is_complaint = true`, el sistema SHALL suprimir la extracción de facts de confirmación en ese turno.
Fail-safe: si LLM falla → `_ya_reclamo = False`.

#### Scenario: Ya-reclamo suprime confirmación de apto

**Given** el candidato envía "Ya le habia dicho que 10 años"
**When** la pregunta anterior pregunta por licencia y apto
**Then** `medical.apto_status` ≠ "vigente" y `license.status` ≠ "vigente"

#### Scenario: Ya-confirmativo no suprime

**Given** el candidato envía "ya"
**When** la pregunta anterior pregunta por apto
**Then** `medical.apto_status` = "vigente"

### Requirement: Memory-claim LLM classifier

El sistema SHALL reemplazar los 6 patrones de `_MEMORY_CLAIM_PATTERNS` por un clasificador LLM T=0 en `memory_guard.py`.
El clasificador MUST activarse solo cuando el mensaje contiene al menos una palabra de `_MEMORY_CLAIM_HINTS`.
El prompt MUST devolver `{"is_memory_claim": true | false}`.
Fail-safe: si LLM falla → `False` (no clasifica como reclamo).

#### Scenario: Memory claim detectado con frase clásica

**Given** el candidato envía "ya te había dicho que full"
**And** existe fact previo `experience.vehicle_type = full`
**When** se aplica `apply_memory_guard`
**Then** `memory_claim.resolution` = "reaffirm"

#### Scenario: No-claim sin frase de reclamo

**Given** el candidato envía "si tengo cartas"
**When** se aplica `apply_memory_guard`
**Then** `memory_claim` = null

