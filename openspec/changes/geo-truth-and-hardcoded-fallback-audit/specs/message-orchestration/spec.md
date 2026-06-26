## ADDED Requirements

### Requirement: Lógica foráneo→documento sin duplicación

La regla de "documento laboral por residencia" (local acepta semanas IMSS; foráneo exige 2 cartas membretadas) SHALL existir en una sola función de dominio consumida por todas las rutas. El orquestador y el generador de pregunta de funnel SHALL NOT mantener copias divergentes de esta lógica.

#### Scenario: Misma decisión en funnel y orquestador
- **WHEN** un candidato local sin documento laboral avanza por el funnel o por la ruta del orquestador
- **THEN** ambas rutas producen la misma pregunta de documento (semanas IMSS / cartas) según `location.is_local_laguna`
- **AND** no hay dos bloques de código que decidan foráneo de forma independiente

### Requirement: La ruta RAG/LLM no improvisa residencia ni horario

Cuando el guard de perfilamiento se suprime (p. ej. pregunta embebida) y la respuesta se genera por la ruta RAG/LLM, esa ruta SHALL recibir las señales deterministas de residencia (`location.is_local_laguna`) y horario (`is_business_hours()`) ya resueltas, o tener prohibido afirmarlas.

#### Scenario: Pregunta de pago con ciudad local en el mismo mensaje
- **WHEN** "soy de Chávez, ¿cuánto pagan?" rutea a RAG por la pregunta embebida
- **THEN** el reply responde el pago sin afirmar que el candidato es foráneo
- **AND** cualquier mención de documentos respeta `location.is_local_laguna=true`
