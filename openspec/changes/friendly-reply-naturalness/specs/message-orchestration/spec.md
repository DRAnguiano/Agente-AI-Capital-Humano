## MODIFIED Requirements

### Requirement: Grounding del comentario conversacional
El LLM amistoso MUST NOT recibir frases de ejemplo literales en el prompt de tono cuando el candidato tiene buen perfil. La instrucción de tono SHALL describir el efecto deseado (breve, cálido, sin prometer contratación) sin citar frases concretas que el modelo pueda imitar. La misma frase de cierre NO MUST aparecer más de una vez por conversación.

#### Scenario: Candidato con buen perfil — variedad en cierre
- **WHEN** `_is_strong_candidate` es True y se invoca `_answer_friendly_message`
- **THEN** el prompt de tono NO contiene frases literales como "Con ese perfil nos interesa conocerle" ni "Va por buen camino"

#### Scenario: Confirmación de experiencia no repite frase de cierre
- **WHEN** el sistema emite la confirmación de `experience.years` en la ruta `profile`
- **THEN** el texto confirma el dato capturado (ej. "6 años de experiencia, anotado.") sin agregar "Con ese perfil nos interesa conocerle"

### Requirement: Variantes de funnel sin registro formal
Las variantes de las preguntas del funnel SHALL usar lenguaje directo de reclutador mexicano. La variante `"Para su perfil, ¿cuántos años lleva manejando de manera profesional?"` MUST eliminarse del step `experience.years` por sonar a entrevista corporativa.

#### Scenario: Pregunta de años de experiencia
- **WHEN** el sistema emite la pregunta de `experience.years`
- **THEN** la variante elegida es "¿Cuántos años tiene de experiencia como operador?" o "¿Cuánto tiempo tiene de experiencia al volante?" — nunca "de manera profesional"

## ADDED Requirements

### Requirement: RAG no promete contacto antes de perfil completo
El prompt del generador RAG MUST NOT instruir al LLM a decir "nuestro equipo lo contactará" cuando el perfil del candidato no está completo (faltan campos del funnel). Esa promesa SHALL emitirse únicamente en la ruta de handoff o cuando el label `perfil_listo` está activo.

#### Scenario: RAG responde sin perfil completo
- **WHEN** la ruta es `rag`, el candidato tiene campos pendientes del funnel (`falta_*` labels activos) y se invoca el generador RAG
- **THEN** la respuesta NO contiene la frase "nuestro equipo lo contactará" ni variantes equivalentes

#### Scenario: Handoff con perfil completo
- **WHEN** el label `perfil_listo` está activo y la ruta es `human_handoff`
- **THEN** la respuesta puede incluir que el equipo dará seguimiento
