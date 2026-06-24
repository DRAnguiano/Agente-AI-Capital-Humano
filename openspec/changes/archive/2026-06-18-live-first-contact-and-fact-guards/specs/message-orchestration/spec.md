# message-orchestration (delta)

## ADDED Requirements

### Requirement: Saludo oficial obligatorio en primer contacto

El sistema SHALL responder con el saludo oficial de Mundo (`GREETING_REPLY`) en
el primer contacto de una conversación (sin mensaje previo del asistente) cuando
el mensaje entrante es un saludo o una entrada de campaña/interés (p. ej. el
mensaje default de la publicación de Facebook "Me interesa la vacante de
operador de quinta rueda"). El current-turn guard NO SHALL aplicar su ack
("Perfecto, lo dejo registrado...") en ese turno.

#### Scenario: Entrada de campaña de Facebook
- **WHEN** el primer mensaje de la conversación es "Me interesa la vacante de operador de quinta rueda"
- **THEN** la respuesta es el saludo oficial de Mundo
- **AND** no contiene "lo dejo registrado"

#### Scenario: Primer mensaje con pregunta no usa el saludo forzado
- **WHEN** el primer mensaje es "me interesa la vacante, cuanto pagan?"
- **THEN** la entrada NO se trata como apertura de campaña (es pregunta) y sigue el flujo normal de respuesta

### Requirement: El interés en la vacante no es señal de perfil

El sistema NO SHALL tratar `candidate.vacancy_accepted` como señal de perfil del
current-turn guard: un mensaje cuyo único fact es el interés en la vacante no
dispara el ack de registro.

#### Scenario: Interés puro no dispara el guard
- **WHEN** el mensaje solo expresa interés ("me interesa la vacante de operador")
- **THEN** `has_current_turn_profile_signal` es falso y el guard no reemplaza la respuesta
