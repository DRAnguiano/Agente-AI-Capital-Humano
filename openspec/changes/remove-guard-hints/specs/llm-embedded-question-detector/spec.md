# Spec: llm-embedded-question-detector (delta)

## MODIFIED Requirements

### Requirement: Embedded question consume TurnIntentSignals

`_EMBEDDED_Q_HINTS` y `_EMBEDDED_Q_SIGNAL` SHALL ser eliminados.
`has_embedded_business_question(message, turn_signals=None)` MUST leer `turn_signals.has_embedded_question` si está disponible, sin invocar un LLM propio.
Si `turn_signals` es None, SHALL llamar al clasificador internamente (compatibilidad tests).

#### Scenario: Pregunta de negocio con vocabulario no listado

**Given** el candidato envía "¿dan comida en los viajes largos?"
**When** el turn pre-classifier corre
**Then** `has_embedded_question` = True (no requiere "rutas" ni "pagan" en hints)

#### Scenario: Perfil puro — no activa LLM ni retorna True

**Given** el candidato envía "soy de Gómez Palacio, tengo licencia E"
**When** `has_embedded_business_question` se llama con `turn_signals` precalculados
**Then** retorna False sin llamada LLM adicional
