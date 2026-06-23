# Spec: llm-embedded-question-detector

Reemplaza `_EMBEDDED_QUESTION_RE` en `current_turn.py` con un clasificador LLM T=0. Este patrón detecta si el mensaje del candidato contiene una pregunta de negocio embebida sin "?" (ej: "soy de gomez palacio que rutas hay").

## Por qué migrar

`_EMBEDDED_QUESTION_RE` es el patrón más frágil del sistema: tiene ~60 tokens de alternación, requiere coordinación de dos subexpresiones (pregunta + tema), y falla ante cualquier variante léxica nueva ("que corridas hay", "cuanto dan de bono", etc.).

## Requisitos

### R1 — Detección de pregunta de negocio embebida
- **Señal de activación**: el mensaje contiene al menos una palabra de las siguientes categorías en normalized text: `("que", "cuanto", "cuantos", "como", "hay", "ay", "dan", "pagan", "necesitan")`
- **Clasificador**: devuelve `{"has_business_question": true | false}`
- **true**: el mensaje incluye una pregunta sobre condiciones laborales (rutas, pago, sueldo, requisitos, boletos, prestaciones, descansos, horarios)
- **false**: el mensaje es una declaración de perfil sin pregunta embebida

### R2 — Comportamiento cuando `has_business_question = true`
- El orquestador responde la pregunta de negocio (RAG/Neo4j)
- Los facts del turno actual SE SIGUEN extrayendo y persistiendo normalmente
- El guard NO secuestra el turno: la respuesta incluye tanto el ack del fact como la respuesta a la pregunta

### R3 — Guard de contexto (pre-LLM)
- Solo se invoca el LLM si hay al menos una palabra de la lista de señal en `text` (normalized)
- Si no hay señal → `has_business_question = False` directamente sin LLM call

## Contratos de test

- `"soy de gomez palacio que rutas hay"` → `has_business_question = True`
- `"soy de gomez palacio"` → `has_business_question = False` (sin señal → no LLM call)
- `"cuantos años de experiencia necesitan"` → `has_business_question = True`
- `"tengo 10 años manejando full"` → `has_business_question = False`

## Archivos afectados

- `app/knowledge/current_turn.py` — reemplazar `_EMBEDDED_QUESTION_RE` y `has_embedded_business_question()`
