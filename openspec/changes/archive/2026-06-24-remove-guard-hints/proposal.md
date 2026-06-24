## Why

Los guards de palabras clave que preceden cada clasificador LLM generan falsos negativos silenciosos: si el mensaje del candidato usa una frase no listada, el LLM nunca se invoca y la señal se pierde sin error visible. El gremio de operadores tiene vocabulario variado — "eso antes ya se lo mencioné", "ponerse en contacto", "tengo el recibo", "soy principiante" — que ninguna lista finita puede cubrir. El LLM ya demuestra capacidad para clasificar correctamente estas señales; la lista de hints es el cuello de botella.

## What Changes

- **ELIMINAR** todas las listas de palabras clave que actúan como `gate` para invocar un clasificador LLM semántico:
  - `_MEMORY_CLAIM_HINTS` en `memory_guard.py`
  - `_EMBEDDED_Q_HINTS` + `_EMBEDDED_Q_SIGNAL` en `current_turn.py`
  - `_CALL_INTENT_HINTS` en `profile_extractor.py`
  - `_RENEWAL_PROOF_HINTS` en `profile_extractor.py`
  - `_no_road_hints` en `profile_extractor.py`
  - `_expiry_hints` en `profile_extractor.py`
  - `t.startswith("ya ")` como gate del ya-reclamo en `current_turn.py`
  - `DRIVING_TERMS` como gate de experience years en `profile_extractor.py`

- **REEMPLAZAR** las N llamadas LLM separadas (cada una con su guard) por un único **turn intent pre-classifier**: una sola llamada LLM T=0 por turno que devuelve todos los signals semánticos en un JSON, antes de que el resto del pipeline los consuma.

- **CONSERVAR** los guards que NO son semánticos (el LLM no puede reemplazarlos):

  | Guard | Módulo | Por qué se queda |
  |-------|--------|-----------------|
  | `_PAID_SENSITIVE_RE` | `knowledge_orchestrator.py` | Seguridad / fraude: fail-closed, no negociable |
  | `_B1_US_RE`, `_REINGRESO_RE`, `_NON_TARGET_RE` | `knowledge_orchestrator.py` | Política de negocio determinista (ruta ≠ intención) |
  | `_residence_markers` | `profile_extractor.py` | Ancla estructural de zona de extracción, no gate semántico |
  | `normalize_vehicle()` catalog | `domain_catalog.py` | Datos de dominio deterministas |
  | Checks de unidad temporal (días/semanas/meses) | `profile_extractor.py` | Análisis estructural de formato |
  | Field prefix checks (`candidate.`, `license.`) | `current_turn.py` | Validación de esquema, no semántica |
  | `_conditional_si` structural guard | `current_turn.py` | Parsing sintáctico del "sí/si" afirmativo |

## Capabilities

### New Capabilities

- `turn-intent-classifier`: clasificador unificado de señales de intención por turno — una sola llamada LLM T=0 que devuelve `{is_ya_reclamo, is_memory_claim, has_embedded_question, call_requested, renewal_proof, has_renewal_proof_context, no_road_experience, has_expiry_context}` antes de que el pipeline de extracción consuma cada señal.

### Modified Capabilities

- `llm-intent-classifiers`: eliminar guards de hint list; consumir señales del turn-intent-classifier
- `llm-embedded-question-detector`: eliminar guards; consumir `has_embedded_question` del pre-classifier
- `candidate-profile-extraction`: eliminar guards de `_CALL_INTENT_HINTS`, `_RENEWAL_PROOF_HINTS`, `_no_road_hints`, `_expiry_hints`, `DRIVING_TERMS`; consumir señales del pre-classifier

## Impact

- `app/knowledge/current_turn.py` — eliminar `_EMBEDDED_Q_HINTS`, `_EMBEDDED_Q_SIGNAL`, gate `t.startswith("ya ")` y `DRIVING_TERMS`; añadir consumo del pre-classifier
- `app/knowledge/memory_guard.py` — eliminar `_MEMORY_CLAIM_HINTS`; consumir `is_memory_claim` del pre-classifier
- `app/lead_memory/profile_extractor.py` — eliminar `_CALL_INTENT_HINTS`, `_RENEWAL_PROOF_HINTS`, `_no_road_hints`, `_expiry_hints`, `DRIVING_TERMS`; consumir del pre-classifier
- `app/knowledge/turn_intent_classifier.py` — archivo nuevo con el clasificador unificado
- Tests: los `skipif(_NO_GROQ)` se mantienen; se añaden tests del clasificador unificado
- Groq: 1 call/turno fijo en lugar de 0–8 calls condicionales → latencia más predecible, costo acotado
