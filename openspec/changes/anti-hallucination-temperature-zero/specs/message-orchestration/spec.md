## MODIFIED Requirements

### Requirement: Temperatura de generación conversacional
El sistema SHALL usar temperatura `0.0` para todas las llamadas al LLM en rutas de generación conversacional (`friendly_smalltalk`, `rag`, `clarification`). El valor MUST leerse de la variable de entorno `TEMPERATURE`; el fallback hardcodeado en `app/indexer.py` MUST ser `"0.0"`, nunca un valor mayor. El clasificador (`call_groq_json`) ya usa `temperature=0.0` explícito y no se modifica.

#### Scenario: Generación friendly con temperatura cero
- **WHEN** la ruta es `friendly_smalltalk` y se invoca `call_llm`
- **THEN** la temperatura enviada a la API de Groq es `0.0`

#### Scenario: Generación RAG con temperatura cero
- **WHEN** la ruta es `rag` y se invoca `call_llm` para sintetizar contexto recuperado
- **THEN** la temperatura enviada a la API de Groq es `0.0`

#### Scenario: Fallback conservador si settings falla
- **WHEN** `settings.TEMPERATURE` no está disponible en tiempo de import
- **THEN** `indexer.py` usa `0.0` como fallback, nunca un valor mayor

## ADDED Requirements

### Requirement: Ausencia de bancos de respuestas canned fuera de política de negocio
El sistema MUST NOT tener bancos de strings fijos activados por regex de palabras clave fuera de las políticas de negocio deterministas documentadas (B1/US, reingreso, escuelita/non-target, fraude/pago sensible). Los regex de política de negocio y los hints de no-respuesta (`_NO_ANSWER_HINTS`) están explícitamente excluidos de este requisito y se mantienen.

#### Scenario: Mensaje general procesado sin canned response
- **WHEN** el candidato envía un mensaje que no activa ninguna política de negocio determinista
- **THEN** la respuesta es generada por el LLM con temperatura `0.0` a partir del prompt y el contexto recuperado, sin intercepción por regex de palabras clave

#### Scenario: Política de negocio determinista no afectada
- **WHEN** el candidato menciona B1, Estados Unidos, reingreso, torton, o datos bancarios
- **THEN** se aplica la política determinista correspondiente (handoff o guardia) independientemente de la temperatura
