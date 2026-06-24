# Spec: candidate-profile-extraction (delta)

## MODIFIED Requirements

### Requirement: Profile extraction consume TurnIntentSignals

`_CALL_INTENT_HINTS`, `_RENEWAL_PROOF_HINTS`, `_no_road_hints`, `_expiry_hints` y `DRIVING_TERMS` como gates SHALL ser eliminados de `profile_extractor.py`.
`extract_profile_facts(message, intent, turn_signals=None)` MUST aceptar `TurnIntentSignals` y leer:
- `turn_signals.call_requested` → registrar `scheduling.call_requested`
- `turn_signals.renewal_proof` → registrar `documents.renewal_proof`
- `turn_signals.no_road_experience` → registrar `experience.road_experience = "none"`
- `turn_signals.has_expiry_context` → activar extracción de fecha/texto de vencimiento
- `turn_signals.experience_context` → activar extracción de `experience.years`

#### Scenario: Call intent con frase no listada

**Given** el candidato envía "prefiero que se pongan en contacto conmigo"
**When** el turn pre-classifier clasifica `call_requested = True`
**Then** `scheduling.call_requested` = "true" se registra

#### Scenario: Vencimiento con variante "se me acaba"

**Given** el candidato envía "se me acaba la vigencia del apto en 3 meses"
**When** el pre-classifier retorna `has_expiry_context = True`
**Then** el extractor de fecha de vencimiento se activa y captura el plazo

#### Scenario: Experience years para "transportista" (no en DRIVING_TERMS previos)

**Given** el candidato envía "soy transportista desde hace 8 años"
**When** el pre-classifier retorna `experience_context = True`
**Then** `experience.years` = "8 años" se registra

#### Scenario: No-road-experience con "soy principiante"

**Given** el candidato envía "soy principiante en esto del tracto"
**When** el pre-classifier retorna `no_road_experience = True`
**Then** `experience.road_experience` = "none" se registra y la ruta cecati_sugerido aplica

### Requirement: Guards estructurales y de seguridad permanecen intactos

Los siguientes guards SHALL mantenerse sin cambio:
- `_PAID_SENSITIVE_RE` (fraude/costo al candidato)
- `_residence_markers` (ancla de zona para extracción de ciudad)
- `normalize_vehicle()` (catálogo determinista)
- Checks de unidad temporal (días/semanas/meses)

#### Scenario: _PAID_SENSITIVE_RE no se modifica

**Given** el candidato envía "hay que pagar para el examen médico"
**When** el pipeline procesa el mensaje
**Then** `_PAID_SENSITIVE_RE` intercepta y enruta a human_handoff antes del turn pre-classifier
