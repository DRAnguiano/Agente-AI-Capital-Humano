# candidate-profile-extraction Specification

## Purpose
TBD - created by archiving change regex-audit-llm-migration. Update Purpose after archive.
## Requirements
### Requirement: renewal-proof LLM classifier

El sistema SHALL reemplazar los dos regex polares de `_has_renewal_proof()` por un clasificador LLM T=0 en `profile_extractor.py`.
El clasificador MUST activarse solo cuando el texto normalizado contenga al menos una de `_RENEWAL_PROOF_HINTS`.
El prompt MUST devolver `{"renewal_proof": "si" | "no" | null}`.
Cuando `renewal_proof = null`, el sistema SHALL no registrar fact (comportamiento idéntico al anterior).

#### Scenario: Candidato tiene comprobante de trámite

**Given** el candidato envía "ya pagué la cita para renovar"
**When** se extrae el perfil
**Then** `documents.renewal_proof` = "si"

#### Scenario: Candidato no tiene comprobante

**Given** el candidato envía "todavía no tengo el comprobante"
**When** se extrae el perfil
**Then** `documents.renewal_proof` = "no"

#### Scenario: Mensaje sin mención de trámite — no activa LLM

**Given** el candidato envía "tengo 10 años manejando full"
**When** se extrae el perfil
**Then** `documents.renewal_proof` no se registra (no hay guardia, no se llama LLM)

### Requirement: call-intent LLM classifier

El sistema SHALL unificar `_CALL_REQUEST_RE` y `_CALL_NEG_RE` en un único clasificador LLM T=0 en `profile_extractor.py`.
El clasificador MUST activarse solo cuando el texto normalizado contenga al menos una de `_CALL_INTENT_HINTS`.
El prompt MUST devolver `{"call_requested": true | false}`.
Cuando `call_requested = true`, el sistema SHALL registrar `scheduling.call_requested = "true"` y `scheduling.call_status = "pending"`.

#### Scenario: Solicitud de llamada explícita

**Given** el candidato envía "quiero que me llamen"
**When** se extrae el perfil
**Then** `scheduling.call_requested` = "true" y `scheduling.call_status` = "pending"

#### Scenario: Rechazo de llamada

**Given** el candidato envía "no me llamen por favor"
**When** se extrae el perfil
**Then** `scheduling.call_requested` no se registra

### Requirement: no-road-experience sin duplicado de regex

El sistema SHALL eliminar `_NO_ROAD_EXPERIENCE_RE` de `knowledge_orchestrator.py` y MUST delegar la detección a `extract_profile_facts_as_dict()` (que ya usa `_NO_ROAD_EXP_SYSTEM` LLM T=0 en `profile_extractor.py`).
La guardia del orquestador MUST verificar palabras clave antes de llamar al extractor.
Cuando `experience.road_experience` = "none", el sistema SHALL mantener la ruta `cecati_sugerido` sin cambio de contrato.

#### Scenario: Candidato sin experiencia → cecati

**Given** el candidato envía "no tengo experiencia en tracto"
**When** se aplican reglas de negocio
**Then** `route` = "human_handoff" e `intent` = "cecati_sugerido"

#### Scenario: Candidato con experiencia no se ve afectado

**Given** el candidato envía "tengo 10 años manejando full"
**When** se aplican reglas de negocio
**Then** la ruta no es "human_handoff" por cecati

