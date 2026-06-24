# Spec: llm-intent-classifiers (delta)

## MODIFIED Requirements

### Requirement: Ya-reclamo consume TurnIntentSignals

El guard `t.startswith("ya ")` SHALL ser eliminado.
`extract_current_turn_facts` MUST aceptar `turn_signals: TurnIntentSignals | None` y leer `turn_signals.is_ya_reclamo` en lugar de invocar su propio LLM.
Si `turn_signals` es None (tests unitarios sin pre-clasificación), SHALL llamar al clasificador internamente.

#### Scenario: Ya-reclamo detectado con frase que no empieza con "ya"

**Given** el candidato envía "eso ya se lo había dicho antes"
**When** `classify_turn_intent` se invoca primero
**Then** `is_ya_reclamo` = True y la confirmación de apto/licencia se suprime

#### Scenario: Backward compatible — sin turn_signals llama LLM internamente

**Given** `extract_current_turn_facts("ya le había dicho que 10 años", ctx)` sin `turn_signals`
**When** se ejecuta
**Then** funciona igual que antes (llama LLM internamente)

### Requirement: Memory-claim consume TurnIntentSignals

`_MEMORY_CLAIM_HINTS` SHALL ser eliminado de `memory_guard.py`.
`_is_memory_claim(message, turn_signals=None)` MUST leer `turn_signals.is_memory_claim` si está disponible.

#### Scenario: Memory claim con frase no listada previamente

**Given** el candidato envía "eso antes ya lo había comentado con su compañero"
**When** el turn pre-classifier corre primero
**Then** `is_memory_claim` = True y `apply_memory_guard` lo procesa correctamente
