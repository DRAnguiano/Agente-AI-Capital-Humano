## ADDED Requirements

### Requirement: Sugerencia de llamada condicionada al horario de oficina

Toda sugerencia de llamada o coordinación de contacto telefónico en el reply al candidato SHALL pasar por `is_business_hours()`. Dentro del horario de atención el mensaje SHALL indicar que el equipo lo contactará; fuera del horario SHALL ofrecer el mensaje de llamada/agenda. Ningún módulo SHALL emitir una sugerencia de llamada incondicional.

#### Scenario: Candidato escribe dentro del horario de atención
- **WHEN** el candidato completa o avanza su perfil a las 10:38 (lun-vie 08:00–17:30 centro de México)
- **THEN** el reply indica que el equipo lo contactará dentro del horario de atención
- **AND** NO sugiere que el candidato agende ni solicite una llamada

#### Scenario: Candidato escribe fuera del horario de atención
- **WHEN** el candidato escribe fuera de 08:00–17:30 o en fin de semana
- **THEN** el reply ofrece el mensaje de llamada/agenda y el rango horario válido

### Requirement: Política de horario centralizada

La decisión de horario SHALL resolverse mediante el helper canónico `is_business_hours()` (zona horaria centro de México). Los templates de seguimiento (`followup`) y la ruta RAG/LLM SHALL consumir esa misma decisión en lugar de copy hardcodeado sin chequeo.

#### Scenario: Template de seguimiento profile_ready/human_review
- **WHEN** el scheduler de seguimiento genera un mensaje para una etapa de llamada
- **THEN** el copy refleja el estado de horario vigente vía `is_business_hours()`

### Requirement: Voz de equipo en mensajes de contacto

Los mensajes de contacto/derivación SHALL usar la voz de equipo ("nuestro equipo", "aquí lo revisamos", "nos pondremos en contacto") y SHALL NOT referirse a "Capital Humano" como un tercero separado del asistente.

#### Scenario: Intro de primer contacto
- **WHEN** se antepone el intro público en la primera respuesta
- **THEN** el texto NO presenta a Mundo como "asistente de Capital Humano" en tercera persona

#### Scenario: Mensaje de documentos por residencia
- **WHEN** el reply menciona la derivación por documentos faltantes
- **THEN** usa la voz de equipo y no atribuye la acción a "Capital Humano" como tercero
