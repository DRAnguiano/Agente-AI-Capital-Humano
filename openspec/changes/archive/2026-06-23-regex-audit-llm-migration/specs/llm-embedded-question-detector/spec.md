# Spec: llm-embedded-question-detector

Reemplaza `_EMBEDDED_QUESTION_RE` en `current_turn.py` con un clasificador LLM T=0. Este patrón detecta si el mensaje del candidato contiene una pregunta de negocio embebida sin "?" (ej: "soy de gomez palacio que rutas hay").

## ADDED Requirements

### Requirement: Embedded-question LLM classifier

El sistema SHALL reemplazar `_EMBEDDED_QUESTION_RE` por un clasificador LLM T=0 en `current_turn.py`.
El clasificador MUST activarse solo si el mensaje contiene al menos una palabra de `_EMBEDDED_Q_SIGNAL` o `_EMBEDDED_Q_HINTS`.
El prompt MUST devolver `{"has_business_question": true | false}`.
La firma pública `has_embedded_business_question(message)` MUST permanecer inalterada.
Fail-safe: si LLM falla → `False`.

#### Scenario: Pregunta de rutas embebida en perfil

**Given** el candidato envía "soy de gomez palacio que rutas hay"
**When** se llama `has_embedded_business_question`
**Then** retorna `True`

#### Scenario: Perfil puro sin pregunta

**Given** el candidato envía "soy de gomez palacio"
**When** se llama `has_embedded_business_question`
**Then** retorna `False` sin invocar LLM (sin señal de guardia)

#### Scenario: Pregunta de cartas con typo "nececita"

**Given** el candidato envía "Nada más tengo 1 si le sirve o cuantas nececita?"
**When** se llama `has_embedded_business_question`
**Then** retorna `True`

#### Scenario: Declaración de experiencia no es pregunta

**Given** el candidato envía "tengo 10 años manejando full"
**When** se llama `has_embedded_business_question`
**Then** retorna `False`
